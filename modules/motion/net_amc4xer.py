import ctypes
from dataclasses import dataclass
from ctypes import byref, c_char_p, c_ubyte, c_uint


@dataclass(frozen=True)
class MotionProfile:
    vo: int
    vt: int
    acc_time: int
    dec_time: int


@dataclass(frozen=True)
class MotionState:
    position: int
    run_state: int
    io_state: int
    emergency: int
    speed: int


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
        self.dll.DeltMov.restype = ctypes.c_int
        self.dll.AxsStop.argtypes = [c_char_p, c_uint]
        self.dll.AxsStop.restype = ctypes.c_int
        self.dll.Read_Position.argtypes = [
            c_char_p,
            c_uint,
            ctypes.POINTER(c_uint),
            ctypes.POINTER(c_ubyte),
            ctypes.POINTER(c_ubyte),
            ctypes.POINTER(c_ubyte),
        ]
        self.dll.Read_Position.restype = ctypes.c_int
        self.dll.Read_Speed.argtypes = [
            c_char_p,
            c_uint,
            ctypes.POINTER(c_uint),
        ]
        self.dll.Read_Speed.restype = ctypes.c_int

        self.dll.SOCKET_init()

    def enable_axis(self, axis: int):
        return self.dll.Set_Axs(self.dest_ip, axis, 1, 0, 0, 0)

    def move_relative(
        self,
        axis: int,
        direction: int,
        length: int,
        profile: MotionProfile,
    ):
        return self.dll.DeltMov(
            self.dest_ip,
            axis,
            0,              # curve
            direction,      # Dir
            0,              # Outmod
            profile.vo,     # Vo
            profile.vt,     # Vt
            length,         # Length
            0,              # StartDec
            profile.acc_time,  # Acctime
            profile.dec_time,  # Dectime
            0,              # SD_EN
            0               # WaitSYNC
        )

    def stop_axis(self, axis: int):
        return self.dll.AxsStop(self.dest_ip, axis)

    def read_axis_state(self, axis: int) -> MotionState:
        position = c_uint()
        run_state = c_ubyte()
        io_state = c_ubyte()
        emergency = c_ubyte()
        speed = c_uint()

        position_result = self.dll.Read_Position(
            self.dest_ip,
            axis,
            byref(position),
            byref(run_state),
            byref(io_state),
            byref(emergency),
        )
        speed_result = self.dll.Read_Speed(self.dest_ip, axis, byref(speed))
        if position_result != 0 or speed_result != 0:
            raise ConnectionError("Motion controller state read failed")

        return MotionState(
            position=int(position.value),
            run_state=int(run_state.value),
            io_state=int(io_state.value),
            emergency=int(emergency.value),
            speed=int(speed.value),
        )

    def close(self):
        self.dll.SOCKET_delete()
