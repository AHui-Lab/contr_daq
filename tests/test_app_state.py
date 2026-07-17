from modules.app_state import AppState


def test_default_state_is_idle_and_descriptive():
    state = AppState()

    assert state.any_running is False
    assert state.summary == {
        "daq": "Idle",
        "camera": "Idle",
        "motion": "Ready",
        "force": "Idle",
        "recording": "Off",
    }


def test_state_summary_reflects_active_subsystems():
    state = AppState(
        daq_running=True,
        camera_1_running=True,
        motion_running=True,
        force_running=True,
        recording=True,
    )

    assert state.any_running is True
    assert state.summary == {
        "daq": "Sampling",
        "camera": "Camera 1",
        "motion": "Scanning",
        "force": "Streaming",
        "recording": "On",
    }


def test_camera_summary_handles_two_cameras():
    state = AppState(camera_1_running=True, camera_2_running=True)

    assert state.summary["camera"] == "Both"
