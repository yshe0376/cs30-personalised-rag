"""Frozen V2 four-condition generation experiments with native evidence.

These are development experiments. A successful batch never promotes draft
Gold, incomplete Role annotations, or machine assessments to formal results.
"""

from __future__ import annotations

import json
import math
import tempfile
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cs30.contracts import EvidenceBundle as LegacyBundle
from cs30.contracts import EvidenceItem as LegacyItem
from cs30.contracts import IndexArtifact as LegacyArtifact
from cs30.contracts import StudentProfile as LegacyProfile
from cs30.evaluation.open_answer_models import ExpectedAnswer
from cs30.generation.client import LLMClient
from cs30.generation.conditions import GenerationCondition
from cs30.generation.exceptions import (
    LLMCacheIntegrityError,
    LLMRequestBudgetExceeded,
    LLMRetryLater,
)
from cs30.generation.lambda_search import load_role_label_package
from cs30.generation.reranking import LevelAwareReranker, RerankConfig, RoleLabel
from cs30.retrieval.real import BM25Retriever
from cs30.v2.contracts import (
    EvidenceProvenance,
    GoldQuestion,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
    StudentLevel,
    StudentProfile,
)
from cs30.v2.corpus import LoadedCorpus, load_corpus_records
from cs30.v2.evidence import EvidenceBundleAdapter
from cs30.v2.experiment_checkpoint import atomic_json, load_cells, save_cell, writer_lock
from cs30.v2.experiment_gold import bind_questions
from cs30.v2.experiment_models import GenerationExperiment, GenerationRun
from cs30.v2.generation import V2AnswerGenerator, V2BatchResult, V2GenerationFailure
from cs30.v2.io import canonical_hash, read_jsonl, sha256_bytes, unique_models


class ExperimentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExperimentConfig(ExperimentModel):
    schema_version: Literal["0.1"] = "0.1"
    generator_model: str = Field(min_length=1)
    split: Literal["dev", "test"] = "dev"
    levels: tuple[StudentLevel, ...] = tuple(StudentLevel)
    candidate_k: int = Field(default=20, ge=1)
    evidence_k: int = Field(default=5, ge=1)
    lambda_weight: float = Field(default=0.35, ge=0, le=1, allow_inf_nan=False)
    profile_confidence: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    max_retries: int = Field(default=1, ge=0, le=3)
    allow_missing_roles: bool = False
    lambda_policy: Literal["fixed_exploratory", "dev_selected"] = "fixed_exploratory"

    @model_validator(mode="after")
    def validate_config(self) -> ExperimentConfig:
        if not self.generator_model.strip():
            raise ValueError("generator model must not be blank")
        if not self.levels or len(set(self.levels)) != len(self.levels):
            raise ValueError("levels must be nonempty and unique")
        if self.evidence_k > self.candidate_k:
            raise ValueError("evidence_k cannot exceed candidate_k")
        return self


class FrozenRetrieval(ExperimentModel):
    question_id: str = Field(min_length=1)
    retrieval: RetrievalResult


class LambdaSelection(ExperimentModel):
    schema_version: Literal["0.2"] = "0.2"
    reportable: Literal[False] = False
    selected_on_split: Literal["dev"] = "dev"
    lambda_weight: float = Field(ge=0, le=1, allow_inf_nan=False)
    candidate_lambdas: list[float]
    gold_sha256: str
    corpus_hash: str
    manifest_hash: str
    role_labels_sha256: str
    profile_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    candidate_k: int = Field(ge=1)
    evidence_k: int = Field(ge=1)
    source_prepared_sha256: str
    source_retrieval_sha256: str | None = None
    objective: Literal["largest_positive_lambda_within_1pt_of_baseline"]
    noninferiority_margin: Literal[0.01] = 0.01
    metrics: list[dict]

    @model_validator(mode="after")
    def validate_grid(self) -> LambdaSelection:
        if (
            not self.candidate_lambdas
            or 0 not in self.candidate_lambdas
            or self.lambda_weight <= 0
            or self.lambda_weight not in self.candidate_lambdas
            or any(not math.isfinite(v) or not 0 <= v <= 1 for v in self.candidate_lambdas)
        ):
            raise ValueError(
                "Dev selection requires a finite grid, zero baseline and positive selected member"
            )
        return self


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def jsonl_bytes(values) -> bytes:
    return "".join(value.model_dump_json() + "\n" for value in values).encode("utf-8")


def load_v2_gold(path: Path, data: bytes | None = None) -> dict[str, GoldQuestion]:
    rows = read_jsonl(path, data)
    if not rows or any(row.get("schema_version") != "2.0" for row in rows):
        raise ValueError("V2 experiments require nonempty native schema_version=2.0 Gold")
    return unique_models(rows, GoldQuestion, "question_id")


