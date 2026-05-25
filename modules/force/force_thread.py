# modules/force/force_thread.py
from PySide6.QtCore import QThread, Signal
import serial
import time
import numpy as np


class ForceThread(QThread):
    data_ready = Signal(float, list)  # total_force, [ch1, ch2, ...]
    started_ok = Signal(bool)

    SLAVE_ADDR = 0x01
    FUNC_READ_HOLDING = 0x03
    GROSS_WEIGHT_START = 450  # decimal register offset, encoded as 0x01C2 in Modbus frames
    CHANNEL_COUNT = 4
    REG_COUNT = CHANNEL_COUNT * 2
    BYTE_COUNT = REG_COUNT * 2
    FRAME_LEN = 3 + BYTE_COUNT + 2

    def __init__(self, port="COM11", baudrate=9600):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = False

    def crc16(self, data):
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc

    def check_crc(self, frame):
        data = frame[:-2]
        crc_recv = frame[-2] | (frame[-1] << 8)
        crc_calc = self.crc16(data)
        return crc_recv == crc_calc

    def build_read_command(self):
        cmd = bytearray([
            self.SLAVE_ADDR,
            self.FUNC_READ_HOLDING,
            (self.GROSS_WEIGHT_START >> 8) & 0xFF,
            self.GROSS_WEIGHT_START & 0xFF,
            (self.REG_COUNT >> 8) & 0xFF,
            self.REG_COUNT & 0xFF,
        ])
        crc = self.crc16(cmd)
        cmd.extend([crc & 0xFF, (crc >> 8) & 0xFF])
        return bytes(cmd)

    def parse_frame(self, frame):
        if len(frame) != self.FRAME_LEN:
            raise ValueError("invalid frame length")
        if frame[0] != self.SLAVE_ADDR or frame[1] != self.FUNC_READ_HOLDING:
            raise ValueError("invalid frame header")
        if frame[2] != self.BYTE_COUNT:
            raise ValueError("invalid byte count")
        if not self.check_crc(frame):
            raise ValueError("invalid crc")

        vals = []
        for ch in range(self.CHANNEL_COUNT):
            base = 3 + ch * 4
            raw_val = (
                (frame[base] << 24)
                | (frame[base + 1] << 16)
                | (frame[base + 2] << 8)
                | frame[base + 3]
            )
            if raw_val >= (1 << 31):
                raw_val -= (1 << 32)
            vals.append(float(raw_val))
        return np.array(vals, dtype=float)

    def run(self):
        self.running = True

        try:
            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            self.started_ok.emit(True)
        except Exception as e:
            print("[Force] open serial failed:", e)
            self.started_ok.emit(False)
            return

        # Ruilide multi-channel read:
        # 01 03 01 C2 00 08 E4 0C
        # Reads the first 4 gross-weight channels, each as a signed 32-bit integer.
        cmd = self.build_read_command()
        buffer = bytearray()

        while self.running:
            try:
                ser.write(cmd)

                time.sleep(0.02)
                buffer.extend(ser.read(ser.in_waiting or 1))

                while len(buffer) >= self.FRAME_LEN:
                    if buffer[0] != self.SLAVE_ADDR or buffer[1] != self.FUNC_READ_HOLDING:
                        buffer.pop(0)
                        continue

                    frame = bytes(buffer[:self.FRAME_LEN])
                    try:
                        vals = self.parse_frame(frame)
                    except ValueError:
                        buffer.pop(0)
                        continue

                    total_force = float(np.sum(vals))
                    self.data_ready.emit(total_force, vals.tolist())
                    buffer = buffer[self.FRAME_LEN:]

                self.msleep(20)

            except Exception as e:
                print("[Force] read failed:", e)

        if ser and ser.is_open:
            ser.close()

    def stop(self):
        self.running = False
        self.wait()
