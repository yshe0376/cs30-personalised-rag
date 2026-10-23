"""Execute the M6 W6 four-book retrieval notebook with UTF-8-safe I/O."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-models",
        action="store_true",
        help="Run all nine embedding models instead of the default provenance preflight.",
    )
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument(
        "--query-set",
        choices=("original", "para_v1"),
        default="original",
        help="Evaluate original Gold questions or the para-v1 robustness queries.",
    )
    parser.add_argument(
        "--gold",
        type=Path,
        help="Optional active Gold JSONL override; required when para-v1 is external.",
    )
    parser.add_argument(
        "--original-gold",
        type=Path,
        help="Optional original Gold JSONL override used for cross-query-set identity checks.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Optional shared work directory for indexes, checkpoints, and measured outputs.",
    )
    parser.add_argument("--timeout", type=int, default=7200, help="Per-cell timeout in seconds.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output notebook; the source notebook is overwritten when omitted.",
    )
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    source = repository / "M6_W6_v2_retrieval_dev_test_full.ipynb"
    output = args.output.resolve() if args.output else source

    os.environ["CS30_M6_RUN_MODELS"] = "1" if args.run_models else "0"
    os.environ["CS30_M6_DEVICE"] = args.device
    os.environ["CS30_M6_QUERY_SET"] = args.query_set
    if args.gold:
        os.environ["CS30_M6_GOLD"] = str(args.gold.resolve())
    if args.original_gold:
        os.environ["CS30_M6_ORIGINAL_GOLD"] = str(args.original_gold.resolve())
    if args.work_dir:
        os.environ["CS30_M6_WORK_DIR"] = str(args.work_dir.resolve())

    notebook = nbformat.read(source, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    client = NotebookClient(
        notebook,
        timeout=args.timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(repository)}},
    )
    try:
        client.execute()
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        nbformat.write(notebook, output)
        print(f"Executed notebook saved: {output}")


if __name__ == "__main__":
    main()
