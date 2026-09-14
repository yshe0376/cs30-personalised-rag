import json
from pathlib import Path

from cs30.evaluation import load_gold_samples

ROOT = Path(__file__).resolve().parents[1]


def test_m3_gold_v0_1_1_loads_with_main_loader() -> None:
    samples = load_gold_samples(ROOT / "m3_gold" / "gold_v0_1_1.jsonl")

    assert len(samples) in {19, 20}


def test_m3_gold_v0_1_1_replays_against_unified_source_document() -> None:
    document = json.loads(
        (ROOT / "m3_unified_source_corpus/source_corpus/openstax_document.json").read_text(
            encoding="utf-8"
        )
    )

    samples = load_gold_samples(
        ROOT / "m3_gold" / "gold_v0_1_1.jsonl",
        documents={document["document_id"]: document["text"]},
    )

    assert len(samples) in {19, 20}
