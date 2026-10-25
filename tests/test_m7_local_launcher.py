"""Local launcher must not quietly start an unbudgeted or misconfigured API run."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_m7_local.py"
SPEC = importlib.util.spec_from_file_location("m7_local_launcher", SCRIPT)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def settings(**overrides):
    return {
        "M7_MODEL": "synthetic-model",
        "M7_BASE_URL": "https://example.invalid/v1",
        "M7_PROVIDER": "synthetic",
        "M7_MODEL_VERSION": "synthetic-version",
        "M7_SMOKE_REQUEST_CAP": "120",
        "M7_DEV_REQUEST_CAP": "2000",
        "M7_MAX_OUTPUT_TOKENS": "4096",
        **overrides,
    }


def test_unconfigured_budget_refuses_api_run(tmp_path):
    with pytest.raises(ValueError, match="M7_SMOKE_REQUEST_CAP"):
        launcher.run_arguments(settings(M7_SMOKE_REQUEST_CAP="0"), tmp_path, "smoke")


def test_full_dev_requires_explicit_smoke_verified_format(tmp_path):
    with pytest.raises(ValueError, match="smoke-verified"):
        launcher.run_arguments(settings(), tmp_path, "dev")


def test_credentials_stay_out_of_arguments_and_resume_is_explicit(tmp_path):
    arguments = launcher.run_arguments(
        settings(M7_GENERATION_API_KEY="synthetic-secret", M7_OUTPUT_FORMAT="json_object"),
        tmp_path / "model-prepared", "dev", resume=True,
    )
    assert "synthetic-secret" not in " ".join(arguments)
    assert arguments[arguments.index("--api-key-env") + 1] == "M7_GENERATION_API_KEY"
    assert arguments[-1] == "--resume"
    assert arguments[arguments.index("--max-api-requests") + 1] == "2000"
    assert "test" not in arguments


def test_reserved_provider_options_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="governed"):
        launcher.run_arguments(settings(M7_EXTRA_BODY='{"model":"other"}'), tmp_path, "smoke")


def test_shared_provider_credentials_are_named_without_exposing_values(tmp_path):
    arguments = launcher.run_arguments(
        settings(M7_API_KEY_ENV="DEEPINFRA_API_KEY", DEEPINFRA_API_KEY="synthetic-secret"),
        tmp_path, "smoke",
    )
    assert arguments[arguments.index("--api-key-env") + 1] == "DEEPINFRA_API_KEY"
    assert "synthetic-secret" not in " ".join(arguments)


def test_invalid_credential_variable_name_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="environment-variable name"):
        launcher.run_arguments(settings(M7_API_KEY_ENV="not a name"), tmp_path, "smoke")


def test_default_status_does_not_prepare_or_call_api(monkeypatch, tmp_path, capsys):
    def unexpected(*args, **kwargs):
        pytest.fail("status must not prepare inputs or run a model")

    monkeypatch.setattr(launcher, "prepare", unexpected)
    assert launcher.main(["status", "--env-file", str(tmp_path / "absent")]) == 0
    assert "No API calls" in capsys.readouterr().out
