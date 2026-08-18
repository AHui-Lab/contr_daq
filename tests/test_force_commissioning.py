import csv

from modules.workflow.force_commissioning import (
    ForceCommissioningLog,
    ForceSafetyConfig,
    ForceSafetySupervisor,
)


def _supervisor(**values):
    config = ForceSafetyConfig(total_high_n=20.0, **values)
    supervisor = ForceSafetySupervisor()
    supervisor.arm(config)
    return supervisor


def test_total_force_limit_trips_immediately():
    decision = _supervisor().evaluate(20.0, [5.0] * 4, 1.0, 1.0)

    assert decision.kind == "trip"
    assert decision.reason == "total_force_high"


def test_negative_individual_channel_is_allowed_when_other_limits_are_safe():
    decision = _supervisor(channel_high_n=12.0).evaluate(
        10.0,
        [-2.0, 4.0, -1.0, 9.0],
        1.0,
        1.0,
    )

    assert decision.kind == "ok"
    assert decision.max_channel_index == 3


def test_positive_channel_limit_is_independent_of_total_force():
    decision = _supervisor(channel_high_n=8.0).evaluate(
        7.0,
        [-2.0, 1.0, 0.0, 8.0],
        1.0,
        1.0,
    )

    assert decision.kind == "trip"
    assert decision.reason == "channel_force_high"
    assert decision.max_channel_index == 3


def test_imbalance_requires_persistence_before_trip():
    supervisor = _supervisor(imbalance_high_n=5.0, imbalance_confirm_s=0.05)

    first = supervisor.evaluate(8.0, [-1.0, 1.0, 2.0, 6.0], 1.0, 1.0)
    confirmed = supervisor.evaluate(8.0, [-1.0, 1.0, 2.0, 6.0], 1.04, 1.06)

    assert first.kind == "wait"
    assert confirmed.kind == "trip"
    assert confirmed.reason == "force_imbalance_high"


def test_rise_rate_uses_new_sample_timestamps_and_confirmation():
    supervisor = _supervisor(
        rise_rate_high_n_s=50.0,
        rise_rate_confirm_s=0.02,
    )

    assert supervisor.evaluate(1.0, [0.25] * 4, 1.00, 1.00).kind == "ok"
    assert supervisor.evaluate(2.0, [0.50] * 4, 1.01, 1.01).kind == "wait"
    decision = supervisor.evaluate(5.0, [1.25] * 4, 1.04, 1.04)

    assert decision.kind == "trip"
    assert decision.reason == "force_rise_rate_high"


def test_repeated_sample_does_not_invent_a_rise_rate_trip():
    supervisor = _supervisor(
        rise_rate_high_n_s=50.0,
        rise_rate_confirm_s=0.02,
    )
    supervisor.evaluate(1.0, [0.25] * 4, 1.00, 1.00)
    supervisor.evaluate(2.0, [0.50] * 4, 1.01, 1.01)

    decision = supervisor.evaluate(2.0, [0.50] * 4, 1.01, 1.04)

    assert decision.kind != "trip"
    assert decision.rise_rate_n_s == 0.0


def test_stale_signal_trips_without_requesting_retract_reason():
    decision = _supervisor().evaluate(5.0, [1.25] * 4, 1.0, 1.2)

    assert decision.reason == "stale_signal"
    assert decision.reason not in ForceSafetySupervisor.RETRACT_REASONS


def test_small_cross_clock_future_skew_is_tolerated():
    decision = _supervisor().evaluate(5.0, [1.25] * 4, 1.015, 1.0)

    assert decision.kind == "ok"


def test_large_future_timestamp_still_trips():
    decision = _supervisor().evaluate(5.0, [1.25] * 4, 1.021, 1.0)

    assert decision.kind == "trip"
    assert decision.reason == "invalid_timestamp"
    assert "0.021000 s" in decision.detail


def test_commissioning_log_saves_complete_force_row(tmp_path):
    session = ForceCommissioningLog(10.0)
    session.append(
        now=10.1,
        sample_monotonic=10.08,
        total_force_n=5.0,
        channel_forces_n=[1.0, -0.5, 2.0, 2.5],
        target_force_n=4.8,
        z_offset_mm=0.0001,
        action="z+0.0001",
        status="correction_applied",
    )

    output = session.save(tmp_path / "commission.csv")
    with output.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["p2_n"] == "-0.5"
    assert rows[0]["action"] == "z+0.0001"
    assert rows[0]["status"] == "correction_applied"
