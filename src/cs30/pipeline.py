"""Unified Week 1 pipeline entry point.

The offline build path and online answering path depend only on Protocols from
:mod:`cs30.ports`. Integrating a real module means supplying a different object
through ``BuildDeps`` or ``PipelineDeps``; orchestration functions do not change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cs30.chunking import FixtureChunker
from cs30.citation import (
    CitationResolver,
    EvidenceContextBuilder,
)
from cs30.config import AppConfig, load_config
from cs30.contracts import IndexArtifact, PipelineRun, RetrievalHit, StudentLevel
from cs30.errors import ConfigError, CS30Error, EmptyQueryError
from cs30.generation import (
    CombinedEvidenceRetriever,
    FixtureAnswerGenerator,
    MockJsonLLMClient,
    OllamaChatClient,
    OpenAIResponsesClient,
    PersonalisedAnswerGenerator,
)
from cs30.generation.demo import build_all_dataset_items
from cs30.indexing import FixtureIndexBuilder
from cs30.ingest import FixtureDocumentParser
from cs30.logging import configure_logging, get_logger
from cs30.ports import (
    AnswerGenerator,
    Chunker,
    DocumentParser,
    IndexBuilder,
    ProfileProvider,
    Retriever,
)
from cs30.profile import FixtureProfileProvider, Week1ProfileProvider
from cs30.retrieval import FixtureRetriever

LOGGER = get_logger("pipeline")

_RULE = "=" * 70
FIXTURE_BANNER = "\n".join(
    (
        _RULE,
        "  FIXTURE MODE - fixed sample data, no index and no model.",
        "  Demonstrates the engineering path only. These results say nothing",
        "  about how well any retrieval method or model performs.",
        _RULE,
    )
)


@dataclass(frozen=True)
class PipelineDeps:
    """The three modules the online path needs."""

    mode: Literal["fixture", "real"]
    profile_provider: ProfileProvider
    retriever: Retriever
    generator: AnswerGenerator


@dataclass(frozen=True)
class BuildDeps:
    """Modules in the offline parse -> chunk -> index path."""

    parser: DocumentParser
    chunker: Chunker
    index_builder: IndexBuilder
    retriever: Retriever


def build_fixture_deps() -> PipelineDeps:
    """Stand-in modules used until the real ones land."""

    return PipelineDeps(
        mode="fixture",
        profile_provider=FixtureProfileProvider(),
        retriever=FixtureRetriever(),
        generator=FixtureAnswerGenerator(),
    )


def build_task7_smoke_deps() -> PipelineDeps:
    """Exercise member 7 against fixture retrieval without calling a remote model."""

    return PipelineDeps(
        mode="fixture",
        profile_provider=Week1ProfileProvider(profile_prefix="task7-smoke"),
        retriever=FixtureRetriever(),
        generator=PersonalisedAnswerGenerator(MockJsonLLMClient()),
    )


def build_fixture_build_deps() -> BuildDeps:
    """Stand-in modules for exercising the complete offline hand-off."""

    return BuildDeps(
        parser=FixtureDocumentParser(),
        chunker=FixtureChunker(),
        index_builder=FixtureIndexBuilder(),
        retriever=FixtureRetriever(),
    )


def run_build_pipeline(source: Path, deps: BuildDeps) -> IndexArtifact:
    """Parse, chunk, build an index, then attach its manifest to retrieval."""

    document = deps.parser.parse(source)
    chunks = deps.chunker.chunk(document)
    artifact = deps.index_builder.build(chunks)
    deps.retriever.load_index(artifact)
    return artifact


def build_real_deps(config: AppConfig) -> PipelineDeps:
    """Build configured generation over the available fixture evidence."""

    dataset = build_all_dataset_items(StudentLevel.INTERMEDIATE)
    evidence_by_id: dict[str, RetrievalHit] = {}
    for item in dataset.items:
        for hit in item.retrieval.hits:
            evidence_by_id.setdefault(hit.chunk_id, hit)
    retriever = CombinedEvidenceRetriever(evidence_by_id.values())

    provider = config.generation.provider.casefold()
    if provider == "mock":
        client = MockJsonLLMClient()
    elif provider == "ollama":
        client = OllamaChatClient(
            config.generation.model or "gpt-oss:20b",
            temperature=config.generation.temperature,
        )
    elif provider == "openai":
        if not config.generation.model:
            raise ConfigError("LLM_MODEL is required when LLM_PROVIDER=openai")
        client = OpenAIResponsesClient(
            config.generation.model,
            temperature=config.generation.temperature,
        )
    else:
        raise ConfigError(
            "LLM_PROVIDER must be one of: mock, ollama, openai; "
            f"received {config.generation.provider!r}"
        )

    return PipelineDeps(
        mode="fixture",
        profile_provider=Week1ProfileProvider(profile_prefix="local-rag"),
        retriever=retriever,
        generator=PersonalisedAnswerGenerator(
            client,
            max_retries=config.generation.max_retries,
        ),
    )


def run_pipeline(
    question: str,
    level: StudentLevel,
    deps: PipelineDeps,
    config: AppConfig,
    *,
    question_id: str | None = None,
) -> PipelineRun:
    """Run profile -> retrieval -> generation -> citation check."""

    if not question.strip():
        raise EmptyQueryError("question must not be empty")
    question = question.strip()

    profile = deps.profile_provider.get(level)

    started = time.perf_counter()
    retrieval = deps.retriever.retrieve(question, config.retrieval.top_k)
    retrieval_ms = (time.perf_counter() - started) * 1000
    LOGGER.info(
        "retrieval hits=%d top_k=%d elapsed_ms=%.1f",
        len(retrieval.hits),
        config.retrieval.top_k,
        retrieval_ms,
    )

    run_id = uuid.uuid4().hex[:12]
    evidence_bundle = EvidenceContextBuilder().build(
        retrieval,
        retrieval_mode=retrieval.mode,
        run_provenance={
            "run_id": run_id,
            "environment": config.environment,
            "mode": deps.mode,
        },
    )
    # M7 owns generation and consumes the frozen RetrievalResult contract.
    # M8 owns the post-generation evidence/citation governance boundary.
    answer = deps.generator.generate(question, profile, retrieval)
    LOGGER.info(
        "generation level=%s abstained=%s citations=%d",
        profile.level.value,
        answer.abstained,
        len(answer.citations),
    )

    validated_answer = CitationResolver().resolve(answer, evidence_bundle)
    run_trace = {
        "request_id": run_id,
        "query": question,
        "profile_level": profile.level.value,
        "retrieval_mode": retrieval.mode.value,
        "retrieved_ids": ",".join(hit.chunk_id for hit in retrieval.hits),
        "selected_evidence_ids": ",".join(
            item.evidence_id for item in evidence_bundle.evidence_items
        ),
        "citation_ids": ",".join(answer.citations),
        "context_token_count": str(evidence_bundle.token_count),
        "context_hash": hashlib.sha256(
            (evidence_bundle.prompt_context or "").encode("utf-8")
        ).hexdigest(),
        "corpus_version": (
            retrieval.provenance.corpus_hash
            if retrieval.provenance is not None
            else "fixture-corpus-v1"
        ),
        "index_version": (
            retrieval.provenance.index_version
            if retrieval.provenance is not None
            else "fixture-index-v1"
        ),
        "artifact_version": (
            retrieval.provenance.index_version
            if retrieval.provenance is not None
            else "fixture-index-v1"
        ),
    }
    LOGGER.info(
        "trace request_id=%s query=%r profile_level=%s retrieved_ids=%s "
        "selected_ids=%s citation_ids=%s context_hash=%s",
        run_trace["request_id"],
        run_trace["query"],
        run_trace["profile_level"],
        run_trace["retrieved_ids"],
        run_trace["selected_evidence_ids"],
        run_trace["citation_ids"],
        run_trace["context_hash"],
    )
    LOGGER.info("trace_json=%s", json.dumps(run_trace, ensure_ascii=False, sort_keys=True))
    metadata = {
        "environment": config.environment,
        "top_k": str(config.retrieval.top_k),
        "index_type": str(
            getattr(deps.retriever, "index_type", config.retrieval.index_type)
        ),
        "provider": config.generation.provider,
        "retrieval_ms": f"{retrieval_ms:.1f}",
    }
    generation_trace = getattr(deps.generator, "last_trace", None)
    if generation_trace is not None and callable(getattr(generation_trace, "to_metadata", None)):
        metadata.update(generation_trace.to_metadata())
    evidence_count = getattr(deps.retriever, "evidence_count", None)
    if evidence_count is not None:
        metadata["corpus_evidence_count"] = str(evidence_count)
    return PipelineRun(
        run_id=run_id,
        mode=deps.mode,
        question=question,
        question_id=question_id,
        profile=profile,
        retrieval=retrieval,
        answer=answer,
        citation_integrity="passed",
        metadata={
            "environment": config.environment,
            "top_k": str(config.retrieval.top_k),
            "retrieval_mode": retrieval.mode.value,
            "provider": config.generation.provider,
            "retrieval_ms": f"{retrieval_ms:.1f}",
            **metadata,
        },
        evidence_bundle=evidence_bundle,
        validated_answer=validated_answer,
        trace=run_trace,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CS-30 Week 1 thin-slice pipeline")
    parser.add_argument("--question", required=True, help="Question to send through the pipeline")
    parser.add_argument(
        "--level",
        choices=[level.value for level in StudentLevel],
        default=StudentLevel.INTERMEDIATE.value,
        help="Student explanation level",
    )
    parser.add_argument("--env", default=None, help="Configuration environment name")
    parser.add_argument(
        "--mode",
        choices=["fixture", "real"],
        default=None,
        help="Override the environment's fixture_mode setting",
    )
    parser.add_argument(
        "--provider",
        choices=["mock", "ollama", "openai"],
        default=None,
        help="Generation provider override; use ollama for the local real model",
    )
    parser.add_argument("--model", default=None, help="Generation model override")
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Number of evidence passages to retrieve",
    )
    parser.add_argument(
        "--answer-only",
        action="store_true",
        help="Print only the final explanation and suppress informational logs",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        config = load_config(args.env)
        if args.provider is not None or args.model is not None:
            generation_updates = {}
            if args.provider is not None:
                generation_updates["provider"] = args.provider
            if args.model is not None:
                generation_updates["model"] = args.model
            config = config.model_copy(
                update={
                    "generation": config.generation.model_copy(
                        update=generation_updates
                    )
                }
            )
        if args.top_k is not None:
            if args.top_k < 1:
                raise ConfigError("--top-k must be positive")
            config = config.model_copy(
                update={
                    "retrieval": config.retrieval.model_copy(
                        update={"top_k": args.top_k}
                    )
                }
            )
        configure_logging("WARNING" if args.answer_only else config.log_level)
        mode = args.mode or ("fixture" if config.fixture_mode else "real")
        if mode == "fixture":
            print(FIXTURE_BANNER, file=sys.stderr)
            deps = build_fixture_deps()
        else:
            deps = build_real_deps(config)
        run = run_pipeline(args.question, StudentLevel(args.level), deps, config)
    except (CS30Error, NotImplementedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if args.answer_only:
        print(run.answer.explanation)
    else:
        print(run.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
