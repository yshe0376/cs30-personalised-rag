"""Judge configuration hashes stay stable for non-Gemini judges."""

import json
import re
from pathlib import Path

from cs30.evaluation.judge_runtime import configuration_sha256
from cs30.evaluation.open_answer_scoring import OpenAnswerScorer
from cs30.evaluation.v2_generation_models import JudgeConfiguration

README = Path(__file__).resolve().parents[1] / "src" / "cs30" / "evaluation" / "README.md"

BASE = {
    "config_version": "judge-v1",
    "provider": "openai",
    "model_family": "gpt",
    "model_revision": "gpt-x-2026",
    "temperature": 0.0,
    "seed": 7,
    "prompt_version": "p1",
    "output_schema_version": "s1",
    "local_model": False,
    "data_approval": "approved",
}


class OpenAIStyleClient:
    model = "judge-v1"
    temperature = 0.0
    endpoint = "https://api.openai.com"
    max_output_tokens = 2048


def test_non_gemini_v2_config_hashes_match_main() -> None:
    """Values computed on main before thinking_level existed; caches stay valid."""

    assert configuration_sha256(JudgeConfiguration(**BASE)) == (
        "3d1255325e3f83937e1efad6f0c6eb934b4966098fc9bec2deb28c0bc49b46f5"
    )
    ollama = {**BASE, "provider": "ollama", "local_model": True, "seed": None}
    assert configuration_sha256(JudgeConfiguration(**ollama)) == (
        "fabf66866a395c07ddba709d6209757c7160541d27ca6f691ecdf5a0334810ff"
    )


def test_non_gemini_open_answer_hashes_match_main() -> None:
    assert OpenAnswerScorer(OpenAIStyleClient()).judge_config_sha256 == (
        "418cb9e93b60c1d0045d2165812a752618ef406185e9ae63c7b7b55f366ef402"
    )
    assert "thinking_level" not in OpenAnswerScorer(OpenAIStyleClient()).judge_config
    assert OpenAnswerScorer(None).judge_config_sha256 == (
        "4f40e2b12faf4fa6f3aa49ddbd572e9fd8f23edf3a9685c97bfb254fab85c608"
    )


def test_gemini_thinking_level_changes_the_hash() -> None:
    gemini = {**BASE, "provider": "gemini", "model_family": "gemini"}
    high = configuration_sha256(JudgeConfiguration(**gemini, thinking_level="high"))
    low = configuration_sha256(JudgeConfiguration(**gemini, thinking_level="low"))
    assert high != low

    client = OpenAIStyleClient()
    client.thinking_level = "high"
    assert OpenAnswerScorer(client).judge_config["thinking_level"] == "high"


def test_readme_gemini_example_is_a_valid_configuration() -> None:
    text = README.read_text(encoding="utf-8").replace("\r\n", "\n")
    section = text.split("### Gemini judge configuration", 1)[1]
    example = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert example is not None
    configuration = JudgeConfiguration.model_validate(json.loads(example.group(1)))
    assert configuration.provider == "gemini"
    assert configuration.thinking_level == "high"
    assert configuration.temperature == 1.0
