"""Find candidate movement input floats in FreeRealms.exe for analog controller support.

Usage:
  1. Launch Free Realms and enter the world with your character standing still.
  2. Run: python tools/find_movement_addresses.py
  3. Press W to move forward, then release and press Enter in this window.
  4. Repeat for A/D strafe if prompted.
  5. Copy the suggested addresses into Client/FRController.ini under [AnalogMovement].
"""

from __future__ import annotations

import ctypes
import struct
import sys
import time

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_uint32),
        ("cntUsage", ctypes.c_uint32),
        ("th32ProcessID", ctypes.c_uint32),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", ctypes.c_uint32),
        ("cntThreads", ctypes.c_uint32),
        ("th32ParentProcessID", ctypes.c_uint32),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_uint32),
        ("szExeFile", ctypes.c_char * 260),
    ]


kernel32 = ctypes.windll.kernel32


def find_pid(name: bytes) -> int | None:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return None
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    pid = None
    if kernel32.Process32First(snap, ctypes.byref(entry)):
        while True:
            if entry.szExeFile.lower() == name.lower():
                pid = entry.th32ProcessID
                break
            if not kernel32.Process32Next(snap, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snap)
    return pid


def read_region(handle, base: int, size: int) -> bytes | None:
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(handle, ctypes.c_void_p(base), buf, size, ctypes.byref(read))
    if not ok:
        return None
    return buf.raw[: read.value]


def snapshot_floats(handle) -> dict[int, float]:
    values: dict[int, float] = {}
    mbi = (ctypes.c_byte * 48)()
    address = 0
    while kernel32.VirtualQueryEx(handle, ctypes.c_void_p(address), mbi, 48):
        base = struct.unpack_from("<Q", bytes(mbi), 0)[0]
        region_size = struct.unpack_from("<Q", bytes(mbi), 8)[0]
        protect = struct.unpack_from("<I", bytes(mbi), 24)[0]
        state = struct.unpack_from("<I", bytes(mbi), 16)[0]
        if state == 0x1000 and (protect & 0x04 or protect & 0x02):
            chunk = read_region(handle, base, min(region_size, 0x200000))
            if chunk:
                for offset in range(0, len(chunk) - 3, 4):
                    value = struct.unpack_from("<f", chunk, offset)[0]
                    if -1.25 <= value <= 1.25 and value not in (0.0, -0.0):
                        values[base + offset] = value
        address = base + region_size
        if address >= 0x7FFFFFFF:
            break
    return values


def diff_snapshots(before: dict[int, float], after: dict[int, float], min_delta: float = 0.05):
    hits = []
    for addr, old in before.items():
        new = after.get(addr)
        if new is None:
            continue
        delta = abs(new - old)
        if delta >= min_delta:
            hits.append((addr, old, new, delta))
    hits.sort(key=lambda item: item[3], reverse=True)
    return hits


def main() -> int:
    pid = find_pid(b"FreeRealms.exe")
    if not pid:
        print("FreeRealms.exe is not running.")
        return 1

    access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        print("Could not open FreeRealms.exe. Run this script as Administrator.")
        return 1

    print("Snapshot 1: stand still, then press Enter...")
    input()
    before = snapshot_floats(handle)

    print("Snapshot 2: hold W to move forward, then press Enter...")
    input()
    after_forward = snapshot_floats(handle)
    forward_hits = diff_snapshots(before, after_forward)

    print("\nTop forward-movement candidates:")
    for addr, old, new, delta in forward_hits[:10]:
        print(f"  0x{addr:08X}  {old:+.4f} -> {new:+.4f}  delta={delta:.4f}")

    print("\nSnapshot 3: hold D to strafe right, then press Enter...")
    input()
    after_strafe = snapshot_floats(handle)
    strafe_hits = diff_snapshots(before, after_strafe)

    print("\nTop strafe candidates:")
    for addr, old, new, delta in strafe_hits[:10]:
        print(f"  0x{addr:08X}  {old:+.4f} -> {new:+.4f}  delta={delta:.4f}")

    if forward_hits:
        print("\nSuggested FRController.ini entries:")
        print("[AnalogMovement]")
        print("UseMemory=1")
        print(f"MoveForwardAddress=0x{forward_hits[0][0]:08X}")
        if strafe_hits:
            print(f"StrafeAddress=0x{strafe_hits[0][0]:08X}")

    kernel32.CloseHandle(handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
