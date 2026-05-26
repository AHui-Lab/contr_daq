import pytest

from modules.recorder import data_recorder


def test_force_data_uses_relative_recording_time(monkeypatch, tmp_path):
    times = iter([100.0, 100.25])
    monkeypatch.setattr(data_recorder.time, "time", lambda: next(times))

    recorder = data_recorder.DataRecorder(save_dir=tmp_path)
    recorder.start()
    recorder.add_force_data(total_force=12.0, vals=[1.0, 2.0, 3.0, 6.0])

    assert recorder.force_buffer == [[0.25, 12.0, 1.0, 2.0, 3.0, 6.0]]


def test_daq_data_uses_relative_recording_time(monkeypatch, tmp_path):
    times = iter([200.0, 200.5])
    monkeypatch.setattr(data_recorder.time, "time", lambda: next(times))

    recorder = data_recorder.DataRecorder(save_dir=tmp_path)
    recorder.start()
    recorder.add_daq_data([0.1, 0.2])

    assert recorder.daq_buffer == [[pytest.approx(0.5), 0.1, 0.2]]
