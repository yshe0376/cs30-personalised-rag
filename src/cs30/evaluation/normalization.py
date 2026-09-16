"""Normalize immutable M3 Gold spans into corpus-global coordinates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from .models import GoldEvidenceSpan, GoldSample, SpanResolutionStatus
from .openstax_archive import OpenStaxArchiveCorpus
from .span_resolution import resolve_span_to_corpus


@dataclass(frozen=True, slots=True)
class NormalizationReport:
    """Auditable result of resolving every Gold evidence span exactly once."""

    total_spans: int
    resolved: int
    stale: int
    ambiguous: int
    diagnostics: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if min(self.total_spans, self.resolved, self.stale, self.ambiguous) < 0:
            raise ValueError("normalization counts must not be negative")
        if self.total_spans != self.resolved + self.stale + self.ambiguous:
            raise ValueError("normalization counts must account for every span exactly once")
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))


def normalize_gold_samples(
    samples: Sequence[GoldSample],
    corpus: OpenStaxArchiveCorpus,
    *,
    normalizer_version: str = "gold-normalizer-0.1",
) -> tuple[list[GoldSample], NormalizationReport]:
    """Return normalized copies of Gold samples without changing M3 inputs."""

    normalized: list[GoldSample] = []
    diagnostics: dict[str, str] = {}
    counts = {status: 0 for status in SpanResolutionStatus}

    for sample in samples:
        core_sets = [
            [
                _normalize_span(span, corpus, diagnostics, counts)
                for span in evidence_set
            ]
            for evidence_set in sample.gold_core_evidence_sets
        ]
        partial_evidence = [
            _normalize_span(span, corpus, diagnostics, counts)
            for span in sample.partial_evidence
        ]
        payload = sample.model_dump(mode="python")
        payload.update(
            schema_version="0.2",
            corpus_version=corpus.corpus_version,
            source_corpus_version=sample.source_corpus_version or sample.corpus_version,
            normalizer_version=normalizer_version,
            gold_core_evidence_sets=core_sets,
            partial_evidence=partial_evidence,
        )
        normalized.append(GoldSample.model_validate(payload))

    return normalized, NormalizationReport(
        total_spans=sum(counts.values()),
        resolved=counts[SpanResolutionStatus.RESOLVED],
        stale=counts[SpanResolutionStatus.STALE],
        ambiguous=counts[SpanResolutionStatus.AMBIGUOUS],
        diagnostics=diagnostics,
    )


def _normalize_span(
    span: GoldEvidenceSpan,
    corpus: OpenStaxArchiveCorpus,
    diagnostics: dict[str, str],
    counts: dict[SpanResolutionStatus, int],
) -> GoldEvidenceSpan:
    resolution = resolve_span_to_corpus(span, corpus)
    counts[resolution.status] += 1
    diagnostics[span.span_id] = resolution.message
    payload = span.model_dump(mode="python")
    payload.update(
        chapter_char_start=resolution.chapter_char_start,
        chapter_char_end=resolution.chapter_char_end,
        corpus_char_start=resolution.corpus_char_start,
        corpus_char_end=resolution.corpus_char_end,
        resolved_block_id=resolution.resolved_block_id,
        resolution_status=resolution.status,
        resolution_method=resolution.method,
    )
    return GoldEvidenceSpan.model_validate(payload)
