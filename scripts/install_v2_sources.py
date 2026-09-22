"""Install the pinned v2 textbook PDFs, from the GitHub Release or a local folder.

The catalogue pins each PDF's SHA-256, so every file is verified while it is
read and a local file with different content is never overwritten.

    python scripts/install_v2_sources.py                       # from the Release
    python scripts/install_v2_sources.py --from-dir ~/Downloads
    python scripts/install_v2_sources.py --print-sha256sums    # for the Release
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cs30.v2.errors import V2Error  # noqa: E402, I001
from cs30.v2.sources import (  # noqa: E402
    DEFAULT_DESTINATION,
    DEFAULT_RELEASE_TAG,
    install_from_directory,
    install_from_release,
    missing_sources,
    pinned_sources,
    sha256sums_text,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DESTINATION,
        help=f"where the PDFs are installed (default: {DEFAULT_DESTINATION})",
    )
    parser.add_argument(
        "--tag",
        default=DEFAULT_RELEASE_TAG,
        help=f"Release tag holding the PDFs (default: {DEFAULT_RELEASE_TAG})",
    )
    parser.add_argument(
        "--from-dir",
        type=Path,
        default=None,
        help="install from PDFs already on disk instead of downloading them",
    )
    parser.add_argument(
        "--print-sha256sums",
        action="store_true",
        help="print the SHA256SUMS body for the Release and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    if args.print_sha256sums:
        print(sha256sums_text(), end="")
        return 0

    pins = pinned_sources()
    print(f"{len(pins)} pinned textbook source(s): {', '.join(sorted(pins))}")
    try:
        if args.from_dir is not None:
            installed, unmatched = install_from_directory(args.from_dir, args.dest)
            for path in unmatched:
                print(f"  ignored (matches no pinned hash): {path}")
        else:
            installed = install_from_release(args.dest, tag=args.tag)
    except V2Error as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return exc.exit_code

    for source in installed:
        print(f"  {source.status}: {source.path} ({source.sha256[:16]}…)")
    still_missing = missing_sources(args.dest)
    if still_missing:
        print(
            "missing pinned source(s): " + ", ".join(still_missing),
            file=sys.stderr,
        )
        return 1
    print(f"all pinned sources are installed under {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
