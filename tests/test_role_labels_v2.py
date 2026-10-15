"""Tests for the v2 Evidence Role labelling workflow script."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cs30.generation.lambda_search import load_role_label_package
from scripts import role_labels_v2 as roles


def _write_corpus(directory: Path, texts: dict[str, str]) -> Path:
    directory.mkdir(parents=True)
    records = "".join(
        json.dumps(
            {
                "chunk_id": chunk_id,
                "textbook_id": "book",
                "section_id": "1.1",
                "section_title": "Section",
                "content_types": ["body"],
                "text": text,
            }
        )
        + "\n"
        for chunk_id, text in texts.items()
    )
    (directory / "records.jsonl").write_text(records, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(records.encode("utf-8")).hexdigest()
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "corpus_version": "test-corpus",
                "corpus_hash": f"sha256:{digest}",
                "records_relpath": "records.jsonl",
                "record_count": len(texts),
            }
        ),
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    return _write_corpus(
        tmp_path / "corpus",
        {
            "c1": "Force is defined as a push or a pull.",
            "c2": "Example 2.1 A car accelerates at 3 m/s^2 for 4 s.",
            "c3": "This result is valid only when v is much less than c.",
        },
    )


def _common(corpus_dir: Path, out_dir: Path) -> list[str]:
    return ["--corpus-dir", str(corpus_dir), "--out-dir", str(out_dir)]


def test_parse_answer_accepts_numbers_names_unsure_and_notes() -> None:
    assert roles.parse_answer("2") == roles.Answer("label", role="example")
    assert roles.parse_answer("app") == roles.Answer("label", role="application")
    assert roles.parse_answer("4? mostly a device") == roles.Answer(
        "label", role="application", unsure=True, note="mostly a device"
    )
    assert roles.parse_answer("?").action == "help"
    assert roles.parse_answer("b").action == "back"
    assert roles.parse_answer("de").action == "invalid"  # definition or derivation
    assert roles.parse_answer("7").action == "invalid"


def test_choose_sample_is_deterministic_and_seeded() -> None:
    ids = [f"chunk-{number}" for number in range(100)]
    first = roles.choose_sample(ids, 10, "seed-a")
    assert first == roles.choose_sample(list(reversed(ids)), 10, "seed-a")
    assert first != roles.choose_sample(ids, 10, "seed-b")
    assert len(set(first)) == 10


def test_agreement_report_matches_hand_computed_values() -> None:
    report = roles.agreement_report(
        ["definition", "definition", "example", "example"],
        ["definition", "example", "example", "example"],
    )
    assert report["accuracy"] == pytest.approx(0.75)
    assert report["cohen_kappa"] == pytest.approx(0.5)
    assert report["per_role"]["definition"]["recall"] == pytest.approx(0.5)
    assert report["per_role"]["example"]["precision"] == pytest.approx(2 / 3)
    assert report["per_role"]["boundary"]["f1"] is None
    assert report["macro_f1"] == pytest.approx((2 / 3 + 0.8) / 2)


def test_latest_label_wins_and_human_overrides_llm(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    roles.append_jsonl(path, {"chunk_id": "c1", "role": "example"})
    roles.append_jsonl(path, {"chunk_id": "c1", "role": "definition"})
    human = roles.usable(roles.latest_labels(path))
    llm = {
        "c1": {"role": "boundary", "model": "m"},
        "c2": {"role": "example", "model": "m"},
    }
    rows, missing = roles.build_package_rows(["c1", "c2", "c3"], human, llm)
    assert [(row["chunk_id"], row["role"], row["label_source"]) for row in rows] == [
        ("c1", "definition", "human"),
        ("c2", "example", "llm:m"),
    ]
    assert missing == ["c3"]


def test_repository_taxonomy_keeps_member7_role_names() -> None:
    taxonomy = roles.load_taxonomy(roles.DEFAULT_TAXONOMY)
    assert tuple(role["role"] for role in taxonomy.roles) == roles.ROLES


def test_prompt_includes_every_decision_rule() -> None:
    taxonomy = roles.load_taxonomy(roles.DEFAULT_TAXONOMY)
    assert taxonomy.rules
    prompt = roles.build_prompt(taxonomy, {"text": "Force is a push.", "content_types": []})
    assert all(f"- {rule}\n" in prompt for rule in taxonomy.rules)
    assert prompt.endswith("Chunk text:\nForce is a push.")


def test_annotate_saves_each_answer_and_supports_back(
    corpus_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "out"
    roles.main(["sample", *_common(corpus_dir, out_dir), "--size", "3",
                "--output", str(out_dir / "sample.json")])
    answers = iter(["2", "b", "1? short", "s", "q"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    roles.main(["annotate", *_common(corpus_dir, out_dir), "--annotator", "tester",
                "--scope", str(out_dir / "sample.json"), "--no-clear"])
    sample = json.loads((out_dir / "sample.json").read_text(encoding="utf-8"))["chunk_ids"]
    labels = roles.latest_labels(out_dir / "human_labels_tester.jsonl")
    assert list(labels) == [sample[0]]
    assert labels[sample[0]]["role"] == "definition"
    assert labels[sample[0]]["unsure"] is True
    assert labels[sample[0]]["note"] == "short"


def test_llm_label_resumes_and_writes_review_queue(
    corpus_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = tmp_path / "out"
    calls: list[str] = []

    def fake_call(**kwargs: object) -> tuple[dict[str, str], float, int]:
        prompt = str(kwargs["prompt"])
        calls.append(prompt)
        if "valid only when" in prompt:
            return {"role": "boundary", "confidence": "high",
                    "evidence_quote": "valid only when v is much less than c"}, 0.1, 100
        return {"role": "definition", "confidence": "medium",
                "evidence_quote": "not in the text"}, 0.1, 100

    monkeypatch.setattr(roles, "check_ollama", lambda base_url, model: None)
    monkeypatch.setattr(roles, "call_ollama", fake_call)
    argv = ["llm-label", *_common(corpus_dir, out_dir), "--scope", "all", "--model", "fake:1b"]
    roles.main(argv)
    assert len(calls) == 3
    roles.main(argv)
    assert len(calls) == 3  # nothing re-labelled on resume

    labels = roles.latest_labels(out_dir / "llm_labels_fake-1b.jsonl")
    assert labels["c3"]["quote_verified"] is True
    queue = (out_dir / "llm_review_queue_fake-1b.txt").read_text(encoding="utf-8")
    queued = [line for line in queue.splitlines() if not line.startswith("#")]
    assert queued == ["c1", "c2"]


def test_export_writes_a_package_member7_can_load(corpus_dir: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    taxonomy = roles.load_taxonomy(roles.DEFAULT_TAXONOMY)
    llm_path = out_dir / "llm.jsonl"
    for chunk_id, role in (("c1", "definition"), ("c2", "example"), ("c3", "boundary")):
        roles.append_jsonl(llm_path, {"chunk_id": chunk_id, "role": role, "model": "fake",
                                      "taxonomy_sha256": taxonomy.sha256})
    human_path = out_dir / "human.jsonl"
    roles.append_jsonl(human_path, {"chunk_id": "c2", "role": "application",
                                    "annotator": "tester",
                                    "taxonomy_sha256": taxonomy.sha256})

    roles.main(["export", *_common(corpus_dir, out_dir), "--llm", str(llm_path),
                "--human", str(human_path)])

    manifest_path = out_dir / "role_labels_v2_provenance_manifest.json"
    package = load_role_label_package(manifest_path, expected_taxonomy_version=taxonomy.version)
    assert package.manifest.reference_universe == "corpus_records"
    assert package.manifest.annotator_ids == ["tester"]
    assert {chunk_id: label.roles[0].value for chunk_id, label in package.labels.items()} == {
        "c1": "definition",
        "c2": "application",
        "c3": "boundary",
    }


def test_advanced_candidate_uses_text_cues_and_llm_labels() -> None:
    derivation = {"text": "[EQUATION: W = Fd] Substituting F = PA, we obtain "
                          "[EQUATION: W = PAd] and thus W = P dV."}
    worked = {"text": "Strategy Use [EQUATION: x = vt]. Solution Substituting gives "
                      "[EQUATION: x = 4 m], thus x = 4 m."}
    boundary = {"text": "This is valid only when v is much less than c."}
    plain = {"text": "Force is a push or a pull."}
    assert roles.advanced_candidate(derivation)
    assert not roles.advanced_candidate(worked)
    assert roles.advanced_candidate(boundary)
    assert not roles.advanced_candidate(plain)
    assert roles.advanced_candidate(plain, "boundary")


def test_export_ranks_human_then_review_then_llm(corpus_dir: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    taxonomy = roles.load_taxonomy(roles.DEFAULT_TAXONOMY)
    stamp = {"taxonomy_sha256": taxonomy.sha256}
    llm_path, review_path, human_path = (out_dir / f"{name}.jsonl"
                                         for name in ("llm", "review", "human"))
    for chunk_id in ("c1", "c2", "c3"):
        roles.append_jsonl(llm_path, {"chunk_id": chunk_id, "role": "definition",
                                      "model": "small", **stamp})
    for chunk_id in ("c2", "c3"):
        roles.append_jsonl(review_path, {"chunk_id": chunk_id, "role": "derivation",
                                         "model": "big", **stamp})
    roles.append_jsonl(human_path, {"chunk_id": "c3", "role": "boundary",
                                    "annotator": "tester", **stamp})

    roles.main(["export", *_common(corpus_dir, out_dir), "--llm", str(llm_path),
                "--review", str(review_path), "--human", str(human_path)])

    rows = roles.read_jsonl(out_dir / "role_labels_v2.jsonl")
    assert [(row["chunk_id"], row["role"], row["label_source"]) for row in rows] == [
        ("c1", "definition", "llm:small"),
        ("c2", "derivation", "review:big"),
        ("c3", "boundary", "human"),
    ]


def test_export_refuses_missing_labels_unless_allowed(corpus_dir: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    taxonomy = roles.load_taxonomy(roles.DEFAULT_TAXONOMY)
    llm_path = out_dir / "llm.jsonl"
    roles.append_jsonl(llm_path, {"chunk_id": "c1", "role": "definition", "model": "fake",
                                  "taxonomy_sha256": taxonomy.sha256})
    argv = ["export", *_common(corpus_dir, out_dir), "--llm", str(llm_path),
            "--annotator", "tester"]
    with pytest.raises(SystemExit, match="2 of 3 chunks have no label"):
        roles.main(argv)
    roles.main([*argv, "--allow-incomplete"])
    report = json.loads(
        (out_dir / "role_labels_v2_export_report.json").read_text(encoding="utf-8")
    )
    assert report["complete"] is False
    assert report["missing_count"] == 2
