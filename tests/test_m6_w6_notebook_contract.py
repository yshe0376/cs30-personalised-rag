from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "M6_W6_v2_retrieval_dev_test_full.ipynb"


def _source() -> str:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell["cell_type"] in {"code", "markdown"}
    )


def test_notebook_uses_one_shared_retriever_for_both_query_sets() -> None:
    source = _source()

    assert 'CS30_M6_QUERY_SET", "original"' in source
    assert 'QUERY_SET in {"original", "para_v1"}' in source
    assert "build_real_retrieval_deps" in source
    assert "def bm25_search" not in source
    assert "def weighted_rrf" not in source
    assert "57ca94918912df01d8d66e6e9e7fed95b3faf4e6dd4254428b349823a3623696" in source


def test_notebook_records_joint_rule_and_limited_exposed_holdout() -> None:
    source = _source()

    assert 'SYSTEM_RETRIEVER_MODEL = "bge_m3"' in source
    assert 'SYSTEM_RETRIEVER_MODE = "hybrid_d0.10_b0.90"' in source
    assert "selected_by_team_after_joint_robustness_review" in source
    assert "rule1_metric_winner" in source
    assert "dev_rule1_selection.csv" in source
    assert "dev_paired_bm25_vs_bge_m3_questions.csv" in source
    assert '"diagnostic_holdout_configuration_count": 2' in source
    assert "team-selected provisional" not in source


def test_notebook_exports_original_query_top20_for_member_7() -> None:
    source = _source()

    assert "m7_bge_m3_d0.10_b0.90_original_top20.jsonl" in source
    assert 'm7_retriever.retrieve(question["question"], RRF_INPUT_TOP_K)' in source
    for field in (
        "provider",
        "textbook_id",
        "document_id",
        "chapter_id",
        "source_name",
        "page_or_location",
        "source_locator",
        "text",
    ):
        assert f'"{field}"' in source
