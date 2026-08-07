"""A health check that only ever reports green is decoration.

These tests prove each check can FAIL - which is the only property that matters for an
unattended daemon. The models check is the one with a real incident behind it: the operator
deleted llama3.1:8b while config/models.yaml still pointed a tier at it, and nothing noticed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.runtime import health                      # noqa: E402


def _named(results, name):
    return next(r for r in results if r["name"] == name)


def test_all_checks_report_a_boolean_and_a_reason():
    for r in health.check_all():
        assert isinstance(r["ok"], bool)
        assert r["detail"], f"{r['name']} gave no detail - useless in an alert"


def test_unreachable_inference_is_detected(monkeypatch):
    monkeypatch.setattr(health, "OLLAMA", "http://127.0.0.1:9")   # discard port
    results = health.check_all()
    assert _named(results, "ollama")["ok"] is False
    # and the models check must not claim success when it could not look
    assert _named(results, "models")["ok"] is False


def test_a_configured_but_missing_model_is_detected(monkeypatch):
    """The llama3.1 incident: config points at a tag that is no longer installed."""
    monkeypatch.setattr(health, "_installed_models", lambda: {"qwen3.5:4b"})
    monkeypatch.setattr(health, "_configured_models",
                        lambda: {"local-mid": "a-model-that-was-deleted:8b"})
    models = _named(health.check_all(), "models")
    assert models["ok"] is False
    assert "a-model-that-was-deleted:8b" in models["detail"]


def test_low_disk_is_detected(monkeypatch):
    monkeypatch.setattr(health, "MIN_FREE_GB", 10_000_000.0)
    assert _named(health.check_all(), "disk")["ok"] is False


def test_summarise_names_every_failing_check():
    results = [
        {"name": "ollama", "ok": True, "detail": "fine"},
        {"name": "models", "ok": False, "detail": "MISSING local-mid=x"},
        {"name": "disk", "ok": False, "detail": "0.1GB free"},
    ]
    healthy, line = health.summarise(results)
    assert healthy is False
    assert "models" in line and "disk" in line and "MISSING local-mid=x" in line


def test_summarise_is_healthy_only_when_everything_passes():
    healthy, _ = health.summarise([{"name": "a", "ok": True, "detail": "d"}])
    assert healthy is True
