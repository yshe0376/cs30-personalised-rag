"""Blind Dev review packets and strict import of actual human ratings."""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from cs30.evaluation.open_answer_models import HumanRating, OpenAnswerRubric, OpenAnswerRun
from cs30.evaluation.open_answer_scoring import canonical_hash, reference_spans, sha256_bytes
from cs30.v2.contracts import GoldQuestion


def write_review_packet(
    gold: Mapping[str, GoldQuestion],
    rubrics: Mapping[str, OpenAnswerRubric],
    runs: Sequence[OpenAnswerRun],
    output_dir: Path,
    *,
    question_count: int = 10,
    seed: int = 0,
) -> dict:
    """Sample question clusters, then include every answered cell in each cluster.

    No scores, conditions, models or student levels go into the rater materials.
    The mapping stays in a separate administrator file. Empty templates are not
    HumanRating records and are rejected by the rating importer until completed.
    """
    if output_dir.exists() or question_count < 1:
        raise ValueError("review output must be new and question_count must be positive")
    grouped = defaultdict(list)
    run_ids = set()
    for run in runs:
        if run.run_id in run_ids:
            raise ValueError("duplicate run ID in review input")
        run_ids.add(run.run_id)
        if run.question_id not in gold:
            raise ValueError("review run refers to unknown Gold")
        question = gold[run.question_id]
        if question.split.value != "dev" or question.options or question.answerable is not True:
            continue
        if run.status != "answered":
            continue
        if run.question_id not in rubrics:
            raise ValueError("review requires a rubric for every eligible question")
        grouped[run.question_id].append(run)
    if not grouped:
        raise ValueError("no answered, answerable open-ended Dev questions to sample")
    rng = random.Random(seed)
    question_ids = sorted(grouped)
    rng.shuffle(question_ids)
    selected = question_ids[:question_count]
    chosen = [run for qid in selected for run in sorted(grouped[qid], key=lambda r: r.run_id)]
    rng.shuffle(chosen)
    items, bindings = [], []
    for position, run in enumerate(chosen, 1):
        question, rubric = gold[run.question_id], rubrics[run.question_id]
        if rubric.question_id != question.question_id:
            raise ValueError("review rubric identity differs from Gold")
        item_id = f"item-{position:04d}"
        # Do not expose review IDs or filenames that can encode experimental metadata.
        items.append(
            {
                "item_id": item_id,
                "question": question.question,
                "answer": run.answer.explanation,
                "reference_answer": question.gold_answer_text,
                "criteria": [criterion.model_dump(mode="json") for criterion in rubric.criteria],
                "required_paths": rubric.required_paths,
                "full_credit_answers": rubric.full_credit_answers,
                "alias_case_sensitive": rubric.alias_case_sensitive,
                "numeric_target": rubric.numeric_target.model_dump(mode="json")
                if rubric.numeric_target
                else None,
                "reference_evidence": reference_spans(question),
                "scale": {"0": "错误或核心矛盾", "1": "部分正确", "2": "完整正确且无实质错误"},
            }
        )
        bindings.append(
            {
                "item_id": item_id,
                "run_id": run.run_id,
                "answer_sha256": sha256_bytes(run.answer.explanation.encode("utf-8")),
                "rubric_sha256": canonical_hash(rubric.model_dump(mode="json")),
            }
        )
    output_dir.mkdir(parents=True, exist_ok=False)
    item_bytes = ("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)).encode()
    (output_dir / "rater_items.jsonl").write_bytes(item_bytes)
    with (output_dir / "rating_form.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["item_id", "score", "note"])
        writer.writeheader()
        writer.writerows({"item_id": item["item_id"], "score": "", "note": ""} for item in items)
    admin = {
        "schema_version": "0.1",
        "result_type": "blind_dev_review_packet",
        "reportable": False,
        "seed": seed,
        "requested_question_count": question_count,
        "sampled_question_count": len(selected),
        "selected_question_ids": selected,
        "item_count": len(items),
        "rater_items_sha256": sha256_bytes(item_bytes),
        "bindings": bindings,
    }
    (output_dir / "administrator_mapping.json").write_text(
        json.dumps(admin, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        "# Dev 人工校准材料\n\n"
        "只向两名独立评阅者各发 rater_items.jsonl 与一份 rating_form.csv。"
        "administrator_mapping.json 由实验管理员保管。\n\n"
        "评分者独立查看完整答案、问题、参考答案及教材证据，在 CSV 中填入 0、1 或 2，"
        "并填写理由。不要提前交换意见。无法判定的项目保留空白并说明原因；"
        "有空白时不能导入为完整评分。此模板没有自动填写任何人工判断。\n\n"
        "评分量表是草稿时，先检查是否符合题意；量表修改后重新生成评分材料。"
        "两份已完成的评分表分别导入，再计算一致性并处理分歧。"
        "该样本不能用于宣称总体模型准确率，Test 不参加本轮抽样。\n",
        encoding="utf-8",
    )
    return admin


def import_rating_form(
    packet_dir: Path, form_path: Path, output_path: Path, *, rater_id: str
) -> list[HumanRating]:
    if output_path.exists() or not rater_id.strip():
        raise ValueError("rating output must be new and rater_id must be nonblank")
    admin = json.loads((packet_dir / "administrator_mapping.json").read_text(encoding="utf-8"))
    if (
        admin.get("schema_version") != "0.1"
        or admin.get("result_type") != "blind_dev_review_packet"
    ):
        raise ValueError("unsupported review packet")
    if sha256_bytes((packet_dir / "rater_items.jsonl").read_bytes()) != admin["rater_items_sha256"]:
        raise ValueError("rater materials changed after packet preparation")
    bindings = {item["item_id"]: item for item in admin["bindings"]}
    if not bindings or len(bindings) != len(admin["bindings"]):
        raise ValueError("review packet has empty or duplicate bindings")
    result, seen = [], set()
    with form_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["item_id", "score", "note"]:
            raise ValueError("rating form must have exactly item_id,score,note columns")
        for row in reader:
            item_id = row["item_id"]
            if item_id not in bindings or item_id in seen:
                raise ValueError("rating form contains an unknown or duplicate item")
            seen.add(item_id)
            if row["score"] not in {"0", "1", "2"} or not (row["note"] or "").strip():
                raise ValueError("every sampled item needs an actual 0/1/2 rating and reason")
            binding = bindings[item_id]
            result.append(
                HumanRating(
                    run_id=binding["run_id"],
                    answer_sha256=binding["answer_sha256"],
                    rubric_sha256=binding["rubric_sha256"],
                    rater_id=rater_id,
                    score=int(row["score"]),
                    note=row["note"],
                )
            )
    if seen != set(bindings):
        raise ValueError("rating form is missing sampled items")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write("".join(item.model_dump_json() + "\n" for item in result))
    return result
