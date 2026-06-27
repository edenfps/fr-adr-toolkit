"""Analyze FreeRealms.exe input system for controller mod."""
import struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXE = r"c:\Users\bobya\FRController\Client\FreeRealms.exe"
IMAGE_BASE = 0x00400000


def load_sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    coff = pe + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    optsz = struct.unpack_from("<H", data, coff + 16)[0]
    sec_off = coff + 20 + optsz
    sections = []
    for i in range(nsec):
        o = sec_off + i * 40
        name = data[o : o + 8].split(b"\0")[0].decode(errors="replace")
        vs, va, rs, ptr = struct.unpack_from("<IIII", data, o + 8)
        sections.append((name, va, vs, rs, ptr))
    return sections


def file_to_va(sections, fo):
    for _, va, vs, _, ptr in sections:
        if ptr <= fo < ptr + vs:
            return IMAGE_BASE + va + (fo - ptr)
    return None


def va_to_file(sections, va):
    rva = va - IMAGE_BASE
    for _, v, s, _, ptr in sections:
        if v <= rva < v + s:
            return ptr + (rva - v)
    return None


def find_string_refs(data, sections, needle):
    idx = data.find(needle)
    if idx < 0:
        return []
    str_va = file_to_va(sections, idx)
    if str_va is None:
        return []
    packed = struct.pack("<I", str_va)
    refs = []
    text_start = va_to_file(sections, IMAGE_BASE + 0x1000)
    text_end = va_to_file(sections, IMAGE_BASE + 0x1362000)
    if text_start is None or text_end is None:
        return []
    pos = text_start
    while True:
        pos = data.find(packed, pos, text_end)
        if pos < 0:
            break
        refs.append((pos, file_to_va(sections, pos)))
        pos += 1
    return refs


def main():
    with open(EXE, "rb") as f:
        data = f.read()

    sections = load_sections(data)
    print("Sections:")
    for name, va, vs, rs, ptr in sections:
        print(f"  {name:8s} VA=0x{va:08X} VS=0x{vs:08X} RAW=0x{ptr:08X}")

    imports = []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dd_off = opt + 96 if magic == 0x10B else opt + 112
    import_rva = struct.unpack_from("<I", data, dd_off + 8)[0]
    import_off = va_to_file(sections, IMAGE_BASE + import_rva)
    off = import_off
    while True:
        orig, _, _, name_rva = struct.unpack_from("<IIII", data, off)
        if orig == 0 and name_rva == 0:
            break
        name_off = va_to_file(sections, IMAGE_BASE + name_rva)
        dll = bytearray()
        while data[name_off] != 0:
            dll.append(data[name_off])
            name_off += 1
        thunk_rva = orig if orig else struct.unpack_from("<I", data, off + 16)[0]
        thunk_off = va_to_file(sections, IMAGE_BASE + thunk_rva)
        while True:
            entry = struct.unpack_from("<I", data, thunk_off)[0]
            if entry == 0:
                break
            if entry & 0x80000000:
                fn = f"ord_{entry & 0xFFFF}"
            else:
                hint_off = va_to_file(sections, IMAGE_BASE + entry)
                fn = data[hint_off + 2 : hint_off + 2 + 128].split(b"\0")[0].decode(
                    errors="replace"
                )
            imports.append((dll.decode(), fn))
            thunk_off += 4
        off += 20

    input_apis = [
        "GetAsyncKeyState",
        "GetKeyState",
        "GetKeyboardState",
        "GetCursorPos",
        "SetCursorPos",
        "SendInput",
        "GetRawInputData",
        "RegisterRawInputDevices",
        "XInputGetState",
    ]
    print("\nImported input APIs:")
    for dll, fn in imports:
        if fn in input_apis:
            print(f"  {dll}!{fn}")

    print("\nProxy candidates (loaded DLLs):")
    for dll, _ in imports:
        if dll.lower() in {
            "version.dll",
            "winmm.dll",
            "dinput8.dll",
            "xinput1_3.dll",
            "xinput9_1_0.dll",
        }:
            print(f"  {dll}")

    needles = [
        b"MoveForward",
        b"CameraRotateOnce",
        b"GInputManagerWin32",
        b"GGamepad",
        b"GetAsyncKeyState",
        b"Axis_X",
        b"Axis_Y",
        b"Button_A",
        b"UKeyState",
    ]
    print("\nString references:")
    for needle in needles:
        idx = data.find(needle)
        refs = find_string_refs(data, sections, needle)
        print(
            f"  {needle.decode():24s} file=0x{idx:X} refs={len(refs)}"
            + (f" first=0x{refs[0][1]:X}" if refs else "")
        )

    # Disassemble around MoveForward string table refs in .data
    move_refs = find_string_refs(data, sections, b"MoveForward")
    print("\nMoveForward pointer refs (data/code):")
    for fo, va in move_refs[:8]:
        sec = None
        for name, sva, svs, _, ptr in sections:
            if ptr <= fo < ptr + svs:
                sec = name
                break
        print(f"  0x{va:08X} in {sec}")
        ctx_off = fo - 16
        print("    " + data[ctx_off : fo + 32].hex())

    # Find GetAsyncKeyState IAT entry
    print("\nAll imports from USER32:")
    for dll, fn in imports:
        if dll.upper() == "USER32.DLL" and "Key" in fn or "Mouse" in fn or "Input" in fn:
            print(f"  {fn}")


if __name__ == "__main__":
    main()
