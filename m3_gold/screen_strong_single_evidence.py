"""Automatically collect 40 high-overlap single-evidence candidates with resume support."""

from __future__ import annotations

import argparse
from pathlib import Path

from candidate_screening_common import DEFAULT_BLOCKS, DEFAULT_DATA, screen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path(__file__).with_name("candidate_pool_strong_v1_3_2.csv")
DEFAULT_CHECKPOINT = Path(__file__).with_name("candidate_pool_strong_v1_3_2.checkpoint.json")


def is_strong(candidate: dict[str, str]) -> bool:
    return (
        bool(candidate["sciq_support"].strip())
        and
        candidate["top_answer_exact"] == "True"
        and candidate["multi_block_candidate"] == "False"
        and float(candidate["support_token_overlap"]) >= 0.80
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--max-questions", type=int)
    parser.add_argument(
        "--target-total",
        type=int,
        default=40,
        help="total candidates desired, including candidates already in the checkpoint",
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--blocks", type=Path, default=DEFAULT_BLOCKS)
    parser.add_argument("--reset", action="store_true", help="start a fresh scan")
    args = parser.parse_args()
    screen(
        target=args.target_total,
        output=args.output,
        checkpoint=args.checkpoint,
        predicate=is_strong,
        bucket="strong_single_evidence",
        reset=args.reset,
        max_questions=args.max_questions,
        data_dir=args.data_dir,
        blocks_path=args.blocks,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
