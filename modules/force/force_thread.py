# modules/force/force_thread.py
from PySide6.QtCore import QThread, Signal
import serial
import time
import numpy as np


class ForceThread(QThread):
    data_ready = Signal(float, list)   # total_force, [ch1,ch2,ch3,ch4]
    started_ok = Signal(bool)

    FRAME_LEN = 3 + 16 + 2   # addr + func + bytecount + data(16) + CRC = 21

    def __init__(self, port="COM11", baudrate=9600):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.running = False

    # =========================
    # CRC16 (Modbus)
    # =========================
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

    # =========================
    # 主线程
    # =========================
    def run(self):
        self.running = True

        try:
            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1
            )
            self.started_ok.emit(True)
        except Exception as e:
            print("[Force] 打开串口失败:", e)
            self.started_ok.emit(False)
            return

        # 👉 读 4通道重量（地址450，读8寄存器）
        cmd = bytes([1, 3, 1, 194, 0, 8, 228, 12])

        buffer = bytearray()

        while self.running:
            try:
                # 1️⃣ 发送命令
                ser.write(cmd)

                # 2️⃣ 读数据（累积缓冲区）
                time.sleep(0.02)
                buffer.extend(ser.read(ser.in_waiting or 1))

                # 3️⃣ 尝试解析完整帧
                while len(buffer) >= self.FRAME_LEN:

                    # 找帧头
                    if buffer[0] != 1 or buffer[1] != 3:
                        buffer.pop(0)
                        continue

                    frame = buffer[:self.FRAME_LEN]

                    # CRC校验
                    if not self.check_crc(frame):
                        buffer.pop(0)
                        continue

                    # 字节数校验
                    byte_count = frame[2]
                    if byte_count != 16:
                        buffer.pop(0)
                        continue

                    # =========================
                    # 解析4通道（32bit）
                    # =========================
                    vals = []
                    for ch in range(4):
                        base = 3 + ch * 4

                        b1 = frame[base]
                        b2 = frame[base + 1]
                        b3 = frame[base + 2]
                        b4 = frame[base + 3]

                        raw_val = (b1 << 24) | (b2 << 16) | (b3 << 8) | b4

                        # 32bit有符号
                        if raw_val >= (1 << 31):
                            raw_val -= (1 << 32)

                        # ⚠️ 这里暂时不缩放（先保证正确）
                        vals.append(raw_val/1000)

                    vals = np.array(vals)

                    total_force = float(np.sum(vals))

                    vals = np.round(vals)
                    total_force = round(total_force)

                    # 发信号
                    self.data_ready.emit(total_force, vals.tolist())

                    # 移除已解析帧
                    buffer = buffer[self.FRAME_LEN:]

                # 控制刷新率
                self.msleep(20)

            except Exception as e:
                print("[Force] 读取异常:", e)

        if ser and ser.is_open:
            ser.close()

    def stop(self):
        self.running = False
        self.wait()