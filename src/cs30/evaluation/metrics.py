"""Offline retrieval metrics for the frozen M1/M3/M4 evaluation seam."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import inf
from typing import Any

from cs30.contracts import RetrievalResult

from .manifest import RunManifest
from .mapping import GoldChunkMapping, QuestionChunkMapping
from .models import EvaluationRunResult, GoldSample

MetricValue = float | int | None


def _span_mappings(
    gold: GoldSample,
    mapping: QuestionChunkMapping,
    *,
    include_partial: bool = False,
) -> dict[str, set[str]]:
    spans = [span for group in gold.gold_core_evidence_sets for span in group]
    if include_partial:
        spans += list(gold.partial_evidence)
    result: dict[str, set[str]] = {}
    for span in spans:
        mapped = mapping.for_span(span.span_id)
        result[span.span_id] = {
            chunk_id for chunk_set in mapped.acceptable_chunk_sets for chunk_id in chunk_set
        }
    return result


def _rank_by_chunk(retrieval: RetrievalResult, k: int | None = None) -> dict[str, int]:
    if k is not None and k <= 0:
        raise ValueError("k must be positive")
    return {
        hit.chunk_id: hit.rank
        for hit in retrieval.hits
        if k is None or hit.rank <= k
    }


def returned_count_at_k(retrieval: RetrievalResult, k: int) -> int:
    """Count unique returned candidates in the top ``k`` ranks."""

    return len(_rank_by_chunk(retrieval, k))


def _span_complete_at_k(
    span_id: str,
    mapping: QuestionChunkMapping,
    rank_by_chunk: dict[str, int],
) -> bool:
    span_mapping = mapping.for_span(span_id)
    return any(
        all(chunk_id in rank_by_chunk for chunk_id in chunk_set)
        for chunk_set in span_mapping.acceptable_chunk_sets
    )


def _span_completion_rank(
    span_id: str,
    mapping: QuestionChunkMapping,
    ranks: dict[str, int],
) -> int:
    span_mapping = mapping.for_span(span_id)
    candidate_ranks = [
        max((ranks.get(chunk_id, inf) for chunk_id in chunk_set), default=inf)
        for chunk_set in span_mapping.acceptable_chunk_sets
    ]
    return min(candidate_ranks, default=inf)


def first_relevant_rank(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
) -> int | None:
    """Return the first rank that hits any core gold-related chunk."""

    span_mappings = _span_mappings(gold, mapping)
    core_chunks = set().union(*span_mappings.values()) if span_mappings else set()
    ranks = [hit.rank for hit in retrieval.hits if hit.chunk_id in core_chunks]
    return min(ranks) if ranks else None


def first_hit_reciprocal_rank(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
) -> float:
    """Standard reciprocal rank of the first core-related hit."""

    rank = first_relevant_rank(gold, retrieval, mapping)
    return 0.0 if rank is None else 1.0 / rank


def complete_evidence_rank(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
) -> int | None:
    """Return the earliest rank at which any complete evidence path exists.

    For an OR path, the path completion rank is the maximum span-completion
    rank within that path.  The question completion rank is the minimum over
    all alternative paths.
    """

    all_ranks = _rank_by_chunk(retrieval)
    path_ranks: list[int] = []
    for evidence_set in gold.gold_core_evidence_sets:
        rank = max(
            (_span_completion_rank(span.span_id, mapping, all_ranks) for span in evidence_set),
            default=inf,
        )
        path_ranks.append(rank)
    complete_rank = min(path_ranks, default=inf)
    return None if complete_rank == inf else int(complete_rank)


def complete_evidence_reciprocal_rank(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
) -> float:
    """Reciprocal rank of the first complete core evidence path."""

    rank = complete_evidence_rank(gold, retrieval, mapping)
    return 0.0 if rank is None else 1.0 / rank


mrr = first_hit_reciprocal_rank
complete_evidence_mrr = complete_evidence_reciprocal_rank


def complete_evidence_hit_at_k(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
    k: int,
) -> float:
    """Return 1 when any complete core evidence path is available by ``k``."""

    if k <= 0:
        raise ValueError("k must be positive")
    rank = complete_evidence_rank(gold, retrieval, mapping)
    return float(rank is not None and rank <= k)


def hit_at_k(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
    k: int,
) -> float:
    """Standard Hit@K: at least one core-related target appears by rank K."""

    if k <= 0:
        raise ValueError("k must be positive")
    rank = first_relevant_rank(gold, retrieval, mapping)
    return float(rank is not None and rank <= k)


def evidence_recall_at_k(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
    k: int,
) -> float:
    """Best necessary-span coverage over the alternative core evidence paths."""

    ranks = _rank_by_chunk(retrieval, k)
    recalls = []
    for evidence_set in gold.gold_core_evidence_sets:
        if not evidence_set:
            continue
        covered = sum(
            _span_complete_at_k(span.span_id, mapping, ranks) for span in evidence_set
        )
        recalls.append(covered / len(evidence_set))
    return max(recalls, default=0.0)


recall_at_k = evidence_recall_at_k


def core_precision_at_k(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
    k: int,
) -> float | None:
    """Fraction of returned candidates mapped to any core gold span."""

    ranks = _rank_by_chunk(retrieval, k)
    if not ranks:
        return None
    core_chunks = set().union(*_span_mappings(gold, mapping).values())
    return len(set(ranks) & core_chunks) / len(ranks)


def context_noise_rate_at_k(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
    k: int,
) -> float | None:
    """Fraction of returned candidates mapped to neither core nor partial spans."""

    ranks = _rank_by_chunk(retrieval, k)
    if not ranks:
        return None
    all_mappings = _span_mappings(gold, mapping, include_partial=True)
    relevant_chunks = set().union(*all_mappings.values()) if all_mappings else set()
    return len(set(ranks) - relevant_chunks) / len(ranks)


def partial_evidence_count_at_k(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
    k: int,
) -> int:
    """Count returned candidates mapped to M3's diagnostic partial evidence."""

    ranks = _rank_by_chunk(retrieval, k)
    if not gold.partial_evidence:
        return 0
    partial_chunks = {
        chunk_id
        for span in gold.partial_evidence
        for chunk_set in mapping.for_span(span.span_id).acceptable_chunk_sets
        for chunk_id in chunk_set
    }
    return len(set(ranks) & partial_chunks)


