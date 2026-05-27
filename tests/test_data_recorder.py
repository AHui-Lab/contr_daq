import csv

import pytest
import numpy as np

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


def test_daq_data_preserves_numpy_voltage_rows(monkeypatch, tmp_path):
    times = iter([300.0, 300.25])
    monkeypatch.setattr(data_recorder.time, "time", lambda: next(times))

    recorder = data_recorder.DataRecorder(save_dir=tmp_path)
    recorder.start()
    recorder.add_daq_data(np.array([0.1, 0.2]))

    assert recorder.daq_buffer == [[pytest.approx(0.25), 0.1, 0.2]]


def test_daq_chunk_uses_sample_rate_timebase(monkeypatch, tmp_path):
    monkeypatch.setattr(data_recorder.time, "time", lambda: 400.0)

    recorder = data_recorder.DataRecorder(save_dir=tmp_path)
    recorder.start()
    recorder.add_daq_chunk(
        rows=np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]),
        sample_rate=1000,
        channels=["ai0", "ai1"],
    )

    assert recorder.daq_channels == ["ai0", "ai1"]
    assert recorder.daq_buffer == [
        [0.0, 0.1, 0.2],
        [0.001, 0.3, 0.4],
        [0.002, 0.5, 0.6],
    ]


def test_save_writes_merged_file_without_dropping_daq_rows(monkeypatch, tmp_path):
    times = iter([500.0, 500.0015, 500.004])
    monkeypatch.setattr(data_recorder.time, "time", lambda: next(times))

    recorder = data_recorder.DataRecorder(save_dir=tmp_path)
    recorder.start()
    recorder.add_daq_chunk(
        rows=np.array([[0.1], [0.2], [0.3], [0.4]]),
        sample_rate=1000,
        channels=["ai0"],
    )
    recorder.add_force_data(total_force=10.0, vals=[1.0, 2.0, 3.0, 4.0])
    recorder.add_force_data(total_force=20.0, vals=[2.0, 4.0, 6.0, 8.0])
    recorder.stop()

    merged_files = list(tmp_path.glob("group1_merged_*.csv"))
    assert len(merged_files) == 1

    with merged_files[0].open(newline="") as f:
        rows = list(csv.reader(f))

    assert rows[0] == [
        "time",
        "ai0",
        "force_time",
        "total_force(N)",
        "P1(N)",
        "P2(N)",
        "P3(N)",
        "P4(N)",
    ]
    assert len(rows) == 5
    assert [row[0] for row in rows[1:]] == ["0.0", "0.001", "0.002", "0.003"]
    assert rows[1][2:] == ["", "", "", "", "", ""]
    assert float(rows[3][2]) == pytest.approx(0.0015)
    assert rows[3][3:] == ["10.0", "1.0", "2.0", "3.0", "4.0"]


def test_force_chunk_uses_sample_rate_timebase(monkeypatch, tmp_path):
    monkeypatch.setattr(data_recorder.time, "time", lambda: 600.0)

    recorder = data_recorder.DataRecorder(save_dir=tmp_path)
    recorder.start()
    recorder.add_force_chunk(
        rows=np.array([[1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]]),
        sample_rate=1000,
    )

    assert recorder.force_buffer == [
        [0.0, 10.0, 1.0, 2.0, 3.0, 4.0],
        [0.001, 20.0, 2.0, 4.0, 6.0, 8.0],
    ]
