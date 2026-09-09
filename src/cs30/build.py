"""Offline real document -> chunks -> FAISS build entry point."""

from __future__ import annotations

import argparse
import contextlib
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from cs30.chunking import BlockAwareChunker, BlockChunkingStrategy, get_chunking_candidate
from cs30.contracts import TextbookDocument
from cs30.errors import IndexUnavailableError
from cs30.ingest.textbooks import DEFAULT_TEXTBOOK_ID, TEXTBOOKS, get_textbook
from cs30.pipeline import BuildDeps, run_build_pipeline
from cs30.retrieval import BM25Retriever


@dataclass
class RealDocumentParser:
    """Adapt a contract JSON or supported textbook PDF to the shared protocol."""

    chapters: tuple[str, ...] = ()
    source_url: str = ""
    download_date: str = ""
    textbook_id: str = DEFAULT_TEXTBOOK_ID

    def parse(self, source: Path) -> TextbookDocument:
        if source.suffix.lower() == ".json":
            return TextbookDocument.model_validate_json(source.read_text(encoding="utf-8"))
        if source.suffix.lower() != ".pdf":
            raise ValueError("source must be a contract JSON document or a supported textbook PDF")
        if not self.chapters:
            raise ValueError("PDF input requires --chapters (space-separated chapter numbers)")
        spec = get_textbook(self.textbook_id)
        try:
            from cs30.ingest import openstax_parser
        except (ImportError, SystemExit) as exc:
            raise IndexUnavailableError('PDF input requires pip install -e ".[parse]"') from exc
        validate_source_identity = getattr(openstax_parser, "validate_source_identity", None)
        if not callable(validate_source_identity):
            raise IndexUnavailableError("PDF parser does not provide source identity validation")
        validate_source_identity(source, spec.source_title_markers)
        parse_options = {
            "selected_chapters": self.chapters,
            "source_url": self.source_url or spec.source_url,
            "download_date": self.download_date or datetime.now(UTC).date().isoformat(),
            "title": spec.title,
            "edition": spec.version,
        }
        if self.textbook_id != DEFAULT_TEXTBOOK_ID:
            source_hash = openstax_parser.sha256_file(source)
            parse_options["document_id"] = f"{spec.document_id_prefix}-{source_hash[:16]}"
        parsed = openstax_parser.parse_openstax(source, **parse_options)
        payload = openstax_parser.build_contract_payload(parsed)
        provenance = {
            "textbook_id": spec.textbook_id,
            "provider": spec.provider,
            "subject": spec.subject,
            "license": spec.license,
        }
        for block in payload["blocks"]:
            block["metadata"].update(provenance)
        return TextbookDocument.model_validate(payload)


def _fit_strategy_to_embedding_limit(
    strategy: BlockChunkingStrategy, token_counter: object
) -> BlockChunkingStrategy:
    """Keep real chunks within the selected embedder's non-special-token limit."""

    limit = getattr(token_counter, "max_input_tokens", None)
    if not isinstance(limit, int) or limit <= 0 or strategy.max_tokens <= limit:
        return strategy
    target_tokens = min(strategy.target_tokens, limit)
    return replace(
        strategy,
        target_tokens=target_tokens,
        min_tokens=min(strategy.min_tokens, target_tokens),
        max_tokens=limit,
    )


def _remove_partial_outputs(index_dir: Path) -> None:
    """Remove only files owned by a failed build in its required empty directory."""

    for filename in ("index.faiss", "chunks.json", "artifact.json"):
        try:
            (index_dir / filename).unlink()
        except FileNotFoundError:
            pass


def build_real_build_deps(
    *,
    index_dir: Path,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    candidate: str = "main",
    chapters: tuple[str, ...] = (),
    source_url: str = "",
    download_date: str = "",
    textbook_id: str = DEFAULT_TEXTBOOK_ID,
) -> BuildDeps:
    """Share the embedding model's tokenizer with M4; never fall back to fixtures."""
    strategy = (
        BlockChunkingStrategy()
        if candidate.lower() == "main"
        else get_chunking_candidate(candidate.upper()).strategy
    )
    try:
        from cs30.indexing.faiss_index import FaissIndexBuilder
    except ImportError as exc:
        raise IndexUnavailableError('Index building requires pip install -e ".[ml]"') from exc
    builder = FaissIndexBuilder(model_name=model_name, index_dir=str(index_dir))
    token_counter = builder.token_counter()
    strategy = _fit_strategy_to_embedding_limit(strategy, token_counter)
    return BuildDeps(
        parser=RealDocumentParser(chapters, source_url, download_date, textbook_id),
        chunker=BlockAwareChunker(strategy=strategy, token_counter=token_counter),
        index_builder=builder,
        # Verify persisted chunk-map loading without loading the embedding model twice.
        retriever=BM25Retriever(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="normalised textbook JSON or supported textbook PDF"
    )
    parser.add_argument("--index-dir", type=Path, required=True, help="New, empty output directory")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument(
        "--candidate", choices=["main", "S1", "S2", "S3", "S4", "S5", "S6"], default="main"
    )
    parser.add_argument("--chapters", nargs="+", default=[], help="PDF chapter numbers, e.g. 2 3 4")
    parser.add_argument("--source-url", default=RealDocumentParser.source_url)
    parser.add_argument(
        "--textbook",
        choices=list(TEXTBOOKS),
        default=DEFAULT_TEXTBOOK_ID,
        help="textbook metadata profile used for PDF input",
    )
    parser.add_argument("--download-date", default="")
    args = parser.parse_args(argv)
    cleanup_on_failure = False
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
        cleanup_on_failure = True
        # Third-party model loaders may print progress; stdout remains one JSON manifest.
        with contextlib.redirect_stdout(sys.stderr):
            deps = build_real_build_deps(
                index_dir=args.index_dir.resolve(),
                model_name=args.model,
                candidate=args.candidate,
                chapters=tuple(args.chapters),
                source_url=args.source_url,
                download_date=args.download_date,
                textbook_id=args.textbook,
            )
            artifact = run_build_pipeline(args.source, deps)
    except Exception as exc:
        if cleanup_on_failure:
            _remove_partial_outputs(args.index_dir)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(artifact.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