def empty_retrieval_at_k(retrieval: RetrievalResult, k: int) -> float:
    """Return 1 when the retriever returned no candidates at all."""

    return float(returned_count_at_k(retrieval, k) == 0)


no_hit_rate_at_k = empty_retrieval_at_k


def no_relevant_hit_rate_at_k(
    gold: GoldSample,
    retrieval: RetrievalResult,
    mapping: QuestionChunkMapping,
    k: int,
) -> float | None:
    """Return 1 when non-empty top-``k`` retrieval has no core hit.

    Empty retrieval is deliberately returned as ``None``: it belongs to the
    separate empty/no-hit metric and must not be counted as an irrelevant hit.
    """

    ranks = _rank_by_chunk(retrieval, k)
    if not ranks:
        return None
    core_chunks = set().union(*_span_mappings(gold, mapping).values())
    return float(not (set(ranks) & core_chunks))


@dataclass(frozen=True)
class RetrievalScoreRow:
    """Auditable per-question retrieval metrics and denominator decision."""

    question_id: str
    status: str
    included: bool
    exclusion_reason: str | None
    first_hit_mrr: float | None
    complete_evidence_mrr: float | None
    by_k: dict[int, dict[str, MetricValue]] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "status": self.status,
            "included": self.included,
            "exclusion_reason": self.exclusion_reason,
            "first_hit_mrr": self.first_hit_mrr,
            "complete_evidence_mrr": self.complete_evidence_mrr,
            "by_k": {str(k): values for k, values in self.by_k.items()},
        }


