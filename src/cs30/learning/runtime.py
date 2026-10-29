"""Single-session runtime for real hybrid retrieval, API answers and practice."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime
from threading import RLock

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.grader import DeterministicGrader
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider, target_levels
from cs30.concept_check.service import ConceptCheckService, PreparedRound
from cs30.concept_check.snapshot import build_learner_context_snapshot
from cs30.concept_check.topics import ChunkTopicResolver
from cs30.generation.compatible import OpenAICompatibleClient
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckEvent,
    ConceptCheckEventType,
    ConceptCheckResult,
    LearnerState,
    StudentLevel,
    StudentProfile,
    TopicResolutionStatus,
    TopicState,
)
from cs30.v2.evidence import CitationValidatorAdapter, EvidenceBundleAdapter
from cs30.v2.experiment import rerank_retrieval
from cs30.v2.generation import V2AnswerGenerator

from .assets import (
    LearningAssets,
    SetupReport,
    check_learning_setup,
    load_learning_assets,
)
from .budget import BudgetedClient, PersistentRequestBudget
from .config import ApiRoleConfig, LearningConfig, LearningConfigurationError
from .models import LearningTurn, OnlineQuizView, PracticeResult, TopicSelectionTrace
from .online_quiz import DraftQuiz, OnlineQuizGenerator, OnlineQuizUnavailable
from .retrieval import build_online_hybrid_retriever, restore_v2_retrieval_result
from .topic_selection import select_cited_demo_topic


class LearningSetupBlocked(RuntimeError):
    def __init__(self, report: SetupReport) -> None:
        self.report = report
        blockers = "; ".join(f"{item.name}: {item.detail}" for item in report.blockers)
        super().__init__(blockers or "learning demo setup is incomplete")


def _create_client(role: ApiRoleConfig) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        role.model,
        base_url=role.base_url,
        provider_name=role.provider_name,
        model_version=role.model_version,
        api_key_env=role.api_key_env,
        timeout_seconds=role.timeout_seconds,
        max_output_tokens=role.max_output_tokens,
        structured_output=role.structured_output,
        transport_retries=0,
        max_api_requests=None,
        extra_body=role.extra_body,
    )


def build_learning_runtime(
    config: LearningConfig,
    static_profile: StudentProfile,
    *,
    concept_check: bool = True,
) -> LearningRuntime:
    """Construct a runtime only after local assets, keys and budget pass doctor."""

    report = check_learning_setup(config)
    if not report.ready:
        raise LearningSetupBlocked(report)
    if static_profile.confidence != 1.0:
        raise LearningConfigurationError(
            "The selected Dev lambda is bound to profile_confidence=1.0"
        )
    assets = load_learning_assets(config)
    request_budget = PersistentRequestBudget(
        config.state_dir / "api_request_total.json",
        total_cap=config.total_request_cap,
        turn_limit=14,
    )
    # Each Streamlit session gets its own API clients; only the locked request
    # counter is shared across sessions and process restarts.
    answer_client = BudgetedClient(_create_client(config.answer_api), request_budget)
    author_client = BudgetedClient(_create_client(config.quiz_api), request_budget)
    concept_config = ConceptCheckConfig(enabled=concept_check, min_topic_support=0.5)
    replayer = EventReplayer(static_profile, assets.topic_registry, concept_config)
    resolver = ChunkTopicResolver(assets.topic_map, assets.topic_registry, concept_config)
    event_dir = (
        config.state_dir
        / "sessions"
        / hashlib.sha256(static_profile.profile_id.encode("utf-8")).hexdigest()
    )
    event_store = JsonlEventStore(event_dir, replayer)
    concept_service = ConceptCheckService(
        config=concept_config,
        resolver=resolver,
        provider=FixtureQuestionProvider(()),
        event_store=event_store,
        replayer=replayer,
    )
    retriever = build_online_hybrid_retriever(assets, config)
    answer_generator = V2AnswerGenerator(answer_client, max_retries=1)
    quiz_generator = OnlineQuizGenerator(
        author_client=author_client,
        corpus=assets.corpus,
        topic_registry=assets.topic_registry,
        profile_id=static_profile.profile_id,
        quiz_config=concept_config,
    )
    return LearningRuntime(
        config=config,
        assets=assets,
        static_profile=static_profile,
        concept_check=concept_check,
        retriever=retriever,
        answer_generator=answer_generator,
        quiz_generator=quiz_generator,
        request_budget=request_budget,
        concept_service=concept_service,
        event_store=event_store,
        replayer=replayer,
    )


class LearningRuntime:
    """A single learner session; all secrets and quiz answers stay server-side."""

    def __init__(
        self,
        *,
        config: LearningConfig,
        assets: LearningAssets,
        static_profile: StudentProfile,
        concept_check: bool,
        retriever,
        answer_generator: V2AnswerGenerator,
        quiz_generator: OnlineQuizGenerator,
        request_budget: PersistentRequestBudget,
        concept_service: ConceptCheckService,
        event_store: JsonlEventStore,
        replayer: EventReplayer,
    ) -> None:
        self.config = config
        self.assets = assets
        self.static_profile = static_profile
        self.concept_check = concept_check
        self.retriever = retriever
        self.answer_generator = answer_generator
        self.quiz_generator = quiz_generator
        self.request_budget = request_budget
        self.concept_service = concept_service
        self.event_store = event_store
        self.replayer = replayer
        self.turns: dict[str, LearningTurn] = {}
        self.active_turn_id: str | None = None
        self._question_cache: dict[str, str] = {}
        self._lock = RLock()

    @property
    def learner_state(self) -> LearnerState:
        return self.replayer.replay(self.event_store.events(self.static_profile.profile_id))

    @property
    def request_usage(self) -> dict[str, int]:
        return self.request_budget.snapshot()

    @property
    def active_turn(self) -> LearningTurn | None:
        return self.turns.get(self.active_turn_id or "")

    def ask(self, question: str) -> LearningTurn:
        """Ask a free-form question; repeated identical calls return the same turn."""

        clean = " ".join(question.split())
        if not clean:
            raise ValueError("Enter a question.")
        if len(clean) > 4000:
            raise ValueError("Keep your question within 4,000 characters.")
        fingerprint = hashlib.sha256(clean.casefold().encode("utf-8")).hexdigest()
        with self._lock:
            existing_id = self._question_cache.get(fingerprint)
            if existing_id is not None and existing_id == self.active_turn_id:
                return self.turns[existing_id]
            if existing_id is not None:
                self._question_cache.pop(fingerprint, None)
            self._expire_offered_questions()
            turn = LearningTurn(turn_id=f"turn-{uuid.uuid4().hex}", question=clean)
            self.turns[turn.turn_id] = turn
            self.active_turn_id = turn.turn_id
            self._question_cache[fingerprint] = turn.turn_id
            started_retrieval = time.perf_counter()
            try:
                with self.request_budget.operation(
                    turn_id=turn.turn_id,
                    operation_id=f"answer:{turn.turn_id}",
                    max_requests=2,
                ):
                    legacy_result = self.retriever.retrieve(clean, self.config.candidate_k)
                    turn.retrieval = restore_v2_retrieval_result(
                        legacy_result, self.assets, self.config
                    )
                    turn.retrieval_ms = (time.perf_counter() - started_retrieval) * 1000

                    if self.concept_check:
                        turn.prepared = self.concept_service.prepare(
                            turn.retrieval, self.static_profile
                        )
                    else:
                        snapshot = build_learner_context_snapshot(
                            self.static_profile, enabled=False
                        )
                        turn.prepared = PreparedRound(snapshot=snapshot, retrieval_topic=None)
                    turn.snapshot = turn.prepared.snapshot
                    turn.retrieval_topic = turn.prepared.retrieval_topic

                    reranked, trace = rerank_retrieval(
                        turn.retrieval,
                        turn.snapshot.profile,
                        self.assets.role_package.labels,
                        self.assets.lambda_selection.lambda_weight,
                        parameter_source="dev",
                        taxonomy_status="fixture",
                        taxonomy_version=self.assets.role_package.manifest.role_taxonomy_version,
                    )
                    selected = tuple(
                        hit.model_copy(update={"rank": rank})
                        for rank, hit in enumerate(reranked.hits[: self.config.evidence_k], 1)
                    )
                    turn.reranked_retrieval = reranked.model_copy(update={"hits": selected})
                    turn.rerank_trace = trace
                    turn.evidence = EvidenceBundleAdapter().build(turn.reranked_retrieval)
                    generation_started = time.perf_counter()
                    answer = self.answer_generator.generate(clean, turn.snapshot, turn.evidence)
                    turn.answer = answer
                    turn.answer_trace = self.answer_generator.last_trace
                    turn.validated_answer = CitationValidatorAdapter().validate(
                        answer, turn.evidence
                    )
                    turn.generation_ms = (time.perf_counter() - generation_started) * 1000
                    turn.status = "answered"
                    trace_usage = getattr(turn.answer_trace, "usage", None)
                    if trace_usage is not None:
                        turn.input_tokens += int(trace_usage.input_tokens)
                        turn.output_tokens += int(trace_usage.output_tokens)
            except Exception as exc:
                turn.status = "failed"
                turn.error = self._safe_error(exc)
                if turn.retrieval is None:
                    turn.retrieval_ms = (time.perf_counter() - started_retrieval) * 1000
                turn.answer_trace = self.answer_generator.last_trace
                if turn.generation_ms == 0 and turn.retrieval is not None:
                    turn.generation_ms = max(
                        0.0, (time.perf_counter() - started_retrieval) * 1000 - turn.retrieval_ms
                    )
            finally:
                turn.api_requests = self.request_budget.turn_usage(turn.turn_id)
            return turn

    def ask_again(self, question: str) -> LearningTurn:
        """Explicitly start a fresh request for a previously asked exact question."""

        clean = " ".join(question.split())
        if not clean or len(clean) > 4000:
            raise ValueError("Enter a question between 1 and 4,000 characters long.")
        fingerprint = hashlib.sha256(clean.casefold().encode("utf-8")).hexdigest()
        with self._lock:
            self._question_cache.pop(fingerprint, None)
        return self.ask(clean)

    def make_quiz(self, turn_id: str, quiz_index: int) -> OnlineQuizView:
        """Create one draft question, idempotent for (turn_id, quiz_index)."""

        with self._lock:
            turn = self._get_turn(turn_id)
            existing = turn.quizzes.get(quiz_index)
            if existing is not None:
                return existing
            if not self.concept_check:
                return self._save_unavailable(
                    turn, quiz_index, "Concept Check is disabled for this session."
                )
            if turn.status != "answered" or turn.validated_answer is None:
                return self._save_unavailable(
                    turn, quiz_index, "Complete an answer before generating a quiz."
                )
            if not 1 <= quiz_index <= 3:
                raise ValueError("You can request at most three quizzes for each answer.")
            if self.active_turn_id != turn_id:
                return self._save_unavailable(
                    turn,
                    quiz_index,
                    "This answer has expired. Ask a new question to continue.",
                )
            if quiz_index != max(turn.quizzes, default=0) + 1:
                raise ValueError("Quiz attempts must be requested in order.")
            previous = turn.quizzes.get(quiz_index - 1)
            if previous is not None and previous.status in {"pending", "offered"}:
                raise ValueError("Submit or skip the previous quiz before requesting another.")

            turn.quizzes[quiz_index] = OnlineQuizView(
                turn_id=turn_id,
                quiz_index=quiz_index,
                status="pending",
                notice="Generating a quiz and locating its textbook evidence.",
            )
            quiz_started = False
            resolved_topic_id: str | None = None
            candidate_topic_ids: tuple[str, ...] = ()
            topic_selection_trace: TopicSelectionTrace | None = None
            generation_basis = "topic"
            try:
                with self.request_budget.operation(
                    turn_id=turn_id,
                    operation_id=f"quiz:{turn_id}:{quiz_index}",
                    max_requests=2,
                ):
                    if turn.validated_answer.abstained:
                        raise OnlineQuizUnavailable(
                            "The answer was withheld, so a quiz cannot be generated."
                        )
                    if turn.validated_answer.citation_status != "passed":
                        raise OnlineQuizUnavailable(
                            "The answer citations did not pass validation, so a quiz cannot be "
                            "generated."
                        )
                    retrieval = turn.reranked_retrieval
                    if retrieval is None:
                        raise OnlineQuizUnavailable(
                            "Ranked retrieval evidence is unavailable, so no quiz was generated."
                        )
                    resolution = self.concept_service.resolver.resolve_cited_topic(
                        retrieval, turn.validated_answer
                    )
                    topic_map = self.assets.topic_map.topic_map
                    assignments = (
                        {item.chunk_id: item.topic_ids for item in topic_map.assignments}
                        if topic_map is not None
                        else {}
                    )
                    resolution_has_support = (
                        resolution.status is TopicResolutionStatus.RESOLVED
                        or resolution.error_code in {"TOPIC_TIE", "TOPIC_SUPPORT_BELOW_THRESHOLD"}
                    )
                    topic_selection_trace = select_cited_demo_topic(
                        profile_id=self.static_profile.profile_id,
                        turn_id=turn_id,
                        quiz_index=quiz_index,
                        cited_chunk_ids=turn.validated_answer.resolved_citations,
                        ranked_hits=retrieval.hits,
                        topic_assignments=assignments,
                        rank_weighted_support=resolution.topic_support,
                        approved_topic_ids=(
                            tuple(t.topic_id for t in self.assets.topic_registry.topics)
                            if "*" in self.config.demo_topic_ids
                            else self.config.demo_topic_ids
                        ),
                        resolver_status=resolution.status.value,
                        resolver_error_code=resolution.error_code,
                        allow_selection=resolution_has_support,
                    )
                    self._append_topic_selection_audit(topic_selection_trace)
                    candidate_topic_ids = tuple(
                        candidate.topic_id for candidate in topic_selection_trace.candidates
                    )
                    resolved_topic_id = topic_selection_trace.selected_topic_id
                    turn.quizzes[quiz_index] = turn.quizzes[quiz_index].model_copy(
                        update={
                            "topic_id": resolved_topic_id,
                            "candidate_topic_ids": candidate_topic_ids,
                            "topic_selection_trace": topic_selection_trace,
                        }
                    )
                    if resolved_topic_id is None:
                        # Missing labels may use cited text; identity/binding failures may not.
                        if (
                            not resolution_has_support
                            and resolution.error_code != "NO_TOPIC_AVAILABLE"
                        ):
                            raise OnlineQuizUnavailable(
                                "Textbook evidence cannot be used: "
                                f"{resolution.error_code or 'unknown'}"
                            )
                        cited_chunk_ids = tuple(turn.validated_answer.resolved_citations)
                        retrieved_ids = {hit.chunk_id for hit in retrieval.hits}
                        if not cited_chunk_ids or any(
                            chunk_id not in retrieved_ids
                            or chunk_id not in self.assets.corpus.chunks_by_id
                            for chunk_id in cited_chunk_ids
                        ):
                            raise OnlineQuizUnavailable(
                                "No valid cited textbook passages are available."
                            )
                        topic = None
                        generation_basis = "textbook"
                        target_level = self.static_profile.level
                    else:
                        selected_candidate = next(
                            candidate
                            for candidate in topic_selection_trace.candidates
                            if candidate.topic_id == resolved_topic_id and candidate.eligible
                        )
                        cited_chunk_ids = selected_candidate.sufficient_evidence_chunk_ids
                        topic = next(
                            item
                            for item in self.assets.topic_registry.topics
                            if item.topic_id == resolved_topic_id
                        )
                        state = self.learner_state
                        topic_state = state.topics.get(resolved_topic_id) or TopicState(
                            topic_id=resolved_topic_id,
                            level=self.static_profile.topic_levels.get(
                                resolved_topic_id, self.static_profile.level
                            ),
                        )
                        target_level = target_levels(topic_state, self.concept_service.config)[0]
                    quiz_started = True
                    draft = self.quiz_generator.generate(
                        turn,
                        quiz_index=quiz_index,
                        topic=topic,
                        target_level=target_level,
                        cited_chunk_ids=cited_chunk_ids,
                        topic_selection_trace=topic_selection_trace,
                    )
                turn.private_quizzes[quiz_index] = draft.record
                turn.quizzes[quiz_index] = self._public_view(draft, turn)
            except Exception as exc:
                detail = self._safe_error(exc)
                turn.quizzes[quiz_index] = OnlineQuizView(
                    turn_id=turn_id,
                    quiz_index=quiz_index,
                    status="unavailable",
                    topic_id=resolved_topic_id,
                    generation_basis=generation_basis,
                    candidate_topic_ids=candidate_topic_ids,
                    topic_selection_trace=topic_selection_trace,
                    notice=detail,
                )
            finally:
                if quiz_started:
                    turn.input_tokens += self.quiz_generator.last_input_tokens
                    turn.output_tokens += self.quiz_generator.last_output_tokens
                turn.api_requests = self.request_budget.turn_usage(turn_id)
            return turn.quizzes[quiz_index]

    def submit(self, turn_id: str, practice_id: str, choice: str | None) -> PracticeResult:
        """Score a private server-side candidate and append one idempotent event."""

        with self._lock:
            turn = self._get_turn(turn_id)
            record = next(
                (item for item in turn.private_quizzes.values() if item.practice_id == practice_id),
                None,
            )
            if record is None:
                raise ValueError("The quiz does not exist or does not belong to this session.")
            if self.active_turn_id != turn_id or record.status in {"expired", "interrupted"}:
                raise ValueError(
                    "This quiz has expired. Generate a new quiz from the latest answer."
                )
            if choice not in {None, "A", "B", "C", "D"}:
                raise ValueError("Choose A, B, C, or D, or skip the question.")
            if record.grade is not None:
                if record.selected_choice != choice:
                    raise ValueError(
                        "This question was already submitted with a different answer and cannot "
                        "be changed."
                    )
                return turn.practice_results[practice_id]

            state_before = self.learner_state
            previous = state_before.topics.get(record.topic_id)
            level_before = (
                previous.level
                if previous
                else self.static_profile.topic_levels.get(
                    record.topic_id, self.static_profile.level
                )
            )
            grade = DeterministicGrader().grade(
                record.question,
                attempt_id=record.attempt_id,
                selected_choice=choice,
            )
            if record.topic_id is None:
                # Textbook-only attempts belong to the session, never to a registry Topic.
                path = self.event_store.directory / "textbook_practice_attempts.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "practice_id": practice_id,
                    "profile_id": self.static_profile.profile_id,
                    "turn_id": turn_id,
                    "topic_id": None,
                    "generation_basis": "textbook",
                    "created_at_utc": datetime.now(UTC).isoformat(),
                    "evidence_chunk_ids": record.evidence_chunk_ids,
                    "grade": grade.model_dump(mode="json"),
                }
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(payload) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                learner_state = state_before
            else:
                learner_state = self._record_topic_attempt(record, grade)
            after = learner_state.topics.get(record.topic_id)
            level_after = after.level if after else level_before
            result = PracticeResult(
                grade=grade,
                learner_state=learner_state,
                correct_answer=record.question.correct_answer,
                explanation=record.question.rationale,
                topic_id=record.topic_id,
                level_before=level_before,
                level_after=level_after,
            )
            record.status = "skipped" if choice is None else "submitted"
            record.selected_choice = choice
            record.grade = grade
            turn.practice_results[practice_id] = result
            view = turn.quizzes[record.quiz_index]
            turn.quizzes[record.quiz_index] = view.model_copy(
                update={
                    "status": "submitted",
                    "notice": (
                        "Response recorded. Answer and explanation come from textbook evidence; "
                        "no independent model review was performed."
                    ),
                }
            )
            return result

    def _record_topic_attempt(self, record, grade) -> LearnerState:
        event = ConceptCheckEvent(
            event_id=record.event_id,
            profile_id=self.static_profile.profile_id,
            attempt_id=record.attempt_id,
            question_id=record.question.question_id,
            topic_id=record.topic_id,
            topic_registry_version=self.assets.topic_registry.topic_registry_version,
            question_difficulty=record.question.difficulty,
            selected_choice=grade.selected_choice,
            performance=grade.performance,
            event_type=(
                ConceptCheckEventType.ATTEMPT_SKIPPED
                if grade.result is ConceptCheckResult.SKIPPED
                else ConceptCheckEventType.ATTEMPT_SUBMITTED
            ),
            state_version_before=0,
            stream_version=1,
            created_at=datetime.now(UTC),
        )
        stored = self.event_store.append(event)
        return self.replayer.replay(self.event_store.events(stored.profile_id))

    def override_level(
        self,
        topic_id: str,
        level: StudentLevel,
        reason: str,
        *,
        event_id: str | None = None,
    ) -> LearnerState:
        if not self.concept_check:
            raise ValueError("Adaptive Concept Check is disabled for this session.")
        if not reason.strip():
            raise ValueError("Enter a reason for the manual level adjustment.")
        turn = self.active_turn
        allowed = set(self.learner_state.topics)
        if turn:
            allowed.update(view.topic_id for view in turn.quizzes.values() if view.topic_id)
            topic = turn.retrieval_topic
            if topic and topic.status is TopicResolutionStatus.RESOLVED and topic.topic_id:
                allowed.add(topic.topic_id)
        if topic_id not in allowed:
            raise ValueError("Select a Concept Check, retrieval or previously practiced Topic.")
        return self.concept_service.override_level(
            topic_id,
            level,
            reason=reason.strip(),
            event_id=event_id or f"override-{uuid.uuid4().hex}",
        )

    def revoke_latest_attempt(self, *, event_id: str | None = None) -> LearnerState:
        events = self.event_store.events(self.static_profile.profile_id)
        revoked = {
            item.revoked_attempt_id
            for item in events
            if item.event_type is ConceptCheckEventType.ATTEMPT_REVOKED
        }
        latest = next(
            (
                item
                for item in reversed(events)
                if item.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED
                and item.attempt_id not in revoked
            ),
            None,
        )
        if latest is None or latest.attempt_id is None:
            raise ValueError("There is no graded answer to undo.")
        return self.concept_service.revoke(
            latest.attempt_id,
            event_id=event_id or f"revoke-{uuid.uuid4().hex}",
        )

    def compare_static_levels(self, turn_id: str, other_level: StudentLevel) -> dict[str, str]:
        """Show two static-profile prompts against the same saved evidence."""

        with self._lock:
            turn = self._get_turn(turn_id)
            if turn.comparison_done:
                return turn.comparison
            if turn.status != "answered" or turn.evidence is None:
                raise ValueError("Complete an answer before comparing learner levels.")
            if other_level is self.static_profile.level:
                raise ValueError("Choose a learner level different from the starting level.")
            comparison_turn_id = f"compare:{turn_id}"
            results: dict[str, str] = {}
            try:
                with self.request_budget.operation(
                    turn_id=comparison_turn_id,
                    operation_id=f"comparison:{turn_id}",
                    max_requests=2,
                ):
                    for level in (self.static_profile.level, other_level):
                        profile = self.static_profile.model_copy(
                            update={"level": level, "topic_levels": {}}
                        )
                        snapshot = build_learner_context_snapshot(profile, enabled=False)
                        answer = V2AnswerGenerator(
                            self.answer_generator.client, max_retries=1
                        ).generate(turn.question, snapshot, turn.evidence)
                        validated = CitationValidatorAdapter().validate(answer, turn.evidence)
                        results[level.value] = validated.answer.explanation
                self.request_budget.turn_usage(comparison_turn_id)
            except Exception as exc:
                results["error"] = self._safe_error(exc)
            turn.comparison = results
            turn.comparison_done = True
            return results

    def _expire_offered_questions(self) -> None:
        for turn in self.turns.values():
            for index, view in tuple(turn.quizzes.items()):
                record = turn.private_quizzes.get(index)
                if view.status in {"pending", "offered"}:
                    if record is not None:
                        record.status = "expired"
                    turn.quizzes[index] = view.model_copy(
                        update={
                            "status": "expired",
                            "notice": (
                                "A new question has started. This quiz can no longer be submitted."
                            ),
                        }
                    )

    def _public_view(self, draft: DraftQuiz, turn: LearningTurn) -> OnlineQuizView:
        question = draft.record.question
        labels = []
        for chunk_id in draft.record.evidence_chunk_ids:
            chunk = self.assets.corpus.chunks_by_id[chunk_id]
            label = chunk.source_name
            if chunk.page_or_location:
                label += f" · {chunk.page_or_location}"
            labels.append(label)
        return OnlineQuizView(
            turn_id=turn.turn_id,
            quiz_index=draft.record.quiz_index,
            practice_id=draft.record.practice_id,
            status="offered",
            topic_id=draft.record.topic_id,
            generation_basis="topic" if draft.record.topic_id else "textbook",
            difficulty=question.difficulty,
            question=question.question,
            options=question.options,
            topic_selection_trace=draft.record.topic_selection_trace,
            notice=(
                "Generated from textbook evidence; no independent model review."
                if draft.record.topic_id
                else "No mapped Topic was available. Generated directly from the answer's cited "
                "textbook passages; this practice does not update Topic mastery or level."
            ),
            evidence_labels=tuple(labels),
        )

    def _append_topic_selection_audit(self, trace: TopicSelectionTrace) -> None:
        """Persist every Topic decision before making author or verifier API calls."""

        path = self.event_store.directory / "topic_selection_audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(trace.model_dump_json() + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _save_unavailable(self, turn: LearningTurn, quiz_index: int, notice: str) -> OnlineQuizView:
        view = OnlineQuizView(
            turn_id=turn.turn_id,
            quiz_index=quiz_index,
            status="unavailable",
            notice=notice,
        )
        turn.quizzes[quiz_index] = view
        return view

    def _get_turn(self, turn_id: str) -> LearningTurn:
        try:
            return self.turns[turn_id]
        except KeyError as exc:
            raise ValueError(
                "This conversation has expired. Ask a new question to continue."
            ) from exc

    def _safe_error(self, error: Exception) -> str:
        message = str(error)
        for role in (self.config.answer_api, self.config.quiz_api, self.config.verify_api):
            secret = os.environ.get(role.api_key_env, "")
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return message[:500] or type(error).__name__
