"""Configure the Ruilide Modbus force sensor for faster response.

Change PORT below, then run:

    python scripts/config_force_sensor.py

The script tries 115200 first, then 9600, so it can be run both before and
after the baud-rate upgrade.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Any


PORT = "COM15"
TRY_BAUDRATES = [115200, 9600]
TARGET_BAUDRATE = 115200
SLAVE_ADDR = 0x01
SERIAL_TIMEOUT = 0.25


@dataclass(frozen=True)
class ConfigStep:
    name: str
    kind: str
    register: int
    value: int
    description: str


FAST_RESPONSE_PROFILE = [
    ConfigStep("unlock", "write_register", 0x0005, 0x5AA5, "unlock system config"),
    ConfigStep("reply_delay", "write_register", 0x0004, 0x0002, "set response delay to 2 ms"),
    ConfigStep("ad_speed", "write_register", 0x0020, 0x0003, "set AD speed profile to 0x03"),
    ConfigStep("filter_type", "write_register", 0x0022, 0x0003, "use first-order filter"),
    ConfigStep("filter_strength", "write_register", 0x0023, 0x0003, "set low filter strength"),
    ConfigStep("zero_tracking", "write_register", 0x0060, 0x0000, "disable automatic zero tracking"),
    ConfigStep("baudrate", "write_register", 0x0001, 0x0007, "set baudrate to 115200"),
]


def crc16(data: bytes | bytearray) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


def with_crc(payload: bytearray) -> bytes:
    crc = crc16(payload)
    payload.extend([crc & 0xFF, (crc >> 8) & 0xFF])
    return bytes(payload)


def write_single_register_frame(register: int, value: int, slave_addr: int = SLAVE_ADDR) -> bytes:
    return with_crc(
        bytearray(
            [
                slave_addr,
                0x10,
                (register >> 8) & 0xFF,
                register & 0xFF,
                0x00,
                0x01,
                0x02,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ]
        )
    )


def read_holding_register_frame(register: int, count: int, slave_addr: int = SLAVE_ADDR) -> bytes:
    return with_crc(
        bytearray(
            [
                slave_addr,
                0x03,
                (register >> 8) & 0xFF,
                register & 0xFF,
                (count >> 8) & 0xFF,
                count & 0xFF,
            ]
        )
    )


def frame_text(frame: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in frame)


def open_serial(port: str, baudrate: int) -> Any:
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial is required; install it with: pip install pyserial") from exc

    return serial.Serial(port, baudrate=baudrate, timeout=SERIAL_TIMEOUT)


def read_response(ser: Any, min_len: int = 8) -> bytes:
    deadline = time.monotonic() + SERIAL_TIMEOUT
    buffer = bytearray()
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buffer.extend(chunk)
            if len(buffer) >= min_len:
                break
    return bytes(buffer)


def response_has_valid_crc(response: bytes) -> bool:
    return len(response) >= 5 and crc16(response[:-2]) == (response[-2] | (response[-1] << 8))


def send_frame(ser: Any, frame: bytes, min_response_len: int = 8) -> bytes:
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    response = read_response(ser, min_response_len)
    if not response_has_valid_crc(response):
        raise RuntimeError(f"invalid or missing response: {frame_text(response)}")
    return response


def detect_baudrate(port: str, baudrates: list[int]) -> int:
    probe = read_holding_register_frame(0x01C2, 8)
    for baudrate in baudrates:
        try:
            with open_serial(port, baudrate) as ser:
                send_frame(ser, probe, min_response_len=21)
                return baudrate
        except Exception as exc:
            print(f"[probe] {port} @ {baudrate}: {exc}")
    raise RuntimeError(f"could not communicate with sensor on {port}")


def apply_profile(port: str, baudrate: int, target_baudrate: int) -> int:
    active_baudrate = baudrate
    with open_serial(port, active_baudrate) as ser:
        for step in FAST_RESPONSE_PROFILE:
            if step.name == "baudrate" and active_baudrate == target_baudrate:
                print(f"[skip] {step.description}; already at {target_baudrate}")
                continue

            frame = write_single_register_frame(step.register, step.value)
            print(f"[send] {step.name}: {step.description}")
            print(f"       {frame_text(frame)}")
            response = send_frame(ser, frame)
            print(f"[recv] {frame_text(response)}")

            if step.name == "baudrate":
                active_baudrate = target_baudrate
                time.sleep(0.2)

    return active_baudrate


def verify_sensor(port: str, baudrate: int) -> None:
    frame = read_holding_register_frame(0x01C2, 8)
    with open_serial(port, baudrate) as ser:
        response = send_frame(ser, frame, min_response_len=21)
    print(f"[verify] read 4-channel gross weight OK @ {baudrate}")
    print(f"         {frame_text(response)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure Ruilide Modbus force sensor.")
    parser.add_argument("--port", default=PORT, help=f"serial port, default: {PORT}")
    parser.add_argument(
        "--baudrates",
        default=",".join(str(item) for item in TRY_BAUDRATES),
        help="comma-separated baudrates to try, default: 115200,9600",
    )
    parser.add_argument(
        "--target-baudrate",
        type=int,
        default=TARGET_BAUDRATE,
        help="target sensor baudrate, default: 115200",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baudrates = [int(item.strip()) for item in args.baudrates.split(",") if item.strip()]

    print(f"[start] configuring force sensor on {args.port}")
    baudrate = detect_baudrate(args.port, baudrates)
    print(f"[ok] detected baudrate: {baudrate}")

    final_baudrate = apply_profile(args.port, baudrate, args.target_baudrate)
    verify_sensor(args.port, final_baudrate)
    print("[done] force sensor fast-response configuration applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
