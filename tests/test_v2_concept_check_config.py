"""Reachability and safety checks for the v2 Concept Check configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.config import ConceptCheckConfig, load_v2_config

EXPECTED_FIELDS = {
    "enabled",
    "allow_llm_generation",
    "allow_unreviewed_questions",
    "promotion_threshold",
    "demotion_threshold",
    "level_change_window",
    "attempt_coverage_window",
    "correct_difficulty_weights",
    "wrong_difficulty_weights",
    "min_topic_support",
}


def test_development_profile_reaches_all_ten_concept_check_knobs() -> None:
    config = load_v2_config("development")

    assert set(ConceptCheckConfig.model_fields) == EXPECTED_FIELDS
    assert config.concept_check.enabled is False
    assert config.concept_check.correct_difficulty_weights == (0.5, 1.0, 1.0)
    assert config.concept_check.wrong_difficulty_weights == (1.0, 1.0, 0.5)
    assert config.concept_check.level_change_window == 3
    assert config.concept_check.attempt_coverage_window == 5


def test_non_development_profiles_reject_unsafe_concept_check_flags(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "staging.toml").write_text(
        """
environment = "staging"
fixture_mode = false

[corpus]
mode = "official"
corpus_version = "2.0.0-rc.1"
required_textbook_ids = [
  "openstax_college_physics_2e",
  "openstax_physics",
  "openstax_college_physics_ap_2e",
]
output_dir = "artifacts/v2/test"

[concept_check]
allow_llm_generation = true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="development-only"):
        load_v2_config("staging", config_dir=config_dir)


def test_invalid_concept_check_weights_fail_closed() -> None:
    with pytest.raises(ValueError, match="positive weights"):
        ConceptCheckConfig(correct_difficulty_weights=(0.0, 1.0, 1.0))


def test_required_catalogue_is_still_reached_when_concept_check_is_disabled() -> None:
    config = load_v2_config("development")
    assert config.required_textbook_ids == REQUIRED_TEXTBOOK_IDS
