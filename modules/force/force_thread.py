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

    def set_zero(self, offset):
        self.zero_offset = np.array(offset)

    def run(self):
        self.running = True

        try:
            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1      # ⚠ 非阻塞模式（关键）
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

                # 2️⃣ 等待传感器响应（最小必要等待）
                # time.sleep(0.02)   # ≈ 20 ms

                # 3️⃣ 只要够一帧，就读“最新一帧”
                n = ser.in_waiting
                if n < self.FRAME_LEN:
                    self.msleep(5)  # ⭐ 防止空转占CPU
                    continue

                raw = ser.read(self.FRAME_LEN)  # ⭐ 只读一帧（更稳定）
                frame = raw

                # 4️⃣ 帧头校验
                if frame[0] != 1 or frame[1] != 3:
                    continue

                # 5️⃣ 数据解析（严格对齐 MATLAB）
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

                vals = np.array(vals)
                total_force = float(np.sum(vals))

                # 6️⃣ 发给 UI
                self.data_ready.emit(total_force, vals.tolist())

            except Exception as e:
                print("[Force] 读取异常:", e)

            # 7️⃣ 控制刷新率 ≈ 20 Hz
            self.msleep(20)

        if ser and ser.is_open:
            ser.close()

    def stop(self):
        self.running = False
        self.wait()
