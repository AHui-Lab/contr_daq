# modules/motion/net_amc4xer.py
import ctypes
from ctypes import c_uint, c_char_p, c_ubyte, c_int

class NetAMC4XER:
    def __init__(self, dll_path, dest_ip: str):
        self.dest_ip = dest_ip.encode("ascii")
        self.dll = ctypes.WinDLL(dll_path)

        self.dll.SOCKET_init.restype = c_uint
        self.dll.SOCKET_delete.restype = None

        self.dll.Set_Axs.argtypes = [
            c_char_p, c_uint, c_uint, c_uint, c_uint, c_uint
        ]
        self.dll.DeltMov.argtypes = [
            c_char_p, c_uint, c_uint, c_uint, c_ubyte,
            c_uint, c_uint, c_uint,
            c_uint, c_uint, c_uint,
            c_uint, c_uint
        ]
        self.dll.AxsStop.argtypes = [c_char_p, c_uint]

        self.dll.SOCKET_init()

    def enable_axis(self, axis: int):
        return self.dll.Set_Axs(self.dest_ip, axis, 1, 1, 1, 1)

    def move_relative(self, axis: int, direction: int, length: int):
        return self.dll.DeltMov(
            self.dest_ip,
            axis,
            0,              # curve
            direction,      # Dir
            0,              # Outmod
            2000,            # Vo
            2000,            # Vt
            length,         # Length
            0,              # StartDec
            200,             # Acctime
            200,             # Dectime
            0,              # SD_EN
            0               # WaitSYNC
        )

    def stop_axis(self, axis: int):
        return self.dll.AxsStop(self.dest_ip, axis)

    def close(self):
        self.dll.SOCKET_delete()
