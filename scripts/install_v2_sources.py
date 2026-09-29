"""Install the pinned v2 textbook sources, from a GitHub Release or from disk.

Real builds read M2's parsed delivery (the default format). The pinned PDFs are
only needed to re-parse from source. The catalogue pins every file's SHA-256,
so each one is verified while it is read and a local file with different
content is never overwritten.

    python scripts/install_v2_sources.py                       # M2's parse, from its Release
    python scripts/install_v2_sources.py --from-archive openstax_parser_v1_3_2_r1.zip
    python scripts/install_v2_sources.py --format raw --from-dir ~/Downloads
    python scripts/install_v2_sources.py --format raw --print-sha256sums
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cs30.v2.errors import V2Error  # noqa: E402, I001
from cs30.v2.sources import (  # noqa: E402
    DEFAULT_DESTINATION,
    DEFAULT_PARSED_DESTINATION,
    DEFAULT_RELEASE_TAG,
    PARSED_RELEASE_TAG,
    install_from_directory,
    install_from_release,
    install_parsed_from_archive,
    install_parsed_from_release,
    missing_parsed_sources,
    missing_sources,
    pinned_parsed_sources,
    pinned_sources,
    sha256sums_text,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--format",
        choices=["parsed", "raw"],
        default="parsed",
        help="parsed: M2's openstax_document.json per book (default); raw: the PDFs",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help=(
            f"where the sources are installed (default: {DEFAULT_PARSED_DESTINATION} "
            f"for parsed, {DEFAULT_DESTINATION} for raw)"
        ),
    )
    parser.add_argument(
        "--tag",
        default=None,
        help=(
            f"Release tag holding the sources (default: {PARSED_RELEASE_TAG} for "
            f"parsed, {DEFAULT_RELEASE_TAG} for raw)"
        ),
    )
    parser.add_argument(
        "--from-archive",
        type=Path,
        default=None,
        help="parsed only: install from a local copy of M2's delivery archive",
    )
    parser.add_argument(
        "--from-dir",
        type=Path,
        default=None,
        help="raw only: install from PDFs already on disk instead of downloading them",
    )
    parser.add_argument(
        "--print-sha256sums",
        action="store_true",
        help="raw only: print the SHA256SUMS body for the PDF Release and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argument_parser = build_argument_parser()
    args = argument_parser.parse_args(argv)
    parsed = args.format == "parsed"
    if parsed and (args.from_dir is not None or args.print_sha256sums):
        argument_parser.error("--from-dir and --print-sha256sums need --format raw")
    if not parsed and args.from_archive is not None:
        argument_parser.error("--from-archive needs --format parsed")
    if args.print_sha256sums:
        print(sha256sums_text(), end="")
        return 0

    destination = args.dest or (DEFAULT_PARSED_DESTINATION if parsed else DEFAULT_DESTINATION)
    pins = pinned_parsed_sources() if parsed else pinned_sources()
    kind = "parsed" if parsed else "PDF"
    print(f"{len(pins)} pinned {kind} source(s): {', '.join(sorted(pins))}")
    try:
        if parsed and args.from_archive is not None:
            installed = install_parsed_from_archive(args.from_archive, destination)
        elif parsed:
            installed = install_parsed_from_release(
                destination, tag=args.tag or PARSED_RELEASE_TAG
            )
        elif args.from_dir is not None:
            installed, unmatched = install_from_directory(args.from_dir, destination)
            for path in unmatched:
                print(f"  ignored (matches no pinned hash): {path}")
        else:
            installed = install_from_release(destination, tag=args.tag or DEFAULT_RELEASE_TAG)
    except V2Error as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return exc.exit_code

    for source in installed:
        print(f"  {source.status}: {source.path} ({source.sha256[:16]}…)")
    still_missing = (
        missing_parsed_sources(destination) if parsed else missing_sources(destination)
    )
    if still_missing:
        print(
            f"missing pinned {kind} source(s): " + ", ".join(still_missing),
            file=sys.stderr,
        )
        return 1
    print(f"all pinned {kind} sources are installed under {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