def retrieve_bm25(
    corpus: LoadedCorpus, gold: Mapping[str, GoldQuestion], candidate_k: int
) -> list[FrozenRetrieval]:
    """Reuse the production BM25 implementation, restoring full V2 identities."""
    config = {
        "backend": "cs30.retrieval.real.BM25Retriever",
        "k1": 1.5,
        "b": 0.75,
        "stopwords": "project-default",
        "candidate_k": candidate_k,
    }
    manifest = corpus.manifest
    with tempfile.TemporaryDirectory(prefix="cs30-v2-bm25-") as temporary:
        root = Path(temporary)
        chunks_path = root / "chunks.json"
        write_json(
            chunks_path,
            [
                {
                    "position": i,
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "chapter_id": c.chapter_id,
                    "source": c.source_name,
                }
                for i, c in enumerate(corpus.chunks)
            ],
        )
        artifact = LegacyArtifact(
            artifact_id="v2-bm25-" + manifest.corpus_hash.removeprefix("sha256:")[:16],
            index_type="bm25",
            location=str(root),
            chunk_count=len(corpus.chunks),
            metadata={
                "chunk_map": str(chunks_path),
                "chunk_map_sha256": sha256_bytes(chunks_path.read_bytes()),
                "corpus_hash": manifest.corpus_hash,
                "chunk_config_hash": manifest.chunk_config_hash,
                "index_version": "v2-bm25-1",
            },
        )
        backend = BM25Retriever(cache_size=0)
        backend.load_index(artifact)
        provenance = EvidenceProvenance(
            corpus_version=manifest.corpus_version,
            corpus_hash=manifest.corpus_hash,
            manifest_hash=manifest.manifest_hash,
            chunk_config_hash=manifest.chunk_config_hash,
            index_version="v2-bm25-1",
            retrieval_mode=RetrievalMode.BM25,
            retrieval_config_hash=canonical_hash(config),
        )
        results = []
        for question in gold.values():
            result = backend.retrieve(question.question, candidate_k)
            hits = []
            for hit in result.hits:
                chunk = corpus.chunks_by_id[hit.chunk_id]
                fields = {
                    name: getattr(chunk, name)
                    for name in (
                        "provider",
                        "textbook_id",
                        "document_id",
                        "chunk_id",
                        "chapter_id",
                        "source_name",
                        "page_or_location",
                        "source_locator",
                        "text",
                    )
                }
                hits.append(
                    RetrievedEvidence(
                        **fields,
                        score=hit.score,
                        rank=hit.rank,
                        retriever_type=RetrievalMode.BM25,
                    )
                )
            results.append(
                FrozenRetrieval(
                    question_id=question.question_id,
                    retrieval=RetrievalResult(
                        query=question.question,
                        mode=RetrievalMode.BM25,
                        hits=tuple(hits),
                        provenance=provenance,
                    ),
                )
            )
    return results


def _validate_retrieval(
    corpus: LoadedCorpus, question: GoldQuestion, result: RetrievalResult, candidate_k: int
) -> None:
    manifest = corpus.manifest
    if result.query != question.question:
        raise ValueError("retrieval query must be the Gold question stem")
    if result.mode is RetrievalMode.FIXTURE or result.provenance is None:
        raise ValueError("V2 batch requires real retrieval provenance")
    provenance = result.provenance
    for name in ("corpus_version", "corpus_hash", "manifest_hash", "chunk_config_hash"):
        if getattr(provenance, name) != getattr(manifest, name):
            raise ValueError(f"retrieval {name} differs from corpus")
    if provenance.retrieval_mode != result.mode or len(result.hits) > candidate_k:
        raise ValueError("retrieval mode or candidate count differs from experiment")
    for hit in result.hits:
        if not math.isfinite(hit.score):
            raise ValueError("retrieval scores must be finite")
        chunk = corpus.chunks_by_id.get(hit.chunk_id)
        if chunk is None or any(
            getattr(hit, field) != getattr(chunk, field)
            for field in (
                "provider",
                "textbook_id",
                "document_id",
                "chapter_id",
                "source_name",
                "page_or_location",
                "source_locator",
                "text",
            )
        ):
            raise ValueError("retrieved evidence differs from the published V2 chunk")


