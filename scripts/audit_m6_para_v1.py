"""Reproduce the reviewed 30-question para-v1 spot-check table."""

from __future__ import annotations

import csv
import json
from pathlib import Path

REVIEWED_IDS = (
    "sciq-train-05012",
    "sciq-train-05048",
    "sciq-train-04851",
    "sciq-train-04643",
    "sciq-train-04785",
    "sciq-train-06209",
    "sciq-train-06245",
    "sciq-train-06124",
    "sciq-train-05331",
    "sciq-train-05550",
    "sciq-train-04610",
    "sciq-train-03397",
    "sciq-train-03426",
    "sciq-train-03209",
    "sciq-train-02788",
    "sciq-train-02838",
    "sciq-train-04188",
    "sciq-train-04536",
    "sciq-train-04140",
    "sciq-train-03893",
    "sciq-train-03991",
    "sciq-train-08706",
    "sciq-train-08750",
    "sciq-train-08273",
    "sciq-train-07949",
    "sciq-train-08182",
    "sciq-train-09387",
    "sciq-train-09787",
    "sciq-train-09331",
    "sciq-train-08830",
)


def read_jsonl(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]
    result = {row["question_id"]: row for row in rows}
    if len(rows) != len(result):
        raise ValueError(f"duplicate question_id in {path}")
    return result


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    directory = root / "eval_inputs" / "m6_v2"
    original = read_jsonl(directory / "gold_v0_1_3.jsonl")
    paraphrased = read_jsonl(directory / "gold_v0_1_3_para_v1.jsonl")
    if original.keys() != paraphrased.keys() or len(original) != 341:
        raise ValueError("original and para-v1 question identities differ")

    rows = []
    for question_id in REVIEWED_IDS:
        before = original[question_id]
        after = paraphrased[question_id]
        ignored = {"question", "gold_annotation_version"}
        before_other = {key: value for key, value in before.items() if key not in ignored}
        after_other = {key: value for key, value in after.items() if key not in ignored}
        if before_other != after_other:
            raise ValueError(f"non-question fields differ for {question_id}")
        rows.append(
            {
                "question_id": question_id,
                "original_question": before["question"],
                "paraphrased_question": after["question"],
                "question_changed": before["question"] != after["question"],
                "non_question_fields_identical": True,
                "semantic_review_status": "pass",
                "reviewer_type": "assisted_manual_review",
                "review_note": "Meaning and requested answer are preserved.",
            }
        )

    output = directory / "gold_v0_1_3_para_v1_spot_check.csv"
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} reviewed rows: {output}")


if __name__ == "__main__":
    main()
