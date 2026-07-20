import pytest

from modules.workflow.force_hold import ForceHoldConfig, ForceHoldController


def test_force_hold_defaults_use_conservative_large_error_limit():
    config = ForceHoldConfig(enabled=True)

    assert config.hard_error_n == pytest.approx(1.0)
    assert config.max_offset_mm == pytest.approx(0.05)


def _armed_controller(**overrides):
    values = {
        "enabled": True,
        "tolerance_n": 0.2,
        "z_step_mm": 0.002,
        "control_interval_s": 0.15,
        "outside_confirm_s": 0.05,
        "signal_timeout_s": 0.25,
        "max_offset_mm": 0.05,
        "hard_error_n": 2.0,
    }
    values.update(overrides)
    controller = ForceHoldController()
    controller.arm(ForceHoldConfig(**values), target_force_n=10.0, now=1.0)
    return controller


def test_force_hold_stays_idle_inside_deadband():
    controller = _armed_controller()

    decision = controller.evaluate(9.9, sample_monotonic=1.2, now=1.2)

    assert decision.kind == "hold"
    assert controller.snapshot()["force_hold_correction_count"] == 0


def test_low_force_requests_z_positive_after_error_is_confirmed():
    controller = _armed_controller()

    assert controller.evaluate(9.5, 1.20, 1.20).kind == "wait"
    decision = controller.evaluate(9.5, 1.26, 1.26)

    assert decision.kind == "correct"
    assert decision.direction == 1
    assert decision.step_mm == pytest.approx(0.002)
    controller.accept(decision)
    assert controller.snapshot()["force_hold_accumulated_z_mm"] == pytest.approx(0.002)


def test_high_force_requests_z_negative():
    controller = _armed_controller()

    controller.evaluate(10.5, 1.20, 1.20)
    decision = controller.evaluate(10.5, 1.26, 1.26)

    assert decision.kind == "correct"
    assert decision.direction == -1


def test_force_hold_does_not_chase_a_single_transient():
    controller = _armed_controller()

    assert controller.evaluate(9.5, 1.20, 1.20).kind == "wait"
    assert controller.evaluate(10.0, 1.22, 1.22).kind == "hold"
    assert controller.evaluate(9.5, 1.24, 1.24).kind == "wait"


def test_force_hold_aborts_on_stale_signal_and_large_error():
    stale = _armed_controller().evaluate(10.0, sample_monotonic=1.0, now=1.5)
    excessive = _armed_controller().evaluate(7.0, sample_monotonic=1.1, now=1.1)

    assert (stale.kind, stale.reason) == ("abort", "stale_signal")
    assert (excessive.kind, excessive.reason) == ("abort", "force_error_limit")


def test_force_hold_aborts_before_exceeding_total_z_budget():
    controller = _armed_controller(z_step_mm=0.002, max_offset_mm=0.004)

    for start in (1.2, 1.5):
        controller.evaluate(9.5, start, start)
        decision = controller.evaluate(9.5, start + 0.06, start + 0.06)
        assert decision.kind == "correct"
        controller.accept(decision)

    controller.evaluate(9.5, 1.8, 1.8)
    decision = controller.evaluate(9.5, 1.86, 1.86)

    assert (decision.kind, decision.reason) == ("abort", "z_travel_limit")


def test_force_hold_target_must_be_positive_and_above_tolerance():
    controller = ForceHoldController()

    with pytest.raises(ValueError, match="target"):
        controller.arm(ForceHoldConfig(enabled=True), target_force_n=0.1, now=1.0)
