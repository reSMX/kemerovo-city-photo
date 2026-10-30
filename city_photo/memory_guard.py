"""Windows commit reserve, which can run out even while physical RAM is free."""
import ctypes
import os
import threading


def available_commit_bytes():
    if os.name!='nt':
        return None
    class MemoryStatus(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),
                  *[(name,ctypes.c_ulonglong) for name in ('total_physical','available_physical','total_pagefile','available_pagefile','total_virtual','available_virtual','available_extended')]]
    value=MemoryStatus()
    value.length=ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        return None
    return value.available_pagefile


class MemoryGuard:
    def __init__(self,cancel,minimum_bytes=3*1024**3,read=available_commit_bytes):
        self.cancel=cancel
        self.minimum=minimum_bytes
        self.read=read
        self.paused=False
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self._watch,name='commit-reserve',daemon=True)

    def _watch(self):
        while not self.stop.wait(.5):
            value=self.read()
            if not self.paused and value is not None and value<self.minimum:
                self.cancel()

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
