import pytest

from modules.workflow.force_hold import ForceHoldConfig, ForceHoldController


def _armed_controller(**overrides):
    values = {
        "enabled": True,
        "derivative_interval_s": 0.10,
        "derivative_deadband_n_s": 1.0,
        "z_step_mm": 0.002,
        "measurement_window_s": 0.05,
        "signal_timeout_s": 0.25,
        "max_offset_mm": 0.05,
        "hard_error_n": 3.0,
    }
    values.update(overrides)
    controller = ForceHoldController()
    controller.arm(ForceHoldConfig(**values), target_force_n=10.0, now=1.0)
    return controller


def test_force_derivative_defaults_are_fixed_period_and_noise_guarded():
    config = ForceHoldConfig(enabled=True)

    assert config.derivative_interval_s == pytest.approx(0.10)
    assert config.derivative_deadband_n_s == pytest.approx(1.0)
    assert config.z_step_mm == pytest.approx(0.0005)
    assert config.metadata()["force_hold_control_mode"] == "derivative"


def test_force_derivative_rejects_averaging_window_longer_than_time_step():
    with pytest.raises(ValueError, match="averaging window"):
        ForceHoldConfig(
            enabled=True,
            derivative_interval_s=0.02,
            measurement_window_s=0.05,
        ).validate()


def test_controller_collects_baseline_and_waits_for_fixed_time_step():
    controller = _armed_controller()

    baseline = controller.evaluate(10.0, sample_monotonic=1.00, now=1.00)
    early = controller.evaluate(10.2, sample_monotonic=1.05, now=1.05)

    assert (baseline.kind, baseline.reason) == ("wait", "collecting_baseline")
    assert (early.kind, early.reason) == ("wait", "sampling_interval")


def test_positive_derivative_moves_toward_lower_force():
    controller = _armed_controller()
    controller.evaluate(10.0, 1.00, 1.00)

    decision = controller.evaluate(10.2, 1.10, 1.10)

    assert decision.kind == "correct"
    assert decision.derivative_n_s == pytest.approx(2.0)
    assert decision.sample_interval_s == pytest.approx(0.10)
    assert decision.direction == -1
    assert decision.step_mm == pytest.approx(0.002)


def test_negative_derivative_moves_toward_higher_force():
    controller = _armed_controller()
    controller.evaluate(10.0, 1.00, 1.00)

    decision = controller.evaluate(9.8, 1.10, 1.10)

    assert decision.kind == "correct"
    assert decision.derivative_n_s == pytest.approx(-2.0)
    assert decision.direction == 1


def test_derivative_uses_configured_fixed_denominator_when_tick_is_late():
    controller = _armed_controller(derivative_interval_s=0.10)
    controller.evaluate(10.0, 1.00, 1.00)

    decision = controller.evaluate(10.3, 1.16, 1.16)

    assert decision.derivative_n_s == pytest.approx(3.0)
    assert decision.sample_interval_s == pytest.approx(0.10)


def test_derivative_deadband_prevents_quantization_chatter():
    controller = _armed_controller(derivative_deadband_n_s=1.1)
    controller.evaluate(10.0, 1.00, 1.00)

    decision = controller.evaluate(10.1, 1.10, 1.10)

    assert decision.kind == "hold"
    assert decision.derivative_n_s == pytest.approx(1.0)
    assert controller.snapshot()["force_hold_correction_count"] == 0


def test_controller_waits_for_a_new_force_sample_at_due_time():
    controller = _armed_controller()
    controller.evaluate(10.0, 1.00, 1.00)

    decision = controller.evaluate(10.0, 1.00, 1.10)

    assert (decision.kind, decision.reason) == ("wait", "waiting_new_sample")


def test_accept_records_fixed_z_step_and_total_travel_limit():
    controller = _armed_controller(z_step_mm=0.002, max_offset_mm=0.002)
    controller.evaluate(10.0, 1.00, 1.00)
    first = controller.evaluate(10.2, 1.10, 1.10)
    controller.accept(first)
    controller.evaluate(10.2, 1.20, 1.20)
    second = controller.evaluate(10.4, 1.30, 1.30)

    assert controller.snapshot()["force_hold_accumulated_z_mm"] == pytest.approx(
        -0.002
    )
    assert (second.kind, second.reason) == ("abort", "z_travel_limit")


def test_controller_aborts_on_stale_signal_and_reference_deviation():
    stale = _armed_controller().evaluate(10.0, sample_monotonic=1.0, now=1.5)
    excessive = _armed_controller(hard_error_n=1.0).evaluate(
        8.0, sample_monotonic=1.1, now=1.1
    )

    assert (stale.kind, stale.reason) == ("abort", "stale_signal")
    assert (excessive.kind, excessive.reason) == (
        "abort",
        "force_error_limit",
    )


def test_z_direction_mapping_can_be_reversed_after_machine_verification():
    controller = _armed_controller(z_positive_increases_force=False)
    controller.evaluate(10.0, 1.00, 1.00)

    decision = controller.evaluate(10.2, 1.10, 1.10)

    assert decision.direction == 1