@dataclass(frozen=True)
class RetrievalMetricSummary:
    """Aggregate retrieval metrics for answerable gold-backed questions."""

    sample_count: int
    first_hit_mrr: float
    complete_evidence_mrr: float
    by_k: dict[int, dict[str, MetricValue]]
    excluded_runs: dict[str, int]
    retrieval_scores: list[RetrievalScoreRow] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "mrr": self.first_hit_mrr,
            "first_hit_mrr": self.first_hit_mrr,
            "complete_evidence_mrr": self.complete_evidence_mrr,
            "by_k": {str(k): values for k, values in self.by_k.items()},
            "excluded_runs": dict(self.excluded_runs),
            "retrieval_scores": [row.model_dump() for row in self.retrieval_scores],
        }


def _resolve_mapping(
    mappings: GoldChunkMapping | dict[str, QuestionChunkMapping],
    question_id: str,
) -> QuestionChunkMapping:
    try:
        if isinstance(mappings, GoldChunkMapping):
            return mappings.for_question(question_id)
        return mappings[question_id]
    except KeyError as exc:
        raise ValueError(f"missing gold chunk mapping for {question_id!r}") from exc


def validate_artifact_compatibility(
    gold_samples: list[GoldSample],
    mappings: GoldChunkMapping | dict[str, QuestionChunkMapping],
    *,
    manifest: RunManifest | None = None,
    question_ids: set[str] | None = None,
    prepared_corpus_version: str | None = None,
) -> None:
    """Reject mismatched Gold, mapping, and run-manifest identities.

    A mapping is a derived artifact, so a successful internal mapping
    validation is not enough: it must still refer to the same corpus and
    annotation versions as the questions being scored.
    """

    selected = [
        sample
        for sample in gold_samples
        if question_ids is None or sample.question_id in question_ids
    ]
    if not selected:
        return
    gold_corpora = {sample.corpus_version for sample in selected}
    if len(gold_corpora) != 1:
        raise ValueError("gold samples contain multiple corpus_version values")
    gold_corpus = next(iter(gold_corpora))
    gold_annotations = {sample.gold_annotation_version for sample in selected}
    if len(gold_annotations) != 1:
        raise ValueError("gold samples contain multiple gold_annotation_version values")
    gold_annotation = next(iter(gold_annotations))
    parsers = {sample.parser_version for sample in selected}
    if len(parsers) != 1:
        raise ValueError("gold samples contain multiple parser_version values")
    parser_version = next(iter(parsers))

    if isinstance(mappings, GoldChunkMapping):
        mapping_items = [
            item
            for item in mappings.items
            if question_ids is None or item.question_id in question_ids
        ]
        mapping_corpus = mappings.corpus_version
        mapping_version = mappings.mapping_version
        chunk_config_hash = mappings.chunk_config_hash
    else:
        mapping_items = [
            item
            for item in mappings.values()
            if question_ids is None or item.question_id in question_ids
        ]
        mapping_corpora = {item.corpus_version for item in mapping_items}
        mapping_versions = {item.mapping_version for item in mapping_items}
        chunk_hashes = {item.chunk_config_hash for item in mapping_items}
        if len(mapping_corpora) > 1:
            raise ValueError("mapping contains multiple corpus_version values")
        if len(mapping_versions) > 1:
            raise ValueError("mapping contains multiple mapping_version values")
        if len(chunk_hashes) > 1:
            raise ValueError("mapping contains multiple chunk_config_hash values")
        mapping_corpus = next(iter(mapping_corpora), None)
        mapping_version = next(iter(mapping_versions), None)
        chunk_config_hash = next(iter(chunk_hashes), None)

    if mapping_corpus is not None and mapping_corpus != gold_corpus:
        raise ValueError(
            "corpus_version mismatch between Gold and mapping: "
            f"{gold_corpus!r} != {mapping_corpus!r}"
        )

    if prepared_corpus_version is not None:
        if gold_corpus != prepared_corpus_version:
            raise ValueError(
                "corpus_version mismatch between prepared corpus and Gold: "
                f"{prepared_corpus_version!r} != {gold_corpus!r}"
            )
        if mapping_corpus is not None and mapping_corpus != prepared_corpus_version:
            raise ValueError(
                "corpus_version mismatch between prepared corpus and mapping: "
                f"{prepared_corpus_version!r} != {mapping_corpus!r}"
            )

    if manifest is not None:
        if (
            prepared_corpus_version is not None
            and manifest.corpus_version != prepared_corpus_version
        ):
            raise ValueError(
                "corpus_version mismatch between prepared corpus and manifest: "
                f"{prepared_corpus_version!r} != {manifest.corpus_version!r}"
            )
        if manifest.corpus_version != "unspecified" and manifest.corpus_version != gold_corpus:
            raise ValueError(
                "corpus_version mismatch between manifest and Gold: "
                f"{manifest.corpus_version!r} != {gold_corpus!r}"
            )
        if (
            manifest.chunk_version != "unspecified"
            and chunk_config_hash is not None
            and manifest.chunk_version != chunk_config_hash
        ):
            raise ValueError(
                "chunk_version mismatch between manifest and mapping: "
                f"{manifest.chunk_version!r} != {chunk_config_hash!r}"
            )
        if (
            manifest.gold_annotation_version is not None
            and manifest.gold_annotation_version != gold_annotation
        ):
            raise ValueError(
                "gold_annotation_version mismatch between manifest and Gold: "
                f"{manifest.gold_annotation_version!r} != {gold_annotation!r}"
            )
        if manifest.mapping_version is not None and manifest.mapping_version != mapping_version:
            raise ValueError(
                "mapping_version mismatch between manifest and mapping: "
                f"{manifest.mapping_version!r} != {mapping_version!r}"
            )
        if manifest.parser_version is not None and manifest.parser_version != parser_version:
            raise ValueError(
                "parser_version mismatch between manifest and Gold: "
                f"{manifest.parser_version!r} != {parser_version!r}"
            )


