# modules/force/force_thread.py
from PySide6.QtCore import QThread, Signal
import serial
import time
import numpy as np


class ForceThread(QThread):
    data_ready = Signal(float, list)   # total_force, [ch1,ch2,ch3,ch4]

    FRAME_LEN = 21
    started_ok = Signal(bool)
    ser=None

    def __init__(self, port="COM15", baudrate=9600):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = False
        self.zero_offset = np.zeros(4)
        self._emit_count = 0
        self._emit_interval = 2  # 每2帧发一次（你可以改）

    def set_zero(self, offset):
        self.zero_offset = np.array(offset)

    def run(self):
        buffer = bytearray()
        self.running = True

        try:
            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.01      # ⚠ 非阻塞模式（关键）
            )
            self.started_ok.emit(True)
        except Exception as e:
            print("[Force] 打开串口失败:", e)
            self.started_ok.emit(False)
            return

        # Modbus 读命令
        cmd = bytes([1, 3, 1, 194, 0, 8, 228, 12])

        while self.running:
            try:
                # 1️⃣ 发送命令
                ser.write(cmd)

                # 2️⃣ 读取所有数据并累加
                n = ser.in_waiting
                if n > 0:
                    buffer.extend(ser.read(n))

                # 3️⃣ 只要 buffer 够一帧就解析
                while len(buffer) >= self.FRAME_LEN:
                    # ⭐ 找帧头（关键）
                    if buffer[0] != 1 or buffer[1] != 3:
                        buffer.pop(0)
                        continue

                    # ⭐ 取一帧
                    frame = buffer[:self.FRAME_LEN]
                    buffer = buffer[self.FRAME_LEN:]

                    # ===== 数据解析 =====
                    vals = []
                    for ch in range(4):
                        base = 4 + ch * 4
                        b1 = frame[base]
                        b2 = frame[base + 1]
                        b3 = frame[base + 2]

                        raw_val = (b1 << 16) | (b2 << 8) | b3
                        if raw_val >= (1 << 23):
                            raw_val -= (1 << 24)

                        vals.append(raw_val / 1000.0)

                    total_force = sum(vals)

                    self._emit_count += 1

                    if self._emit_count % self._emit_interval == 0:
                        self.data_ready.emit(total_force, vals)

            except Exception as e:
                print("[Force] 读取异常:", e)

            self.msleep(1)

        if ser and ser.is_open:
            ser.close()

    def stop(self):
        self.running = False
        self.wait()
