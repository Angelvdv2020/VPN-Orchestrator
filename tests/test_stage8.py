from pathlib import Path

from hostfront_manager.config import WatchdogSection
from hostfront_manager.watchdog.engine import evaluate, record_repair
from hostfront_manager.watchdog.models import HealthSignal
from hostfront_manager.watchdog.store import WatchdogStore


def config(**values):
    defaults = dict(
        state_file=Path("state.json"), failure_threshold=2,
        recovery_threshold=2, cooldown_seconds=60,
        repair_window_seconds=300, max_repairs_per_window=2,
    )
    defaults.update(values)
    return WatchdogSection(**defaults)


def test_failure_threshold_and_recovery_hysteresis():
    cfg = config()
    bad = [HealthSignal("docker", False, "down", "docker")]
    decision, state = evaluate(bad, {}, cfg, now=100)
    assert decision.state == "unknown"
    assert not decision.repair_allowed
    decision, state = evaluate(bad, state, cfg, now=101)
    assert decision.state == "unhealthy"
    assert decision.repair_allowed

    good = [HealthSignal("docker", True, "up")]
    decision, state = evaluate(good, state, cfg, now=102)
    assert decision.state == "unhealthy"
    decision, state = evaluate(good, state, cfg, now=103)
    assert decision.state == "healthy"


def test_cooldown_and_repair_loop_guard():
    cfg = config(failure_threshold=1)
    bad = [HealthSignal("docker", False, "down", "docker")]
    decision, state = evaluate(bad, {}, cfg, now=100)
    assert decision.repair_allowed
    state = record_repair(state, now=100)
    decision, state = evaluate(bad, state, cfg, now=120)
    assert not decision.repair_allowed
    decision, state = evaluate(bad, state, cfg, now=161)
    assert decision.repair_allowed
    state = record_repair(state, now=161)
    decision, _ = evaluate(bad, state, cfg, now=230)
    assert not decision.repair_allowed
    assert "repair-loop" in decision.reason


def test_store_roundtrip(tmp_path):
    store = WatchdogStore(tmp_path / "nested" / "state.json")
    store.save({"state": "healthy", "failure_streak": 0})
    assert store.load()["state"] == "healthy"