def compute_retrieval_metrics(
    gold_samples: list[GoldSample],
    run_results: list[EvaluationRunResult],
    mappings: GoldChunkMapping | dict[str, QuestionChunkMapping],
    *,
    k_values: list[int],
    top_k: int | None = None,
    strict_mapping: bool = False,
) -> RetrievalMetricSummary:
    """Score saved retrieval traces without invoking a model.

    Development scoring excludes a question whose mapping is incomplete and
    records the reason in ``retrieval_scores``.  Formal callers can set
    ``strict_mapping=True`` to fail before producing any aggregate result.
    """

    if not k_values or any(k <= 0 for k in k_values) or len(set(k_values)) != len(k_values):
        raise ValueError("k_values must contain unique positive integers")
    if k_values != sorted(k_values):
        raise ValueError("k_values must be sorted in ascending order")
    if top_k is not None and any(k > top_k for k in k_values):
        raise ValueError("k_values must not exceed top_k")
    gold_by_id = {sample.question_id: sample for sample in gold_samples}
    if len(gold_by_id) != len(gold_samples):
        raise ValueError("gold_samples contain duplicate question_id values")
    run_question_ids = [result.question_id for result in run_results]
    if len(set(run_question_ids)) != len(run_question_ids):
        raise ValueError("run_results must contain one result per question")

    excluded = {
        # ``total`` is the authoritative number of excluded questions.  The
        # remaining keys are mutually exclusive reasons, not additive parent
        # and child counters.
        "total": 0,
        "missing_gold": 0,
        "missing_gold_evidence": 0,
        "unanswerable": 0,
        "unresolved": 0,
        "disputed": 0,
        "retrieval_error": 0,
        "mapping_missing": 0,
    }
    scored: list[tuple[GoldSample, EvaluationRunResult, QuestionChunkMapping]] = []
    retrieval_scores_by_id: dict[str, RetrievalScoreRow] = {}
    for result in run_results:
        gold = gold_by_id.get(result.question_id)
        if gold is None:
            excluded["total"] += 1
            excluded["missing_gold"] += 1
            retrieval_scores_by_id[result.question_id] = (
                RetrievalScoreRow(
                    question_id=result.question_id,
                    status=result.status.value,
                    included=False,
                    exclusion_reason="missing_gold",
                    first_hit_mrr=None,
                    complete_evidence_mrr=None,
                )
            )
            continue
        if gold.answerable is False:
            excluded["total"] += 1
            excluded["unanswerable"] += 1
            retrieval_scores_by_id[result.question_id] = (
                RetrievalScoreRow(
                    question_id=result.question_id,
                    status=result.status.value,
                    included=False,
                    exclusion_reason="unanswerable",
                    first_hit_mrr=None,
                    complete_evidence_mrr=None,
                )
            )
            continue
        if gold.answerable is None:
            excluded["total"] += 1
            reason = (
                "disputed"
                if gold.annotation_status.value == "disputed"
                else "unresolved"
            )
            excluded[reason] += 1
            retrieval_scores_by_id[result.question_id] = (
                RetrievalScoreRow(
                    question_id=result.question_id,
                    status=result.status.value,
                    included=False,
                    exclusion_reason=reason,
                    first_hit_mrr=None,
                    complete_evidence_mrr=None,
                )
            )
            continue
        if not gold.gold_core_evidence_sets:
            excluded["total"] += 1
            excluded["missing_gold_evidence"] += 1
            retrieval_scores_by_id[result.question_id] = (
                RetrievalScoreRow(
                    question_id=result.question_id,
                    status=result.status.value,
                    included=False,
                    exclusion_reason="missing_gold_evidence",
                    first_hit_mrr=None,
                    complete_evidence_mrr=None,
                )
            )
            continue
        if result.retrieval is None:
            excluded["total"] += 1
            excluded["retrieval_error"] += 1
            retrieval_scores_by_id[result.question_id] = (
                RetrievalScoreRow(
                    question_id=result.question_id,
                    status=result.status.value,
                    included=False,
                    exclusion_reason="retrieval_error",
                    first_hit_mrr=None,
                    complete_evidence_mrr=None,
                )
            )
            continue
        try:
            mapping = _resolve_mapping(mappings, result.question_id)
            # Core and diagnostic partial spans must both be mappable.  Calling
            # this once up front avoids a later metric failing halfway through
            # an otherwise valid row.
            _span_mappings(gold, mapping, include_partial=True)
        except (KeyError, ValueError) as exc:
            excluded["total"] += 1
            excluded["mapping_missing"] += 1
            if strict_mapping:
                raise ValueError(
                    f"mapping_missing for {result.question_id!r}: {exc}"
                ) from exc
            retrieval_scores_by_id[result.question_id] = (
                RetrievalScoreRow(
                    question_id=result.question_id,
                    status=result.status.value,
                    included=False,
                    exclusion_reason="mapping_missing",
                    first_hit_mrr=None,
                    complete_evidence_mrr=None,
                )
            )
            continue
        scored.append((gold, result, mapping))

    def score_row(
        gold: GoldSample,
        result: EvaluationRunResult,
        mapping: QuestionChunkMapping,
    ) -> RetrievalScoreRow:
        assert result.retrieval is not None
        by_k: dict[int, dict[str, MetricValue]] = {}
        for k in k_values:
            by_k[k] = {
                "complete_evidence_hit_at_k": complete_evidence_hit_at_k(
                    gold, result.retrieval, mapping, k
                ),
                "hit_at_k": hit_at_k(gold, result.retrieval, mapping, k),
                "evidence_recall_at_k": evidence_recall_at_k(
                    gold, result.retrieval, mapping, k
                ),
                "recall_at_k": recall_at_k(gold, result.retrieval, mapping, k),
                "core_precision_at_k": core_precision_at_k(
                    gold, result.retrieval, mapping, k
                ),
                "context_noise_rate_at_k": context_noise_rate_at_k(
                    gold, result.retrieval, mapping, k
                ),
                "no_relevant_hit_rate_at_k": no_relevant_hit_rate_at_k(
                    gold, result.retrieval, mapping, k
                ),
                "partial_evidence_count_at_k": partial_evidence_count_at_k(
                    gold, result.retrieval, mapping, k
                ),
                "returned_count_at_k": returned_count_at_k(result.retrieval, k),
                "empty_retrieval_rate": empty_retrieval_at_k(result.retrieval, k),
                "no_hit_rate_at_k": no_hit_rate_at_k(result.retrieval, k),
            }
        return RetrievalScoreRow(
            question_id=result.question_id,
            status=result.status.value,
            included=True,
            exclusion_reason=None,
            first_hit_mrr=first_hit_reciprocal_rank(
                gold, result.retrieval, mapping
            ),
            complete_evidence_mrr=complete_evidence_reciprocal_rank(
                gold, result.retrieval, mapping
            ),
            by_k=by_k,
        )

    included_rows = [score_row(gold, result, mapping) for gold, result, mapping in scored]
    for row in included_rows:
        retrieval_scores_by_id[row.question_id] = row

    first_mrr = (
        sum(row.first_hit_mrr or 0.0 for row in included_rows) / len(included_rows)
        if scored
        else 0.0
    )
    complete_mrr = (
        sum(row.complete_evidence_mrr or 0.0 for row in included_rows)
        / len(included_rows)
        if scored
        else 0.0
    )

    def mean(values: list[MetricValue]) -> float | None:
        defined = [float(value) for value in values if value is not None]
        return sum(defined) / len(defined) if defined else None

    by_k: dict[int, dict[str, MetricValue]] = {}
    for k in k_values:
        rows = [row.by_k[k] for row in included_rows]
        by_k[k] = {
            "complete_evidence_hit_at_k": mean(
                [row["complete_evidence_hit_at_k"] for row in rows]
            ),
            "hit_at_k": mean([row["hit_at_k"] for row in rows]),
            "evidence_recall_at_k": mean(
                [row["evidence_recall_at_k"] for row in rows]
            ),
            "recall_at_k": mean([row["recall_at_k"] for row in rows]),
            "core_precision_at_k": mean(
                [row["core_precision_at_k"] for row in rows]
            ),
            "core_precision_defined_count": sum(
                row["core_precision_at_k"] is not None for row in rows
            ),
            "context_noise_rate_at_k": mean(
                [row["context_noise_rate_at_k"] for row in rows]
            ),
            "context_noise_defined_count": sum(
                row["context_noise_rate_at_k"] is not None for row in rows
            ),
            "no_relevant_hit_rate_at_k": mean(
                [row["no_relevant_hit_rate_at_k"] for row in rows]
            ),
            "no_relevant_hit_defined_count": sum(
                row["no_relevant_hit_rate_at_k"] is not None for row in rows
            ),
            "partial_evidence_count_at_k": mean(
                [row["partial_evidence_count_at_k"] for row in rows]
            ),
            "mean_partial_evidence_count_at_k": mean(
                [row["partial_evidence_count_at_k"] for row in rows]
            ),
            "returned_count_at_k": mean(
                [row["returned_count_at_k"] for row in rows]
            ),
            "empty_retrieval_rate": mean(
                [row["empty_retrieval_rate"] for row in rows]
            ),
            "no_hit_rate_at_k": mean([row["no_hit_rate_at_k"] for row in rows]),
        }
    return RetrievalMetricSummary(
        sample_count=len(included_rows),
        first_hit_mrr=first_mrr,
        complete_evidence_mrr=complete_mrr,
        by_k=by_k,
        excluded_runs=excluded,
        retrieval_scores=[retrieval_scores_by_id[question_id] for question_id in run_question_ids],
    )


score_retrieval_batch = compute_retrieval_metrics
