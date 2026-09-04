"""Generate the Week 1 task-7 smoke artifacts from fixed, non-evaluation data."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from cs30.contracts import RetrievalHit, RetrievalMode, RetrievalResult, StudentLevel
from cs30.logging import get_logger
from cs30.profile import Week1ProfileProvider

from .batch import BatchItem, generate_batch
from .client import MockJsonLLMClient, OllamaChatClient, OpenAIResponsesClient
from .generator import PersonalisedAnswerGenerator
from .sciq_smoke import (
    build_free_question_items,
    build_sciq_smoke_items,
    load_packaged_free_questions,
    load_packaged_sciq_questions,
    load_sciq_questions,
)

FIXTURE_NOTICE = (
    "Task-7 fixture smoke data only. This output validates the engineering path "
    "and must not be reported as retrieval or model-effectiveness evidence."
)

SCIQ_FIXTURE_NOTICE = (
    "Real SciQ questions with SciQ support wrapped as fixture evidence. This validates "
    "the task-7 engineering path only and is not a real retrieval or effectiveness result."
)

ALL_DATASETS_NOTICE = (
    "Combined Task-7 smoke data: original fixture questions, Member 3 packaged "
    "questions, and local SciQ rows when available. Evidence remains fixture-labelled; "
    "this is not a retrieval or model-effectiveness result."
)

DEFAULT_LOCAL_SCIQ_PATH = Path(
    os.environ.get("CS30_LOCAL_SCIQ_PATH", "data/raw/sciq/train_first_20.json")
)

LOGGER = get_logger("generation.demo")

ORIGINAL_DATASET = "member7-original-fixture"
TEAM_SCIQ_DATASET = "member3-packaged-sciq"
TEAM_FREE_DATASET = "member3-packaged-free"
LOCAL_SCIQ_DATASET = "member7-local-sciq"


@dataclass(frozen=True)
class DemoDataset:
    items: list[BatchItem]
    sources: dict[str, str]
    gold_choices: dict[str, str]


# The evidence is deliberately small and labelled fixture://. Option A is supported
# in every item so the deterministic mock checks structure without claiming accuracy.
_CASES = [
    (
        "Acceleration is best described as:",
        "The rate of change of velocity",
        "The rate of change of position only",
        "The amount of matter",
        "The energy stored in an object",
        "Acceleration is the rate at which velocity changes with time.",
    ),
    (
        "Newton's first law states that an object remains at rest or in uniform motion when:",
        "The net external force is zero",
        "Its acceleration is always positive",
        "Its mass becomes zero",
        "Its kinetic energy is maximum",
        "With zero net external force, an object's velocity remains constant.",
    ),
    (
        "According to Newton's second law, net force equals:",
        "Mass multiplied by acceleration",
        "Mass divided by acceleration",
        "Velocity multiplied by time",
        "Momentum divided by distance",
        "Newton's second law relates net force to mass and acceleration: F = ma.",
    ),
    (
        "Near Earth's surface, the weight of an object is:",
        "Its mass multiplied by gravitational acceleration",
        "Its mass divided by gravitational acceleration",
        "Independent of gravity",
        "The same quantity as density",
        "Weight is the gravitational force on an object and is given by W = mg.",
    ),
    (
        "Linear momentum is defined as:",
        "Mass multiplied by velocity",
        "Force multiplied by distance",
        "Mass multiplied by acceleration",
        "Energy divided by time",
        "The linear momentum of a particle is the product p = mv.",
    ),
    (
        "The translational kinetic energy of a mass m moving at speed v is:",
        "One half m times v squared",
        "m times v",
        "m divided by v squared",
        "Force times time",
        "Translational kinetic energy is K = one half of m multiplied by v squared.",
    ),
    (
        "For a constant force parallel to displacement, work equals:",
        "Force multiplied by displacement",
        "Force divided by displacement",
        "Mass multiplied by time",
        "Power multiplied by speed",
        "When force and displacement are parallel, work is W = Fd.",
    ),
    (
        "Average power measures:",
        "Work done per unit time",
        "Force per unit area",
        "Energy per unit mass",
        "Momentum per unit distance",
        "Average power is the work performed divided by the elapsed time.",
    ),
    (
        "Near Earth's surface, gravitational potential energy changes by:",
        "Mass times gravitational acceleration times height change",
        "Mass times speed",
        "Force divided by height",
        "Pressure times volume only",
        "Near Earth's surface the change in gravitational potential energy is m g delta h.",
    ),
    (
        "Mass density is:",
        "Mass per unit volume",
        "Volume per unit mass",
        "Force per unit area",
        "Energy per unit time",
        "Density is defined as the mass contained in a unit volume.",
    ),
    (
        "Pressure is defined as:",
        "Normal force per unit area",
        "Mass per unit volume",
        "Work per unit time",
        "Charge per unit time",
        "Pressure is the magnitude of normal force divided by the area over which it acts.",
    ),
    (
        "The period of a repeating motion is:",
        "The time for one complete cycle",
        "The number of cycles per second",
        "The maximum displacement",
        "The speed of the wave",
        "The period is the time required for one complete cycle of a periodic motion.",
    ),
    (
        "For a periodic wave, wave speed equals:",
        "Frequency multiplied by wavelength",
        "Frequency divided by wavelength",
        "Amplitude multiplied by period",
        "Wavelength divided by amplitude",
        "Wave speed, frequency, and wavelength satisfy v = f lambda.",
    ),
    (
        "Electric current measures:",
        "Charge passing a point per unit time",
        "Energy stored per unit mass",
        "Force acting per unit charge only",
        "Resistance multiplied by area",
        "Electric current is the rate at which charge passes a point in a circuit.",
    ),
    (
        "Ohm's law for an ohmic element is:",
        "Voltage equals current multiplied by resistance",
        "Voltage equals current divided by resistance",
        "Resistance equals voltage multiplied by current",
        "Power equals resistance divided by current",
        "For an ohmic element, potential difference, current, and resistance satisfy V = IR.",
    ),
    (
        "For resistors connected in series, the equivalent resistance is:",
        "The sum of the individual resistances",
        "Less than every individual resistance",
        "Always zero",
        "The product of current and voltage",
        "Series resistances add directly to give the equivalent resistance.",
    ),
    (
        "The law of reflection states that:",
        "The angle of incidence equals the angle of reflection",
        "Light never changes direction",
        "The reflected angle is always zero",
        "Frequency equals wavelength",
        "For reflection from a surface, the angle of incidence equals the angle of reflection.",
    ),
    (
        "Refraction occurs because light:",
        "Changes speed when it enters a different medium",
        "Always stops at a boundary",
        "Loses all its frequency",
        "Becomes an electric current",
        (
            "Light changes speed on entering a medium with a different refractive "
            "index, causing bending."
        ),
    ),
    (
        "Temperature is most directly related to:",
        "The thermal state that determines heat-transfer direction",
        "The total number of atoms only",
        "The object's volume only",
        "Its electric resistance only",
        (
            "Temperature characterises thermal state, and spontaneous heat transfer "
            "is from hotter to colder."
        ),
    ),
    (
        "Specific heat capacity is the energy required to:",
        "Raise one unit mass of a substance by one degree",
        "Move one coulomb through one volt",
        "Accelerate any mass by one metre per second squared",
        "Complete one wave cycle",
        (
            "Specific heat capacity is the energy needed per unit mass per degree "
            "of temperature change."
        ),
    ),
]


def build_demo_items(level: StudentLevel) -> list[BatchItem]:
    profile = Week1ProfileProvider(profile_prefix="task7-smoke").get(level)
    items = []
    for number, case in enumerate(_CASES, start=1):
        stem, option_a, option_b, option_c, option_d, evidence = case
        question_id = f"task7_smoke_{number:03d}"
        question = (
            f"{stem}\nA. {option_a}\nB. {option_b}\nC. {option_c}\nD. {option_d}"
        )
        hit = RetrievalHit(
            chunk_id=f"fixture_chunk_{number:03d}",
            text=evidence,
            chapter_id=f"fixture_ch_{((number - 1) // 5) + 1:02d}",
            source="fixture://task7-smoke/openstax-style-physics",
            score=1.0,
            rank=1,
            retriever_type=RetrievalMode.FIXTURE,
        )
        items.append(
            BatchItem(
                question_id=question_id,
                question=question,
                profile=profile,
                retrieval=RetrievalResult(
                    query=question,
                    mode=RetrievalMode.FIXTURE,
                    hits=[hit],
                ),
            )
        )
    return items


def build_all_dataset_items(
    level: StudentLevel,
    *,
    local_sciq_path: Path | None = DEFAULT_LOCAL_SCIQ_PATH,
) -> DemoDataset:
    """Combine original, teammate, and local datasets with stable provenance."""

    items: list[BatchItem] = []
    sources: dict[str, str] = {}
    gold_choices: dict[str, str] = {}
    seen_ids: set[str] = set()
    seen_questions: set[str] = set()

    def add(new_items: list[BatchItem], source: str) -> None:
        for item in new_items:
            normalised_question = " ".join(item.question.split()).casefold()
            if item.question_id in seen_ids or normalised_question in seen_questions:
                continue
            seen_ids.add(item.question_id)
            seen_questions.add(normalised_question)
            items.append(item)
            sources[item.question_id] = source

    add(build_demo_items(level), ORIGINAL_DATASET)

    team_sciq = load_packaged_sciq_questions()
    add(build_sciq_smoke_items(team_sciq, level), TEAM_SCIQ_DATASET)
    gold_choices.update(
        {
            question.question_id: question.correct_choice
            for question in team_sciq
            if question.question_id in sources
        }
    )

    team_free = load_packaged_free_questions()
    add(build_free_question_items(team_free, level), TEAM_FREE_DATASET)

    if local_sciq_path is not None:
        if local_sciq_path.is_file():
            local_sciq = load_sciq_questions(local_sciq_path)
            add(build_sciq_smoke_items(local_sciq, level), LOCAL_SCIQ_DATASET)
            gold_choices.update(
                {
                    question.question_id: question.correct_choice
                    for question in local_sciq
                    if question.question_id in sources
                }
            )
        else:
            LOGGER.warning(
                "local SciQ dataset not found at %s; running with %d packaged "
                "dataset sources",
                local_sciq_path,
                len(set(sources.values())),
            )

    return DemoDataset(items=items, sources=sources, gold_choices=gold_choices)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Task 7 Week 1 smoke generation")
    parser.add_argument("--provider", choices=["mock", "ollama", "openai"], default="mock")
    parser.add_argument("--model", default=None, help="Model name; falls back to LLM_MODEL")
    parser.add_argument(
        "--level",
        choices=[level.value for level in StudentLevel],
        default=StudentLevel.INTERMEDIATE.value,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of questions to run; defaults to every selected item",
    )
    parser.add_argument(
        "--dataset",
        choices=["all", "original", "team", "local-sciq"],
        default="all",
        help="Dataset group to run; defaults to every available dataset",
    )
    parser.add_argument(
        "--sciq-json",
        type=Path,
        default=None,
        help=(
            "Local Hugging Face rows JSON. Included by --dataset all and required by "
            "--dataset local-sciq; defaults to CS30_LOCAL_SCIQ_PATH or "
            "data/raw/sciq/train_first_20.json"
        ),
    )
    parser.add_argument(
        "--skip-three-level",
        action="store_true",
        help="Skip the additional beginner/intermediate/advanced comparison",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/task7"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    level = StudentLevel(args.level)
    local_sciq_path = args.sciq_json or DEFAULT_LOCAL_SCIQ_PATH
    try:
        if args.dataset == "all":
            dataset = build_all_dataset_items(level, local_sciq_path=local_sciq_path)
            notice = ALL_DATASETS_NOTICE
        elif args.dataset == "original":
            original_items = build_demo_items(level)
            dataset = DemoDataset(
                items=original_items,
                sources={item.question_id: ORIGINAL_DATASET for item in original_items},
                gold_choices={},
            )
            notice = FIXTURE_NOTICE
        elif args.dataset == "team":
            team_sciq = load_packaged_sciq_questions()
            team_sciq_items = build_sciq_smoke_items(team_sciq, level)
            team_free_items = build_free_question_items(
                load_packaged_free_questions(), level
            )
            dataset = DemoDataset(
                items=team_sciq_items + team_free_items,
                sources={
                    **{item.question_id: TEAM_SCIQ_DATASET for item in team_sciq_items},
                    **{item.question_id: TEAM_FREE_DATASET for item in team_free_items},
                },
                gold_choices={
                    question.question_id: question.correct_choice for question in team_sciq
                },
            )
            notice = SCIQ_FIXTURE_NOTICE
        else:
            if not local_sciq_path.is_file():
                raise ValueError(f"local SciQ JSON file does not exist: {local_sciq_path}")
            local_sciq = load_sciq_questions(local_sciq_path)
            local_items = build_sciq_smoke_items(local_sciq, level)
            dataset = DemoDataset(
                items=local_items,
                sources={item.question_id: LOCAL_SCIQ_DATASET for item in local_items},
                gold_choices={
                    question.question_id: question.correct_choice for question in local_sciq
                },
            )
            notice = SCIQ_FIXTURE_NOTICE
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc

    items = dataset.items
    if not items:
        raise SystemExit("error: selected dataset contains no questions")
    limit = len(items) if args.limit is None else args.limit
    if not 1 <= limit <= len(items):
        raise SystemExit(f"error: --limit must be between 1 and {len(items)}")

    if args.sciq_json and args.dataset == "original":
        raise SystemExit("error: --sciq-json cannot be combined with --dataset original")

    if args.provider == "openai":
        model = args.model or os.environ.get("LLM_MODEL")
        if not model:
            raise SystemExit("error: --model or LLM_MODEL is required for provider=openai")
        client = OpenAIResponsesClient(model)
    elif args.provider == "ollama":
        model = args.model or os.environ.get("LLM_MODEL") or "gpt-oss:20b"
        client = OllamaChatClient(model)
    else:
        client = MockJsonLLMClient()

    generator = PersonalisedAnswerGenerator(client, max_retries=2)
    selected_items = items[:limit]
    batch_results = generate_batch(generator, selected_items)

    three_level = []
    if not args.skip_three_level:
        first_item = items[0]
        for sample_level in StudentLevel:
            sample = BatchItem(
                question_id=f"{first_item.question_id}-{sample_level.value}",
                question=first_item.question,
                profile=Week1ProfileProvider("task7-three-level").get(sample_level),
                retrieval=first_item.retrieval,
            )
            three_level.extend(generate_batch(generator, [sample]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    batch_path = args.output_dir / f"batch_{len(batch_results)}_results.json"
    levels_path = args.output_dir / "three_level_sample.json"
    source_counts = Counter(dataset.sources[result.question_id] for result in batch_results)
    batch_payload = {
        "notice": notice,
        "dataset_sources": dict(sorted(source_counts.items())),
        "provider": args.provider,
        "level": level.value,
        "result_count": len(batch_results),
        "completed": sum(result.status == "completed" for result in batch_results),
        "failed": sum(result.status == "failed" for result in batch_results),
        "results": [
            {
                **result.model_dump(),
                "dataset_source": dataset.sources[result.question_id],
                **(
                    {"fixture_gold_choice": dataset.gold_choices[result.question_id]}
                    if result.question_id in dataset.gold_choices
                    else {}
                ),
            }
            for result in batch_results
        ],
    }
    batch_path.write_text(json.dumps(batch_payload, indent=2), encoding="utf-8")
    if three_level:
        levels_path.write_text(
            json.dumps(
                {
                    "notice": notice,
                    "dataset_source": dataset.sources[first_item.question_id],
                    "results": [result.model_dump() for result in three_level],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "notice": notice,
                "batch_results": str(batch_path),
                "three_level_sample": str(levels_path) if three_level else None,
                "completed": batch_payload["completed"],
                "failed": batch_payload["failed"],
                "dataset_sources": batch_payload["dataset_sources"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
