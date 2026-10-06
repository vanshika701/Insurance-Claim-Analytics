"""Model loading and scoring tests.

The actual scoring call (XGBoost predict + SHAP) goes through the same subprocess
entry point mcp_server/server.py uses (`python -m copilot.score <id>`), deliberately --
see docs/INTERVIEW_NOTES.md Phase 4 for why running XGBoost/SHAP in-process in the same
pytest session as the retrieval tests (sentence-transformers/torch) is exactly the
combination that segfaults. Keeping this test subprocess-isolated means test order can
never resurrect that bug.
"""
from __future__ import annotations

import json
import subprocess
import sys

from copilot.config import MODELS_DIR, PROJECT_ROOT, RESULTS_DIR


def test_model_artifacts_exist() -> None:
    assert (MODELS_DIR / "xgboost_pipeline.joblib").exists()
    assert (MODELS_DIR / "model_config.json").exists()
    assert (RESULTS_DIR / "model_metrics.json").exists()


def test_model_config_has_expected_shape() -> None:
    config = json.loads((MODELS_DIR / "model_config.json").read_text())
    assert "categorical" in config and len(config["categorical"]) > 0
    assert "numeric" in config and len(config["numeric"]) > 0
    assert isinstance(config["threshold"], float)
    assert "insured_hobbies" not in config["categorical"]  # excluded from the deployed model


def test_metrics_report_baseline_not_beaten() -> None:
    """Pins down the headline, honestly-reported Phase 2 finding so a future change to
    the model can't silently start claiming it beats the baseline without a human
    noticing the test fail."""
    metrics = json.loads((RESULTS_DIR / "model_metrics.json").read_text())
    assert metrics["threshold_selection"]["beats_baseline"] is False


def _run_scorer(claim_id: int) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "copilot.score", str(claim_id)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_score_known_claim() -> None:
    result = _run_scorer(1)
    assert result["found"] is True
    assert 0.0 <= result["fraud_probability"] <= 1.0
    assert result["risk_band"] in {"low", "medium", "high"}
    assert isinstance(result["would_flag"], bool)
    assert len(result["top_contributing_features"]) == 5
    assert all("feature" in f and "shap_value" in f for f in result["top_contributing_features"])


def test_score_missing_claim() -> None:
    result = _run_scorer(999999)
    assert result["found"] is False
    assert "error" in result and result["error"]


def test_major_damage_rule_matches_severity() -> None:
    result = _run_scorer(1)
    assert result["major_damage_rule_flags"] == (result["incident_severity"] == "Major Damage")
