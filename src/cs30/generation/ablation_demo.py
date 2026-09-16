"""Runnable fixture demonstration of Member 7's four W5 conditions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cs30.contracts import RetrievalHit, RetrievalMode, RetrievalResult, StudentLevel
from cs30.profile import Week1ProfileProvider

from .client import MockJsonLLMClient, OllamaChatClient, OpenAIResponsesClient
from .conditions import FourConditionRunner, GenerationCondition
from .generator import PersonalisedAnswerGenerator
from .reranking import EvidenceRole, LevelAwareReranker, RerankConfig, RoleLabel

QUESTION = "Why can an object accelerate when a net force acts on it?"


def _fixture_evidence() -> RetrievalResult:
    return RetrievalResult(
        query=QUESTION,
        mode=RetrievalMode.FIXTURE,
        hits=[
            RetrievalHit(
                chunk_id="fixture_derivation",
                text="From F = ma, acceleration follows by dividing net force by mass.",
                chapter_id="forces",
                source="fixture://member7-roles",
                score=0.95,
                rank=1,
                retriever_type=RetrievalMode.FIXTURE,
            ),
            RetrievalHit(
                chunk_id="fixture_definition",
                text="Acceleration is the rate at which velocity changes with time.",
                chapter_id="motion",
                source="fixture://member7-roles",
                score=0.90,
                rank=2,
                retriever_type=RetrievalMode.FIXTURE,
            ),
            RetrievalHit(
                chunk_id="fixture_application",
                text="For fixed mass, increasing the net force increases acceleration.",
                chapter_id="forces",
                source="fixture://member7-roles",
                score=0.70,
                rank=3,
                retriever_type=RetrievalMode.FIXTURE,
            ),
        ],
    )


def _client(provider: str, model: str | None):
    if provider == "mock":
        return MockJsonLLMClient()
    if provider == "ollama":
        return OllamaChatClient(model or "gpt-oss:20b")
    if not model:
        raise ValueError("--model is required with --provider openai")
    return OpenAIResponsesClient(model)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["mock", "ollama", "openai"], default="mock")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--level",
        choices=[level.value for level in StudentLevel],
        default=StudentLevel.BEGINNER.value,
    )
    parser.add_argument("--lambda-weight", type=float, default=0.8)
    parser.add_argument(
        "--condition",
        choices=["all", *(condition.value for condition in GenerationCondition)],
        default="all",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path; parent directories are created",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    profile = Week1ProfileProvider(profile_prefix="member7-ablation").get(StudentLevel(args.level))
    client = _client(args.provider, args.model)
    runner = FourConditionRunner(
        PersonalisedAnswerGenerator(client),
        LevelAwareReranker(
            {
                "fixture_derivation": RoleLabel.single(EvidenceRole.DERIVATION),
                "fixture_definition": RoleLabel.single(EvidenceRole.DEFINITION),
                "fixture_application": RoleLabel.single(EvidenceRole.APPLICATION),
            },
            config=RerankConfig(
                lambda_weight=args.lambda_weight,
                parameter_source="fixture",
                taxonomy_status="fixture",
                taxonomy_version="candidate-v1",
            ),
        ),
    )
    evidence = _fixture_evidence()
    if args.condition == "all":
        results = runner.run_all(QUESTION, profile, evidence)
    else:
        results = [runner.run(QUESTION, profile, evidence, args.condition)]
    output = json.dumps(
        {
            "result_type": "engineering_fixture",
            "run_classification": {
                "generation": "fixture" if args.provider == "mock" else "real",
                "evidence": "fixture",
                "role_labels": "fixture",
                "reportable": False,
            },
            "provider": args.provider,
            "model": client.model,
            "warning": "Not a model-quality or validated-personalisation result.",
            "results": [result.model_dump() for result in results],
        },
        indent=2,
    )
    if args.output is None:
        print(output)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"{output}\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
