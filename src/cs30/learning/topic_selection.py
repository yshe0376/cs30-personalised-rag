"""Auditable Topic selection policy for the online learning Demo only.

This policy does not change the M7 reranking or experiment logic. It uses the
existing citation resolver's rank-weighted support, then requires at least one
validated cited chunk assigned to the Topic before it can be selected.
"""

from __future__ import annotations

import math
import random
import secrets
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from cs30.v2.contracts import RetrievedEvidence

from .models import CitedTopicEvidence, TopicSelectionCandidate, TopicSelectionTrace

POLICY_VERSION = "online-demo-cited-topic-weighted-v2"
POLICY_VALIDATION_STATUS = "demo-only-not-m7-validated"
MINIMUM_EVIDENCE_RULE = (
    "A candidate needs at least one citation-validated cited chunk assigned to that Topic; "
    "chunks may support multiple Topics."
)
SUPPORT_DEFINITION = (
    "Existing citation-resolver support: normalized rank-weighted sum of "
    "1 / (cited evidence rank * number of assigned Topic IDs). This is distinct from the "
    "M6 Dense/BM25 retrieval weights and the M7 reranking lambda."
)
RNG_ALGORITHM = (
    "Python random.Random(seed).random() multiplied by the sum of eligible supports, "
    "then cumulative selection in ascending Topic ID order."
)


def select_cited_demo_topic(
    *,
    profile_id: str,
    turn_id: str,
    quiz_index: int,
    cited_chunk_ids: tuple[str, ...],
    ranked_hits: Sequence[RetrievedEvidence],
    topic_assignments: Mapping[str, Sequence[str]],
    rank_weighted_support: Mapping[str, float],
    approved_topic_ids: tuple[str, ...],
    resolver_status: str,
    resolver_error_code: str | None,
    allow_selection: bool,
    rng_seed: int | None = None,
) -> TopicSelectionTrace:
    """Choose an approved Topic only from citation-backed, sufficient evidence.

    The resolver's support map is retained even when its single-winner result is
    tied or below 0.5. The online Demo does not use that threshold as a gate:
    candidate eligibility instead requires direct cited evidence assigned to the Topic.
    Multiple eligible candidates are drawn
    proportionally to their resolver support. The random seed and draw are part
    of the returned trace so the decision can be replayed and audited.
    """

    seed = secrets.randbits(64) if rng_seed is None else int(rng_seed)
    approved = set(approved_topic_ids)
    cited_ids = set(cited_chunk_ids)
    hits_by_id = {hit.chunk_id: hit for hit in ranked_hits if hit.chunk_id in cited_ids}
    evidence: list[CitedTopicEvidence] = []
    for chunk_id in cited_chunk_ids:
        hit = hits_by_id.get(chunk_id)
        assignment = tuple(topic_assignments.get(chunk_id, ()))
        evidence.append(
            CitedTopicEvidence(
                chunk_id=chunk_id,
                rank=hit.rank if hit is not None else None,
                topic_ids=assignment,
                approved_topic_ids=tuple(sorted(set(assignment) & approved)),
            )
        )

    candidate_ids = sorted(
        {
            topic_id
            for item in evidence
            for topic_id in item.topic_ids
            if topic_id in approved
        }
    )
    candidates: list[TopicSelectionCandidate] = []
    for topic_id in candidate_ids:
        cited_for_topic = tuple(item.chunk_id for item in evidence if topic_id in item.topic_ids)
        sufficient_for_topic = tuple(
            item.chunk_id
            for item in evidence
            if topic_id in item.approved_topic_ids
        )
        support = float(rank_weighted_support.get(topic_id, 0.0))
        evidence_sufficient = bool(sufficient_for_topic)
        eligible = allow_selection and evidence_sufficient and support > 0.0
        candidates.append(
            TopicSelectionCandidate(
                topic_id=topic_id,
                rank_weighted_support=support,
                cited_chunk_ids=cited_for_topic,
                sufficient_evidence_chunk_ids=sufficient_for_topic,
                evidence_sufficient=evidence_sufficient,
                eligible=eligible,
            )
        )

    eligible = [candidate for candidate in candidates if candidate.eligible]
    selected_topic_id: str | None = None
    selection_method: str = "none"
    rng_draw: float | None = None
    failure_reason: str | None = None
    if not allow_selection:
        failure_reason = (
            "The cited passages have no mapped Topic."
            if resolver_error_code == "NO_TOPIC_AVAILABLE" else
            "Topic selection is unavailable: " + (resolver_error_code or resolver_status)
        )
    elif not candidates:
        failure_reason = (
            "No in-scope Topic is mapped to the validated citations."
        )
    elif not eligible:
        failure_reason = (
            "No cited Topic has positive support and valid mapped textbook evidence."
        )
    elif len(eligible) == 1:
        selected_topic_id = eligible[0].topic_id
        selection_method = "single_candidate"
    else:
        total_support = math.fsum(candidate.rank_weighted_support for candidate in eligible)
        if total_support <= 0.0 or not math.isfinite(total_support):
            failure_reason = (
                "Eligible Topics have no positive finite rank-weighted support; "
                "no quiz was generated."
            )
        else:
            rng_draw = random.Random(seed).random() * total_support
            cumulative = 0.0
            for candidate in eligible:
                cumulative += candidate.rank_weighted_support
                if rng_draw < cumulative:
                    selected_topic_id = candidate.topic_id
                    break
            if selected_topic_id is None:
                # Protect against floating-point accumulation at the final edge.
                selected_topic_id = eligible[-1].topic_id
            selection_method = "weighted_random"

    return TopicSelectionTrace(
        policy_version=POLICY_VERSION,
        policy_validation_status=POLICY_VALIDATION_STATUS,
        audit_id=f"topic-selection:{turn_id}:{quiz_index}",
        profile_id=profile_id,
        turn_id=turn_id,
        quiz_index=quiz_index,
        created_at_utc=datetime.now(UTC),
        rng_seed=seed,
        rng_algorithm=RNG_ALGORITHM,
        rng_draw=rng_draw,
        support_definition=SUPPORT_DEFINITION,
        minimum_evidence_rule=MINIMUM_EVIDENCE_RULE,
        approved_topic_ids=tuple(sorted(approved)),
        resolver_status=resolver_status,
        resolver_error_code=resolver_error_code,
        cited_evidence=tuple(evidence),
        candidates=tuple(candidates),
        selection_method=selection_method,
        selected_topic_id=selected_topic_id,
        failure_reason=failure_reason,
    )