def prepare_experiment(
    *,
    corpus_dir: Path,
    gold_path: Path,
    output_dir: Path,
    config: ExperimentConfig,
    role_manifest: Path | None = None,
    retrieval_path: Path | None = None,
    question_limit: int | None = None,
    question_ids_path: Path | None = None,
    selected_lambda_path: Path | None = None,
    conversion_manifest_path: Path | None = None,
) -> dict:
    if output_dir.exists():
        raise ValueError("output directory already exists")
    if question_limit is not None and (question_limit < 1 or config.split != "dev"):
        raise ValueError("question_limit is positive and Dev-only")
    corpus = load_corpus_records(corpus_dir)
    gold_bytes = gold_path.read_bytes()
    conversion = None
    if conversion_manifest_path:
        conversion = json.loads(conversion_manifest_path.read_bytes())
        if conversion.get("result_type") != "explicit_m3_to_v2_gold_conversion" or conversion.get(
            "output_gold_sha256"
        ) != sha256_bytes(gold_bytes):
            raise ValueError("Gold conversion audit differs from the supplied Gold bytes")
    all_gold = load_v2_gold(gold_path, gold_bytes)
    chosen = [q for q in all_gold.values() if q.split.value == config.split]
    question_ids_bytes = question_ids_path.read_bytes() if question_ids_path else None
    if question_ids_bytes is not None:
        ids = json.loads(question_ids_bytes)
        if (
            config.split != "dev"
            or question_limit is not None
            or not isinstance(ids, list)
            or not ids
            or not all(isinstance(key, str) for key in ids)
            or len(set(ids)) != len(ids)
            or not set(ids) <= {q.question_id for q in chosen}
        ):
            raise ValueError("question-ids must be unique known Dev IDs; cannot combine with limit")
        chosen = [all_gold[key] for key in ids]
    if question_limit:
        chosen = sorted(chosen, key=lambda q: q.question_id)[:question_limit]
    if not chosen:
        raise ValueError("Gold has no questions in the selected split")
    gold = {q.question_id: q for q in chosen}
    for question in gold.values():
        if question.corpus_version != corpus.manifest.corpus_version:
            raise ValueError("Gold corpus_version differs from V2 corpus")
        spans = [e.span for group in question.gold_core_evidence_sets for e in group]
        spans += [e.span for e in question.partial_evidence]
        for span in spans:
            if span.textbook_id not in corpus.manifest.included_textbook_ids:
                raise ValueError("Gold evidence refers to a textbook absent from corpus")
    bindings = bind_questions(gold, corpus)
    if retrieval_path:
        retrieval_bytes = retrieval_path.read_bytes()
        supplied = unique_models(
            read_jsonl(retrieval_path, retrieval_bytes), FrozenRetrieval, "question_id"
        )
        if not set(gold) <= set(supplied):
            raise ValueError("saved retrieval is missing selected questions")
        results = [supplied[key] for key in gold]
    else:
        retrieval_bytes = None
        results = retrieve_bm25(corpus, gold, config.candidate_k)
    for item in results:
        _validate_retrieval(corpus, gold[item.question_id], item.retrieval, config.candidate_k)
    candidate_ids = {hit.chunk_id for item in results for hit in item.retrieval.hits}
    labels: dict[str, RoleLabel] = {}
    role_provenance = None
    if role_manifest:
        package = load_role_label_package(role_manifest)
        if package.manifest.corpus_version != corpus.manifest.corpus_version:
            raise ValueError("Role-label corpus_version differs from V2 corpus")
        if package.manifest.reference_type != "chunk":
            raise ValueError("V2 reranking requires chunk Role labels")
        if set(package.labels) - corpus.chunks_by_id.keys():
            raise ValueError("Role labels contain chunk IDs outside the V2 corpus")
        labels = package.labels
        role_provenance = package.manifest.model_dump(mode="json")
    missing_roles = sorted(candidate_ids - labels.keys())
    if missing_roles and not config.allow_missing_roles:
        raise ValueError(
            f"{len(missing_roles)} candidate chunks lack Role labels; supply matching annotations "
            "or explicitly enable allow_missing_roles for development diagnostics"
        )
    selection = None
    if selected_lambda_path is not None:
        selection = LambdaSelection.model_validate_json(selected_lambda_path.read_bytes())
        if (
            config.lambda_policy != "dev_selected"
            or config.lambda_weight != selection.lambda_weight
            or config.profile_confidence != selection.profile_confidence
            or config.candidate_k != selection.candidate_k
            or config.evidence_k != selection.evidence_k
            or sha256_bytes(gold_bytes) != selection.gold_sha256
            or corpus.manifest.corpus_hash != selection.corpus_hash
            or corpus.manifest.manifest_hash != selection.manifest_hash
            or role_provenance is None
            or role_provenance["labels_sha256"] != selection.role_labels_sha256
            or missing_roles
            or selection.source_retrieval_sha256
            != (sha256_bytes(retrieval_bytes) if retrieval_bytes is not None else None)
        ):
            raise ValueError("selected Dev lambda differs from corpus, Gold, Roles or run settings")
    elif config.lambda_policy == "dev_selected":
        raise ValueError("dev_selected policy requires the saved Dev selection artifact")
    matrix = GenerationExperiment(
        matrix_version="m7-v2-four-condition-0.2",
        gold_sha256=sha256_bytes(gold_bytes),
        cases=[
            ExpectedAnswer(
                run_id="v2-"
                + canonical_hash(
                    [qid, level.value, condition.condition_id, config.generator_model]
                )[:24],
                question_id=qid,
                condition_id=condition.condition_id,
                student_level=level,
                generator_model=config.generator_model,
            )
            for qid in gold
            for level in config.levels
            for condition in GenerationCondition
        ],
    )
    label_rows = [
        {"chunk_id": key, "roles": [r.value for r in value.roles], "source": value.source}
        for key, value in sorted(labels.items())
        if key in candidate_ids
    ]
    payloads = {
        "gold.jsonl": gold_bytes,
        "retrieval.jsonl": jsonl_bytes(results),
        "config.json": (config.model_dump_json(indent=2) + "\n").encode(),
        "expected_experiment.json": (matrix.model_dump_json(indent=2) + "\n").encode(),
        "role_labels.json": (json.dumps(label_rows, sort_keys=True) + "\n").encode(),
        "corpus_manifest.json": (corpus.manifest.model_dump_json(indent=2) + "\n").encode(),
        "gold_bindings.jsonl": ("".join(json.dumps(row) + "\n" for row in bindings)).encode(),
        "lambda_selection.json": (
            json.dumps(selection.model_dump(mode="json") if selection else None) + "\n"
        ).encode(),
        "gold_conversion.json": (json.dumps(conversion) + "\n").encode(),
    }
    manifest = {
        "schema_version": "0.2",
        "result_type": "m7_v2_prepared_experiment",
        "reportable": False,
        "split": config.split,
        "question_count": len(gold),
        "expected_runs": len(matrix.cases),
        "selected_question_ids": list(gold),
        "input_sha256": {name: sha256_bytes(data) for name, data in payloads.items()},
        "source_retrieval_sha256": sha256_bytes(retrieval_bytes) if retrieval_bytes else None,
        "question_ids_sha256": sha256_bytes(question_ids_bytes) if question_ids_bytes else None,
        "role_provenance": role_provenance,
        "missing_role_chunk_ids": missing_roles,
        "candidate_unique_chunks": len(candidate_ids),
        "role_coverage_complete": not missing_roles,
        "lambda_source": config.lambda_policy,
        "profile_policy": "controlled_static_levels_with_explicit_confidence",
        "limitations": [
            "Development result; no formal Gold or Test approval inferred.",
            "Only a saved Dev selection artifact establishes Dev-selected lambda; "
            "no selection or tuning occurs on Test.",
            "Role gaps fall back to retrieval scores and prevent interpreting reranking effects.",
            "Citation IDs are checked structurally; semantic support and level adaptation need "
            "separate evaluation.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        (output_dir / name).write_bytes(data)
    write_json(output_dir / "input_manifest.json", manifest)
    return manifest


def load_prepared(
    directory: Path,
) -> tuple[dict, ExperimentConfig, GenerationExperiment, dict, dict, dict]:
    manifest = json.loads((directory / "input_manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("result_type") != "m7_v2_prepared_experiment"
        or manifest.get("schema_version") != "0.2"
        or manifest.get("reportable") is not False
    ):
        raise ValueError("unsupported prepared experiment manifest")
    required = {
        "gold.jsonl",
        "retrieval.jsonl",
        "config.json",
        "expected_experiment.json",
        "role_labels.json",
        "corpus_manifest.json",
        "gold_bindings.jsonl",
        "lambda_selection.json",
        "gold_conversion.json",
    }
    hashes = manifest.get("input_sha256", {})
    if set(hashes) != required:
        raise ValueError("prepared experiment must bind exactly its required input files")
    snapshots = {name: (directory / name).read_bytes() for name in required}
    if any(sha256_bytes(data) != hashes[name] for name, data in snapshots.items()):
        raise ValueError("prepared input changed after preparation")
    config = ExperimentConfig.model_validate_json(snapshots["config.json"])
    selection_data = json.loads(snapshots["lambda_selection.json"])
    if (selection_data is not None) != (config.lambda_policy == "dev_selected"):
        raise ValueError("prepared lambda policy differs from the selection artifact")
    if selection_data is not None:
        selection = LambdaSelection.model_validate(selection_data)
        if selection.lambda_weight != config.lambda_weight:
            raise ValueError("prepared lambda weight differs from the saved Dev selection")
    matrix = GenerationExperiment.model_validate_json(snapshots["expected_experiment.json"])
    if matrix.gold_sha256 != hashes["gold.jsonl"]:
        raise ValueError("matrix Gold hash differs from prepared inputs")
    gold = load_v2_gold(directory / "gold.jsonl", snapshots["gold.jsonl"])
    retrieval = unique_models(
        read_jsonl(directory / "retrieval.jsonl", snapshots["retrieval.jsonl"]),
        FrozenRetrieval,
        "question_id",
    )
    rows = json.loads(snapshots["role_labels.json"])
    labels = {}
    for row in rows:
        if row["chunk_id"] in labels:
            raise ValueError("duplicate frozen Role ID")
        labels[row["chunk_id"]] = RoleLabel(tuple(row["roles"]), source=row["source"])
    expected_cells = {
        (qid, level, condition.condition_id, config.generator_model)
        for qid in retrieval
        for level in config.levels
        for condition in GenerationCondition
    }
    actual_cells = {
        (c.question_id, c.student_level, c.condition_id, c.generator_model) for c in matrix.cases
    }
    if actual_cells != expected_cells or set(retrieval) - gold.keys():
        raise ValueError("prepared matrix is not the configured four-condition cross product")
    if (
        set(manifest["selected_question_ids"]) != set(retrieval)
        or manifest["question_count"] != len(retrieval)
        or manifest["expected_runs"] != len(matrix.cases)
        or manifest["split"] != config.split
    ):
        raise ValueError("prepared manifest summary differs from its matrix")
    candidates = {hit.chunk_id for item in retrieval.values() for hit in item.retrieval.hits}
    missing = sorted(candidates - labels.keys())
    if (
        missing != manifest["missing_role_chunk_ids"]
        or bool(missing) == manifest["role_coverage_complete"]
        or (missing and not config.allow_missing_roles)
    ):
        raise ValueError("prepared Role coverage differs from actual candidate labels")
    for qid, item in retrieval.items():
        if gold[qid].split.value != config.split or item.retrieval.query != gold[qid].question:
            raise ValueError("prepared split or query differs from Gold")
    return manifest, config, matrix, gold, retrieval, labels


def rerank_retrieval(
    result: RetrievalResult,
    profile: StudentProfile,
    labels: Mapping[str, RoleLabel],
    weight: float,
    *,
    parameter_source: Literal["fixture", "dev"] = "fixture",
    taxonomy_version: str = "unavailable-role-taxonomy",
) -> tuple[RetrievalResult, dict]:
    """Delegate M7's exact normalizer, Role preferences and stable ties to its runner."""
    bundle = EvidenceBundleAdapter().build(result)
    legacy = LegacyBundle(
        query=bundle.query,
        retrieval_mode=bundle.retrieval_mode.value,
        evidence_items=[
            LegacyItem(
                evidence_id=i.evidence_id,
                chunk_id=i.chunk_id,
                text=i.text,
                chapter_id=i.chapter_id,
                source=i.source_name,
                source_locator=i.source_locator,
                rank=i.rank,
                score=i.score,
                token_count=i.token_count,
            )
            for i in bundle.evidence_items
        ],
        citation_map=bundle.citation_map,
        token_count=bundle.token_count,
    )
    ranked = LevelAwareReranker(
        labels,
        config=RerankConfig(
            lambda_weight=weight,
            parameter_source=parameter_source,
            taxonomy_version=taxonomy_version,
        ),
    ).rerank(
        legacy,
        LegacyProfile(
            profile_id=profile.profile_id, level=profile.level.value, confidence=profile.confidence
        ),
    )
    by_id = {hit.chunk_id: hit for hit in result.hits}
    hits = tuple(
        by_id[i.chunk_id].model_copy(update={"rank": rank})
        for rank, i in enumerate(ranked.evidence.evidence_items, 1)
    )
    return result.model_copy(update={"hits": hits}), ranked.trace.model_dump()


def select_dev_lambda(prepared_dir: Path, candidates: list[float]) -> LambdaSelection:
    """Use complete OR-of-AND Gold evidence hits, never a union of partial spans."""
    manifest, config, matrix, gold, retrieval, labels = load_prepared(prepared_dir)
    if config.split != "dev":
        raise ValueError("lambda selection is Dev-only; Test tuning is forbidden")
    if not manifest["role_coverage_complete"] or manifest["role_provenance"] is None:
        raise ValueError("Dev lambda selection requires complete candidate Role coverage")
    grid = sorted(set(candidates))
    if not grid or 0.0 not in grid or any(not math.isfinite(v) or not 0 <= v <= 1 for v in grid):
        raise ValueError("lambda grid must be finite in [0,1] and include the zero baseline")
    bindings = read_jsonl(prepared_dir / "gold_bindings.jsonl")
    by_span = {
        (row["question_id"], row["binding"]["span_id"]): set(row["binding"]["chunk_ids"])
        for row in bindings
    }
    metrics = []
    for weight in grid:
        rows = []
        for qid, item in retrieval.items():
            question = gold[qid]
            if question.answerable is not True:
                continue
            paths = [
                [by_span[(qid, e.span.span_id)] for e in group]
                for group in question.gold_core_evidence_sets
            ]
            for level in config.levels:
                profile = StudentProfile(
                    profile_id="dev-" + level.value,
                    level=level,
                    confidence=config.profile_confidence,
                )
                ordered, _ = rerank_retrieval(
                    item.retrieval,
                    profile,
                    labels,
                    weight,
                    parameter_source="dev",
                    taxonomy_version=manifest["role_provenance"]["role_taxonomy_version"],
                )
                selected_ids = {h.chunk_id for h in ordered.hits[: config.evidence_k]}
                rows.append(
                    {
                        "question_id": qid,
                        "level": level.value,
                        "complete_hit": any(
                            all(ids & selected_ids for ids in path) for path in paths
                        ),
                        "span_coverage": max(
                            sum(bool(ids & selected_ids) for ids in path) / len(path)
                            for path in paths
                        ),
                    }
                )
        if not rows:
            raise ValueError("Dev lambda selection requires answerable Gold with evidence")
        metrics.append(
            {
                "lambda_weight": weight,
                "case_count": len(rows),
                "complete_hit_rate": sum(row["complete_hit"] for row in rows) / len(rows),
                "mean_span_coverage": sum(row["span_coverage"] for row in rows) / len(rows),
                "cases": rows,
            }
        )
    baseline = next(m for m in metrics if m["lambda_weight"] == 0)
    eligible = [
        m
        for m in metrics
        if m["lambda_weight"] > 0 and m["complete_hit_rate"] >= baseline["complete_hit_rate"] - 0.01
    ]
    if not eligible:
        raise ValueError(
            "no positive lambda satisfies the 1 percentage point noninferiority margin"
        )
    best = max(eligible, key=lambda m: m["lambda_weight"])
    corpus = json.loads((prepared_dir / "corpus_manifest.json").read_text(encoding="utf-8"))
    return LambdaSelection(
        lambda_weight=best["lambda_weight"],
        candidate_lambdas=grid,
        gold_sha256=matrix.gold_sha256,
        corpus_hash=corpus["corpus_hash"],
        manifest_hash=corpus["manifest_hash"],
        role_labels_sha256=manifest["role_provenance"]["labels_sha256"],
        profile_confidence=config.profile_confidence,
        candidate_k=config.candidate_k,
        evidence_k=config.evidence_k,
        source_prepared_sha256=canonical_hash(manifest),
        source_retrieval_sha256=manifest.get("source_retrieval_sha256"),
        objective="largest_positive_lambda_within_1pt_of_baseline",
        metrics=metrics,
    )


def retryable_provider_failure(record: GenerationRun, details: dict) -> bool:
    """A citation/parse failure mixed with an outage is not a pure provider outage."""
    attempts = (details.get("generation_trace") or {}).get("attempts", [])
    return (
        record.status == "generation_error"
        and bool(attempts)
        and all(a.get("status") == "provider_failure" for a in attempts)
    )


def _runtime_row(record: GenerationRun, details: dict) -> dict:
    trace = details.get("generation_trace")
    usage = trace["usage"] if trace else {}
    return {
        "condition_id": record.condition_id,
        "student_level": record.student_level.value,
        "status": record.status,
        "model_calls": len(trace["attempts"]) if trace else 0,
        "latency_ms": trace["latency_ms"] if trace else None,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "citation_count": len(record.answer.citations) if record.answer else 0,
    }


def run_experiment(
    prepared_dir: Path,
    output_dir: Path,
    client: LLMClient,
    *,
    provider: str,
    progress: Callable[[int, int, GenerationRun, dict], None] | None = None,
    resume: bool = False,
    concurrency: int = 1,
) -> list[GenerationRun]:
    if concurrency < 1 or concurrency > 32:
        raise ValueError("concurrency must be between 1 and 32")
    if concurrency > 1 and not callable(getattr(client, "for_cell", None)):
        raise ValueError("concurrency requires a client with isolated per-cell state")
    if output_dir.exists() and not resume:
        raise ValueError("output directory already exists; use --resume or a new directory")
    if resume and not output_dir.is_dir():
        raise ValueError("resume requires an existing experiment directory")
    _, config, matrix, *_ = load_prepared(prepared_dir)
    if config.lambda_weight == 0 and any("R1" in c.condition_id for c in matrix.cases):
        raise ValueError("lambda_weight == 0 cannot run an R1 matrix; select a positive Dev lambda")
    if client.model != config.generator_model:
        raise ValueError("generation client model differs from prepared experiment")
    output_dir.mkdir(parents=True, exist_ok=resume)
    with writer_lock(output_dir):
        manifest_path = output_dir / "run_manifest.json"
        original_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
        try:
            return _run_experiment(
                prepared_dir,
                output_dir,
                client,
                provider=provider,
                progress=progress,
                resume=resume,
                concurrency=concurrency,
            )
        except BaseException as exc:
            if manifest_path.exists() and manifest_path.read_bytes() != original_manifest:
                state = json.loads(manifest_path.read_bytes())
                state.update(
                    status="interrupted",
                    interruption_type=type(exc).__name__,
                    interruption_reason=str(exc)[:500],
                    checkpoint_count=len(list((output_dir / "checkpoints").glob("*.json"))),
                )
                if callable(getattr(client, "audit_summary", None)):
                    state["api_audit"] = client.audit_summary(output_dir)
                atomic_json(manifest_path, state)
            raise


def _run_experiment(
    prepared_dir: Path,
    output_dir: Path,
    client: LLMClient,
    *,
    provider: str,
    progress: Callable[[int, int, GenerationRun, dict], None] | None = None,
    resume: bool = False,
    concurrency: int = 1,
) -> list[GenerationRun]:
    """Checkpoint every cell. Failures remain records in the expected denominator."""
    manifest, config, matrix, gold, retrieval, labels = load_prepared(prepared_dir)
    if client.model != config.generator_model:
        raise ValueError("generation client model differs from prepared experiment")
    package_root = files("cs30")
    implementation_hashes = {
        relative: sha256_bytes(package_root.joinpath(relative).read_bytes())
        for relative in (
            "v2/experiment.py",
            "v2/experiment_checkpoint.py",
            "v2/experiment_models.py",
            "v2/io.py",
            "v2/generation.py",
            "v2/generation_prompt.py",
            "v2/evidence.py",
            "generation/client.py",
            "generation/compatible.py",
            "generation/schema.py",
            "generation/prompt.py",
            "generation/reranking.py",
            "retrieval/real.py",
        )
    }
    expected_path = output_dir / "expected_experiment.json"
    requested_manifest = {
        "schema_version": "0.1",
        "result_type": "m7_v2_generation_run",
        "status": "running",
        "reportable": False,
        "provider": provider,
        "prepared_manifest_sha256": canonical_hash(manifest),
        "prepared_inputs": manifest,
        "configuration": config.model_dump(mode="json"),
        "implementation_sha256": implementation_hashes,
        "client": {
            "model": client.model,
            "temperature": client.temperature,
            "max_output_tokens": getattr(client, "max_output_tokens", None),
            "endpoint_sha256": sha256_bytes(client.endpoint.encode())
            if getattr(client, "endpoint", None)
            else None,
        },
    }
    requested_manifest["client"].update(
        context_window=getattr(client, "context_window", None),
        model_digest=getattr(client, "model_digest", None),
        timeout_seconds=getattr(client, "timeout_seconds", None),
        seed=getattr(client, "seed", None),
    )
    if callable(getattr(client, "runtime_identity", None)):
        requested_manifest["client"].update(client.runtime_identity())
    requested_manifest["concurrency"] = concurrency
    requested_manifest["max_api_requests"] = getattr(client, "max_api_requests", None)
    checkpoint_dir = output_dir / "checkpoints"
    if resume:
        existing = json.loads((output_dir / "run_manifest.json").read_bytes())
        for field in (
            "prepared_manifest_sha256",
            "configuration",
            "implementation_sha256",
            "provider",
            "client",
        ):
            if existing.get(field) != requested_manifest[field]:
                raise ValueError(f"resume {field} differs from the original run")
        if json.loads(expected_path.read_bytes()) != matrix.model_dump(mode="json"):
            raise ValueError("resume expected matrix differs from the original run")
        prior_budget = existing.get("max_api_requests")
        new_budget = requested_manifest["max_api_requests"]
        if prior_budget is not None and (new_budget is None or new_budget < prior_budget):
            raise ValueError("resume request cap may only be explicitly increased")
        requested_manifest["budget_history"] = existing.get("budget_history", [])
        if prior_budget != new_budget:
            requested_manifest["budget_history"] = [
                *requested_manifest["budget_history"],
                {"previous": prior_budget, "new": new_budget},
            ]
        completed = load_cells(checkpoint_dir, matrix.cases)
        for run_id, (record, details) in list(completed.items()):
            if retryable_provider_failure(record, details):
                from cs30.v2.experiment_checkpoint import supersede_cell

                supersede_cell(checkpoint_dir, run_id)
                del completed[run_id]
        requested_manifest.update(resume_count=existing.get("resume_count", 0) + 1)
    else:
        checkpoint_dir.mkdir()
        atomic_json(expected_path, matrix.model_dump(mode="json"))
        completed = {}
        requested_manifest["resume_count"] = 0
    if callable(getattr(client, "configure_run", None)):
        client.configure_run(output_dir)
    atomic_json(output_dir / "run_manifest.json", requested_manifest)
    conditions = {item.condition_id: item for item in GenerationCondition}

    def generate_cell(cell):
        cell_client = (
            client.for_cell(cell.run_id, output_dir / "api_cache")
            if callable(getattr(client, "for_cell", None))
            else client
        )
        generator = V2AnswerGenerator(cell_client, max_retries=config.max_retries)
        profile = StudentProfile(
            profile_id="controlled-" + cell.student_level.value,
            level=cell.student_level,
            confidence=config.profile_confidence,
        )
        condition = conditions[cell.condition_id]
        original = retrieval[cell.question_id].retrieval
        selected, rerank_trace = original, None
        if condition.reranking:
            selected, rerank_trace = rerank_retrieval(
                original,
                profile,
                labels,
                config.lambda_weight,
                parameter_source="dev" if config.lambda_policy == "dev_selected" else "fixture",
                taxonomy_version=manifest["role_provenance"]["role_taxonomy_version"]
                if manifest["role_provenance"]
                else "unavailable-role-taxonomy",
            )
        selected = selected.model_copy(update={"hits": selected.hits[: config.evidence_k]})
        bundle = EvidenceBundleAdapter().build(selected)
        try:
            answer = generator.generate(
                gold[cell.question_id],
                profile,
                bundle,
                personalise_prompt=condition.prompt_personalisation,
            )
            assert generator.last_trace is not None
            result = V2BatchResult(answer, generator.last_trace)
        except V2GenerationFailure as exc:
            result = V2BatchResult(None, exc.trace, str(exc))
        except (LLMRequestBudgetExceeded, LLMCacheIntegrityError, LLMRetryLater):
            raise
        except Exception as exc:
            # Malformed provider response objects must not discard later cells.
            result = None
            record = GenerationRun(
                **cell.model_dump(),
                status="generation_error",
                error=f"{type(exc).__name__}: {exc}",
            )
        if result is not None:
            record = GenerationRun.from_v2_result(cell, result)
        generation_trace = result.trace if result else generator.last_trace
        details = {
            **cell.model_dump(mode="json"),
            "profile": profile.model_dump(mode="json"),
            "input_candidate_ids": [h.chunk_id for h in original.hits],
            "selected_candidate_ids": [h.chunk_id for h in selected.hits],
            "evidence": bundle.model_dump(mode="json"),
            "rerank_trace": rerank_trace,
            "generation_trace": asdict(generation_trace) if generation_trace else None,
            "status": record.status,
            "error": record.error,
            "answer": record.answer.model_dump(mode="json") if record.answer else None,
        }
        save_cell(checkpoint_dir, record, details)
        return record, details

    records, runtime_rows = [], []
    with (
        (output_dir / "saved_answers.jsonl").open("w", encoding="utf-8") as answer_file,
        (output_dir / "generation_records.jsonl").open("w", encoding="utf-8") as trace_file,
    ):
        if concurrency > 1:
            pending_cells = iter(c for c in matrix.cases if c.run_id not in completed)
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {}

                def submit_next():
                    cell = next(pending_cells, None)
                    if cell is not None:
                        futures[pool.submit(generate_cell, cell)] = cell

                for _ in range(concurrency):
                    submit_next()
                done_count = len(completed)
                try:
                    while futures:
                        ready, _ = wait(futures, return_when=FIRST_COMPLETED)
                        for future in ready:
                            cell = futures.pop(future)
                            record, details = future.result()
                            completed[cell.run_id] = (record, details)
                            done_count += 1
                            if progress:
                                progress(done_count, len(matrix.cases), record, details)
                            submit_next()
                finally:
                    for future in futures:
                        future.cancel()
        for cell in matrix.cases:
            if cell.run_id in completed:
                record, details = completed[cell.run_id]
            else:
                record, details = generate_cell(cell)
            records.append(record)
            runtime_rows.append(_runtime_row(record, details))
            # The durable detail row precedes its lightweight scoring view.
            trace_file.write(json.dumps(details, ensure_ascii=False, allow_nan=False) + "\n")
            trace_file.flush()
            answer_file.write(record.model_dump_json() + "\n")
            answer_file.flush()
            if progress and cell.run_id not in completed:
                progress(len(records), len(matrix.cases), record, details)
    groups = []
    for condition in GenerationCondition:
        for level in config.levels:
            rows = [
                row
                for row in runtime_rows
                if row["condition_id"] == condition.condition_id
                and row["student_level"] == level.value
            ]
            times = [row["latency_ms"] for row in rows if row["latency_ms"] is not None]
            groups.append(
                {
                    "condition_id": condition.condition_id,
                    "student_level": level.value,
                    "expected": len(rows),
                    "answered": sum(row["status"] == "answered" for row in rows),
                    "abstained": sum(row["status"] == "abstained" for row in rows),
                    "technical_failures": sum(row["status"] == "generation_error" for row in rows),
                    "output_truncated": sum(row["status"] == "output_truncated" for row in rows),
                    "model_calls": sum(row["model_calls"] for row in rows),
                    "mean_cell_call_latency_ms": sum(times) / len(times) if times else None,
                    "input_tokens": sum(row["input_tokens"] for row in rows),
                    "output_tokens": sum(row["output_tokens"] for row in rows),
                    "answers_with_citations": sum(row["citation_count"] > 0 for row in rows),
                }
            )
    write_json(
        output_dir / "generation_summary.json",
        {
            "schema_version": "0.1",
            "reportable": False,
            "expected_runs": len(matrix.cases),
            "groups": groups,
            "role_coverage_complete": manifest["role_coverage_complete"],
            "latency_policy": "sum of locally measured call durations, including failed calls",
            "citation_policy": "chunk ID subset validation; semantic support is not measured",
        },
    )
    (output_dir / "generation_report.md").write_text(
        "# V2 批量生成运行报告\n\n"
        "开发实验，reportable=false。生成产物交给 M8 独立评分。\n\n"
        f"预定 {len(matrix.cases)} 个实验单元，保存 {len(records)} 个。"
        f"Role 候选覆盖完整：{manifest['role_coverage_complete']}。\n\n"
        "| 条件 | 等级 | 预定 | 回答 | 拒答 | 技术失败 | 输出截断 | 模型调用 |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|\n"
        + "".join(
            f"| {g['condition_id']} | {g['student_level']} | {g['expected']} | "
            f"{g['answered']} | {g['abstained']} | {g['technical_failures']} | "
            f"{g['output_truncated']} | {g['model_calls']} |\n"
            for g in groups
        )
        + "\nAPI 温度为 0 或传入 seed 仍不能保证逐字复现；噪声底需独立 Dev 重复生成后报告。"
        "API 原始请求与返回见 api_cache/，逐次 HTTP 用量与请求数见 run_manifest.json 的 api_audit。"
        "\n耗时、用量及引用数量见 generation_summary.json；完整证据和原始模型输出见 "
        "generation_records.jsonl。引用 ID 有效不等于证据语义支持；"
        "本报告不测量学生等级适配质量，也不自动批准正式结论。\n",
        encoding="utf-8",
    )
    run_path = output_dir / "run_manifest.json"
    run_manifest = json.loads(run_path.read_text(encoding="utf-8"))
    run_manifest.update(
        {
            "status": "completed",
            "completed_cells": len(records),
            "technical_failures": sum(r.status == "generation_error" for r in records),
            "output_truncated": sum(r.status == "output_truncated" for r in records),
            "output_sha256": {
                name: sha256_bytes((output_dir / name).read_bytes())
                for name in (
                    "expected_experiment.json",
                    "saved_answers.jsonl",
                    "generation_records.jsonl",
                    "generation_summary.json",
                    "generation_report.md",
                )
            },
        }
    )
    if callable(getattr(client, "audit_summary", None)):
        run_manifest["api_audit"] = client.audit_summary(output_dir)
    atomic_json(run_path, run_manifest)
    return records
