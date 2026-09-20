"""Offline real document -> chunks -> FAISS build entry point."""

from __future__ import annotations

import argparse
import contextlib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cs30.chunking import BlockAwareChunker, BlockChunkingStrategy, get_chunking_candidate
from cs30.chunking.official import W5_CHUNKING_STRATEGY
from cs30.contracts import OpenStaxDocument
from cs30.errors import CS30Error, IndexUnavailableError
from cs30.pipeline import BuildDeps, run_build_pipeline
from cs30.retrieval import BM25Retriever


@dataclass
class RealDocumentParser:
    """Adapt M2's file output or PDF parser to the shared parser protocol."""

    chapters: tuple[str, ...] = ()
    source_url: str = "https://openstax.org/details/books/college-physics-2e"
    download_date: str = ""

    def parse(self, source: Path) -> OpenStaxDocument:
        if source.suffix.lower() == ".json":
            return OpenStaxDocument.model_validate_json(source.read_text(encoding="utf-8"))
        if source.suffix.lower() != ".pdf":
            raise ValueError("source must be a contract JSON document or an OpenStax PDF")
        if not self.chapters:
            raise ValueError("PDF input requires --chapters (space-separated chapter numbers)")
        try:
            from cs30.ingest import openstax_parser
        except (ImportError, SystemExit) as exc:
            raise IndexUnavailableError('PDF input requires pip install -e ".[parse]"') from exc
        parsed = openstax_parser.parse_openstax(
            source,
            selected_chapters=self.chapters,
            source_url=self.source_url,
            download_date=self.download_date or datetime.now(UTC).date().isoformat(),
            title="College Physics 2e",
            edition="2e",
        )
        return OpenStaxDocument.model_validate(openstax_parser.build_contract_payload(parsed))


def _chunking_strategy(candidate: str) -> BlockChunkingStrategy:
    """Resolve the chunking configuration a build should use.

    ``official`` is the frozen W5 configuration and the only one that matches
    the evidence policy Gold is annotated against, so it is the default. The
    ablation candidates are kept reachable but abort on the real corpus: they
    filter by content type, the surviving blocks repeat verbatim, and they all
    still set ``reject_duplicate_text=True``.
    """

    name = candidate.lower()
    if name == "official":
        return W5_CHUNKING_STRATEGY
    if name == "main":
        return BlockChunkingStrategy()
    return get_chunking_candidate(candidate.upper()).strategy


def build_real_build_deps(
    *,
    index_dir: Path,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    candidate: str = "official",
    chapters: tuple[str, ...] = (),
    source_url: str = "https://openstax.org/details/books/college-physics-2e",
    download_date: str = "",
) -> BuildDeps:
    """Share the embedding model's tokenizer with M4; never fall back to fixtures."""
    strategy = _chunking_strategy(candidate)
    try:
        from cs30.indexing.faiss_index import (
            FaissIndexBuilder,
            get_query_instruction,
        )
    except ImportError as exc:
        raise IndexUnavailableError('Index building requires pip install -e ".[ml]"') from exc
    builder = FaissIndexBuilder(
        model_name=model_name,
        index_dir=str(index_dir),
        query_instruction=get_query_instruction(model_name),
    )
    return BuildDeps(
        parser=RealDocumentParser(chapters, source_url, download_date),
        chunker=BlockAwareChunker(strategy=strategy, token_counter=builder.token_counter()),
        index_builder=builder,
        # Verify persisted chunk-map loading without loading the embedding model twice.
        retriever=BM25Retriever(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="M2 openstax_document.json or College Physics PDF"
    )
    parser.add_argument("--index-dir", type=Path, required=True, help="New, empty output directory")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument(
        "--candidate",
        choices=["official", "main", "S1", "S2", "S3", "S4", "S5", "S6"],
        default="official",
        help="official is the frozen W5 configuration; use it for the real corpus",
    )
    parser.add_argument("--chapters", nargs="+", default=[], help="PDF chapter numbers, e.g. 2 3 4")
    parser.add_argument("--source-url", default=RealDocumentParser.source_url)
    parser.add_argument("--download-date", default="")
    args = parser.parse_args(argv)
    try:
        if not args.source.is_file():
            raise ValueError(f"source file not found: {args.source}")
        if args.source.suffix.lower() not in {".json", ".pdf"}:
            raise ValueError("source must be a .json or .pdf file")
        if args.source.suffix.lower() == ".pdf" and not args.chapters:
            raise ValueError("PDF input requires --chapters")
        if args.index_dir.exists() and (
            not args.index_dir.is_dir() or any(args.index_dir.iterdir())
        ):
            raise ValueError("index-dir must be empty; choose a new directory for each build")
        # Third-party model loaders may print progress; stdout remains one JSON manifest.
        with contextlib.redirect_stdout(sys.stderr):
            deps = build_real_build_deps(
                index_dir=args.index_dir.resolve(),
                model_name=args.model,
                candidate=args.candidate,
                chapters=tuple(args.chapters),
                source_url=args.source_url,
                download_date=args.download_date,
            )
            artifact = run_build_pipeline(args.source, deps)
    except (CS30Error, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(artifact.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
