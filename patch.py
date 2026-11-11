#!/usr/bin/env python3
"""Create an isolated, experimental windowed Project Eden executable."""

import argparse
import hashlib
import os
import struct
import tempfile
from pathlib import Path


ORIGINAL_SHA256 = "4ed37be2cc50850583ce2af30ed931b39c02998c107643ac30905e57dc30e101"
IMAGE_BASE = 0x00400000


def jump32(source, target):
    return b"\xE9" + struct.pack("<i", target - source - 5)


def jne32(source, target):
    return b"\x0F\x85" + struct.pack("<i", target - source - 6)


def je32(source, target):
    return b"\x0F\x84" + struct.pack("<i", target - source - 6)


def ja32(source, target):
    return b"\x0F\x87" + struct.pack("<i", target - source - 6)


def call32(source, target):
    return b"\xE8" + struct.pack("<i", target - source - 5)


CURSOR_HANDLER = 0x0045C84B
CURSOR_DEFAULT = 0x0045C745
CURSOR_GUARD = 0x0060C641
MOUSE_DISPATCH = 0x0060C7B1
MOUSE_ACTIVATE = 0x0060A0A0
FOREGROUND_HELPER = 0x00614DA0
CLIENT_CLICK_FALLBACK = 0x00614DC4
FOREGROUND_NAME = 0x00614DE0
CLIENT_STYLE_HELPER = 0x00614E00
ACTIVATION_STYLE_HELPER = 0x00614F00
MOUSE_SAVE_HELPER = 0x00614E40
MOUSE_REACQUIRE_GUARD = 0x00614E60
MOVE_DISPATCH_HELPER = 0x00614E80
MOVE_ENTER_HELPER = 0x00614EB0
MOVE_EXIT_HELPER = 0x00614ED0
MOUSE_POINTER = 0x01689900
SIZING_FLAG = 0x01689904
CLIENT_FOCUS_PENDING = 0x01689908
DISPLAY_MODE = 0x0168990C
SAVED_WINDOW_STYLE = 0x01689910
SAVED_WINDOW_RECT = 0x01689914
MONITOR_INFO = 0x01689924
EXTENSION_BASE = 0x0168D000
EXTENSION_RENDER = EXTENSION_BASE
EXTENSION_EVENT = EXTENSION_BASE + 0x300
EXTENSION_MOVE_EXIT = EXTENSION_BASE + 0xA00
EXTENSION_ACTIVATION = EXTENSION_BASE + 0xA20
EXTENSION_BOOT_AFTER_MOUSE = EXTENSION_BASE + 0xA40
EXTENSION_PRESENT = EXTENSION_BASE + 0xA80
EXTENSION_MOVIE_RENDER = EXTENSION_BASE + 0x1000
EXTENSION_MOVIE_EVENT = EXTENSION_BASE + 0x1100
EXTENSION_MOVIE_STARTUP = EXTENSION_BASE + 0x1200
EXTENSION_SHA256 = "d831b45af33cee1c4f366fe767732073ec8112c3fb108e363c20e40827ebc3c4"
ORIGINAL_TEXT_VIRTUAL_SIZE = 0x00213D92
EXTENDED_TEXT_VIRTUAL_SIZE = 0x00213F50
ORIGINAL_DATA1_VIRTUAL_SIZE = 0x000008E0
EXTENDED_DATA1_VIRTUAL_SIZE = 0x00000C00

# Reuse executable alignment gaps for the window-message guards. Both
# WM_SETCURSOR and WM_MOUSEACTIVATE carry the hit-test code in LOWORD(lParam).
CURSOR_GUARD_CODE = (
    bytes.fromhex("66 83 FF 01")  # cmp di, HTCLIENT
    + jne32(CURSOR_GUARD + 4, CURSOR_DEFAULT)
    + jump32(CURSOR_GUARD + 10, CURSOR_HANDLER)
)
MOUSE_DISPATCH_CODE = (
    bytes.fromhex("83 FE 21")  # cmp esi, WM_MOUSEACTIVATE
    + je32(MOUSE_DISPATCH + 3, MOUSE_ACTIVATE)
    + jump32(MOUSE_DISPATCH + 9, CURSOR_GUARD)
)
MOUSE_ACTIVATE_CODE = (
    bytes.fromhex("66 83 FF 01")  # cmp di, HTCLIENT
    + bytes.fromhex("75 11")  # nonclient area: return MA_NOACTIVATE
    + bytes.fromhex("C6 05") + struct.pack("<I", CLIENT_FOCUS_PENDING)
    + b"\x01"
    + call32(MOUSE_ACTIVATE + 13, FOREGROUND_HELPER)
    + jump32(MOUSE_ACTIVATE + 18, 0x0045C865)  # original return-1 tail
    + bytes.fromhex("6A 03 58 5F 5E 5D C2 14 00")  # return MA_NOACTIVATE
)
FOREGROUND_HELPER_CODE = (
    call32(FOREGROUND_HELPER, CLIENT_STYLE_HELPER)
    + bytes.fromhex("68 40 38 62 00 FF 15 64 51 61 00")
    + b"\x68" + struct.pack("<I", FOREGROUND_NAME)
    + bytes.fromhex("50 FF 15 48 51 61 00 85 C0 74 03 55 FF D0 C3")
)
CLIENT_CLICK_FALLBACK_CODE = (
    bytes.fromhex("81 FE 01 02 00 00")  # WM_LBUTTONDOWN
    + bytes.fromhex("75 0F")  # ignore other messages
    + bytes.fromhex("FF 15 6C 52 61 00 3B C5 74 05")
    + call32(CLIENT_CLICK_FALLBACK + 18, FOREGROUND_HELPER)
    + jump32(CLIENT_CLICK_FALLBACK + 23, 0x0045C7CE)
)
CLIENT_STYLE_CODE = (
    bytes.fromhex(
        "6A EC 55 FF 15 34 52 61 00"  # GetWindowLongA(hwnd, GWL_EXSTYLE)
        "25 FF FF FF F7"  # clear WS_EX_NOACTIVATE
        "50 6A EC 55 FF 15 30 52 61 00"  # SetWindowLongA
        "6A 37 6A 00 6A 00 6A 00 6A 00 6A 00 55"
        "FF 15 08 52 61 00 C3"  # SetWindowPos(SWP_FRAMECHANGED | ...)
    )
)
ACTIVATION_STYLE_CODE = (
    bytes.fromhex(
        "6A EC 55 FF 15 34 52 61 00"  # GetWindowLongA(hwnd, GWL_EXSTYLE)
        "66 83 7C 24 20 00 74 10"  # focus lost: keep NOACTIVATE
        "80 3D") + struct.pack("<I", CLIENT_FOCUS_PENDING) + bytes.fromhex(
        "00 74 30"  # ignore activation that did not come from a client click
        "25 FF FF FF F7 EB 05"  # clear NOACTIVATE for gameplay focus
        "0D 00 00 00 08"  # set it on focus loss or during sizing
        "50 6A EC 55 FF 15 30 52 61 00"  # SetWindowLongA
        "6A 37 6A 00 6A 00 6A 00 6A 00 6A 00 55"
        "FF 15 08 52 61 00"  # SetWindowPos(SWP_FRAMECHANGED | ...)
        "C6 05") + struct.pack("<I", CLIENT_FOCUS_PENDING) + b"\x00\xC3"
)
MOUSE_SAVE_CODE = (
    bytes.fromhex("8B 06 A3") + struct.pack("<I", MOUSE_POINTER)
    + bytes.fromhex("8B 4C 24 20")
    + jump32(MOUSE_SAVE_HELPER + 11, 0x00526804)
)
MOUSE_REACQUIRE_CODE = (
    bytes.fromhex("83 3D") + struct.pack("<I", SIZING_FLAG) + b"\x00"
    + jne32(MOUSE_REACQUIRE_GUARD + 7, 0x005264BE)
    + bytes.fromhex("8B 46 0C 50 8B 08 FF 51 1C")
    + jump32(MOUSE_REACQUIRE_GUARD + 22, 0x005264D3)
)
MOVE_DISPATCH_CODE = (
    bytes.fromhex("81 FE 31 02 00 00")  # WM_ENTERSIZEMOVE
    + je32(MOVE_DISPATCH_HELPER + 6, MOVE_ENTER_HELPER)
    + bytes.fromhex("81 FE 32 02 00 00")  # WM_EXITSIZEMOVE
    + je32(MOVE_DISPATCH_HELPER + 18, EXTENSION_MOVE_EXIT)
    + bytes.fromhex("83 FE 10")  # original WM_CLOSE range check
    + ja32(MOVE_DISPATCH_HELPER + 27, CLIENT_CLICK_FALLBACK)
    + jump32(MOVE_DISPATCH_HELPER + 33, 0x0045C608)
)
MOVE_ENTER_CODE = (
    bytes.fromhex("C7 05") + struct.pack("<I", SIZING_FLAG)
    + struct.pack("<I", 1)
    + b"\xA1" + struct.pack("<I", MOUSE_POINTER)
    + bytes.fromhex("85 C0 74 06 8B 08 50 FF 51 20")
    + jump32(MOVE_ENTER_HELPER + 25, CURSOR_DEFAULT)
)
MOVE_EXIT_CODE = (
    bytes.fromhex("C7 05") + struct.pack("<I", SIZING_FLAG)
    + struct.pack("<I", 0)
    + jump32(MOVE_EXIT_HELPER + 10, CURSOR_DEFAULT)
)

# A two-byte conditional jump chooses fullscreen handling when the graphics
# configuration's fullscreen flag is set. Replacing it with NOPs runs the
# existing windowed branch, which sets D3DPRESENT_PARAMETERS.Windowed = TRUE.
# The companion branches handle display mode updates during setup/reset.
PATCHES = (
    (0x004043D7, bytes.fromhex("D9 44 24 10 D8 E9"),
     jump32(0x004043D7, EXTENSION_MOVIE_RENDER) + b"\x90",
     "draw Startup Movies on the native Options page"),
    (0x0040452F, bytes.fromhex("8B 40 10 83 C0 F3"),
     jump32(0x0040452F, EXTENSION_MOVIE_EVENT) + b"\x90",
     "save the Startup Movies menu selection"),
    (0x0045E498, bytes.fromhex("C7 44 24 14 7C 69 63 00"),
     jump32(0x0045E498, EXTENSION_MOVIE_STARTUP) + b"\x90" * 3,
     "skip only the two startup movies when selected"),
    (0x00409911, bytes.fromhex("8B 5C 24 18 6A 00"),
     jump32(0x00409911, EXTENSION_RENDER) + b"\x90",
     "draw the native Display Mode graphics-menu row"),
    (0x00409A90, bytes.fromhex("3D BE 00 00 00"),
     jump32(0x00409A90, EXTENSION_EVENT),
     "handle Display Mode arrow clicks"),
    (0x0045C5FF, bytes.fromhex("83 FE 10 0F 87 C6 01 00 00"),
     jump32(0x0045C5FF, MOVE_DISPATCH_HELPER) + b"\x90" * 4,
     "handle move and resize notifications before the message switch"),
    (0x0045C647, bytes.fromhex("66 83 7C 24 1C 00"),
     call32(0x0045C647, EXTENSION_ACTIVATION) + b"\x90",
     "load saved display settings on game activation"),
    (0x0045C64D, bytes.fromhex("0F 85 F2 00 00 00"),
     jump32(0x0045C64D, CURSOR_DEFAULT) + b"\x90",
     "keep window visible and skip legacy minimize on focus loss"),
    (0x00517A6F, bytes.fromhex("75 0E"), bytes.fromhex("90 90"),
     "windowed display size during setup"),
    (0x00517BD0, bytes.fromhex("0F 95 C1 83 C1 02"),
     bytes.fromhex("B9 03 00 00 00 90"),
     "use copy swap effect for aspect-correct presentation"),
    (0x00517C0E, bytes.fromhex("75 32"), bytes.fromhex("90 90"),
     "windowed Direct3D device creation"),
    (0x005195DC, bytes.fromhex("75 21"), bytes.fromhex("90 90"),
     "windowed display format during device recovery"),
    (0x00519567, bytes.fromhex("6A 00 8B 86 6C EC 06 00"),
     jump32(0x00519567, EXTENSION_PRESENT) + b"\x90" * 3,
     "center the image within the client area without stretching"),
    (0x0052684C, bytes.fromhex("33 D2 8B 36 89 54 24 08"),
     jump32(0x0052684C, EXTENSION_BOOT_AFTER_MOUSE) + b"\x90" * 3,
     "restore saved display settings after DirectInput startup"),
    (0x005267FE, bytes.fromhex("8B 06 8B 4C 24 20"),
     jump32(0x005267FE, MOUSE_SAVE_HELPER) + b"\x90",
     "retain the exclusive mouse device pointer for window moves"),
    (0x005264CA, bytes.fromhex("8B 46 0C 50 8B 08 FF 51 1C"),
     jump32(0x005264CA, MOUSE_REACQUIRE_GUARD) + b"\x90" * 4,
     "avoid reacquiring the mouse during move and resize"),
    # The first message table entry originally dispatched only WM_SETCURSOR.
    # Route WM_MOUSEACTIVATE through it too, then dispatch by message number.
    (0x0045C898, bytes.fromhex("4B C8 45 00"),
     struct.pack("<I", MOUSE_DISPATCH),
     "dispatch frame mouse activation separately"),
    (0x0045C8B1, b"\x05", b"\x00",
     "handle WM_MOUSEACTIVATE before Windows activates the game"),
    (0x0045C84B, bytes.fromhex(
        "8B 4C 24 10 8A 81 29 B1 01 00 84 C0 0F 84 E8 FE FF FF"),
     bytes.fromhex("FF 15 6C 52 61 00 3B C5")
     + jne32(CURSOR_HANDLER + 8, CURSOR_DEFAULT) + b"\x90" * 4,
     "hide the OS cursor only while the game is foreground"),
    (CURSOR_GUARD, b"\x90" * len(CURSOR_GUARD_CODE), CURSOR_GUARD_CODE,
     "keep the OS cursor visible over the window frame"),
    (MOUSE_DISPATCH, b"\x90" * len(MOUSE_DISPATCH_CODE),
     MOUSE_DISPATCH_CODE, "route frame mouse activation"),
    (MOUSE_ACTIVATE, b"\xCC" * len(MOUSE_ACTIVATE_CODE),
     MOUSE_ACTIVATE_CODE, "activate only from game client clicks"),
    (FOREGROUND_HELPER, b"\x00" * len(FOREGROUND_HELPER_CODE),
     FOREGROUND_HELPER_CODE, "resolve and call SetForegroundWindow"),
    (CLIENT_CLICK_FALLBACK, b"\x00" * len(CLIENT_CLICK_FALLBACK_CODE),
     CLIENT_CLICK_FALLBACK_CODE, "restore focus from background client clicks"),
    (FOREGROUND_NAME, b"\x00" * len(b"SetForegroundWindow\0"),
     b"SetForegroundWindow\0", "store activation API name"),
    (CLIENT_STYLE_HELPER, b"\x00" * len(CLIENT_STYLE_CODE),
     CLIENT_STYLE_CODE, "clear no-activation on an intentional game click"),
    (ACTIVATION_STYLE_HELPER, b"\x00" * len(ACTIVATION_STYLE_CODE),
     ACTIVATION_STYLE_CODE, "change activation style after DirectInput setup"),
    (MOUSE_SAVE_HELPER, b"\x00" * len(MOUSE_SAVE_CODE), MOUSE_SAVE_CODE,
     "remember the exclusive mouse device"),
    (MOUSE_REACQUIRE_GUARD, b"\x00" * len(MOUSE_REACQUIRE_CODE),
     MOUSE_REACQUIRE_CODE, "defer mouse reacquisition until sizing ends"),
    (MOVE_DISPATCH_HELPER, b"\x00" * len(MOVE_DISPATCH_CODE),
     MOVE_DISPATCH_CODE, "dispatch move and resize notifications"),
    (MOVE_ENTER_HELPER, b"\x00" * len(MOVE_ENTER_CODE), MOVE_ENTER_CODE,
     "unacquire exclusive mouse before a move or resize"),
    (MOVE_EXIT_HELPER, b"\x00" * len(MOVE_EXIT_CODE), MOVE_EXIT_CODE,
     "allow mouse reacquisition after move or resize"),
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def pe32_sections(data):
    if data[:2] != b"MZ":
        raise ValueError("source is not an MZ executable")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("source has no PE signature")
    coff = pe + 4
    optional = coff + 20
    if struct.unpack_from("<H", data, optional)[0] != 0x10B:
        raise ValueError("source is not PE32")
    image_base = struct.unpack_from("<I", data, optional + 28)[0]
    if image_base != IMAGE_BASE:
        raise ValueError(f"unexpected image base: 0x{image_base:08X}")
    section_count = struct.unpack_from("<H", data, coff + 2)[0]
    section_table = optional + struct.unpack_from("<H", data, coff + 16)[0]
    sections = []
    for index in range(section_count):
        entry = section_table + 40 * index
        name = data[entry:entry + 8].split(b"\0")[0]
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from(
            "<IIII", data, entry + 8)
        sections.append((name, rva, virtual_size, raw_offset, raw_size))
    return sections


def file_offset(sections, va):
    rva = va - IMAGE_BASE
    for name, section_rva, virtual_size, raw_offset, raw_size in sections:
        if section_rva <= rva < section_rva + max(virtual_size, raw_size):
            delta = rva - section_rva
            if name != b".text" or delta >= raw_size:
                raise ValueError(f"patch address 0x{va:08X} is not executable")
            return raw_offset + delta
    raise ValueError(f"patch address 0x{va:08X} is outside the source")


def section_virtual_size_offset(data, name):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    coff = pe + 4
    optional = coff + 20
    count = struct.unpack_from("<H", data, coff + 2)[0]
    table = optional + struct.unpack_from("<H", data, coff + 16)[0]
    for index in range(count):
        entry = table + 40 * index
        if data[entry:entry + 8].split(b"\0")[0] == name:
            return entry + 8
    raise ValueError(f"source has no {name.decode('ascii')} section")


def build(source, output):
    source = Path(source).resolve(strict=True)
    output = Path(output).resolve()
    if source == output:
        raise ValueError("source and output must be different files")
    data = source.read_bytes()
    if sha256(data) != ORIGINAL_SHA256:
        raise ValueError(
            "unknown Eden.exe build; source SHA-256 is " + sha256(data))
    sections = pe32_sections(data)
    patched = bytearray(data)
    for va, expected, replacement, description in PATCHES:
        offset = file_offset(sections, va)
        if data[offset:offset + len(expected)] != expected:
            raise ValueError(f"unexpected instruction at 0x{va:08X}")
        patched[offset:offset + len(expected)] = replacement
        print(f"0x{va:08X}: {description}")
    virtual_size_offset = section_virtual_size_offset(data, b".text")
    if struct.unpack_from("<I", data, virtual_size_offset)[0] != ORIGINAL_TEXT_VIRTUAL_SIZE:
        raise ValueError("unexpected .text virtual size")
    struct.pack_into("<I", patched, virtual_size_offset, EXTENDED_TEXT_VIRTUAL_SIZE)
    print("extend .text mapping for the client activation helper")
    data1_size_offset = section_virtual_size_offset(data, b".data1")
    if struct.unpack_from("<I", data, data1_size_offset)[0] != ORIGINAL_DATA1_VIRTUAL_SIZE:
        raise ValueError("unexpected .data1 virtual size")
    data1_section = next(section for section in sections if section[0] == b".data1")
    for va in (MOUSE_POINTER, SIZING_FLAG, CLIENT_FOCUS_PENDING,
               DISPLAY_MODE, SAVED_WINDOW_STYLE, SAVED_WINDOW_RECT,
               SAVED_WINDOW_RECT + 12, MONITOR_INFO, MONITOR_INFO + 36):
        delta = va - IMAGE_BASE - data1_section[1]
        if delta < 0 or delta + 4 > data1_section[4]:
            raise ValueError("mouse state is outside .data1 raw bytes")
        if data[data1_section[3] + delta:data1_section[3] + delta + 4] != b"\x00" * 4:
            raise ValueError("mouse state storage is not empty")
    state_start = data1_section[3] + 0x950
    state_end = data1_section[3] + EXTENDED_DATA1_VIRTUAL_SIZE
    if any(data[state_start:state_end]):
        raise ValueError("display settings storage is not empty")
    struct.pack_into("<I", patched, data1_size_offset, EXTENDED_DATA1_VIRTUAL_SIZE)
    print("extend .data1 mapping for move and resize state")
    extension = (Path(__file__).resolve().parent / "extension.bin").read_bytes()
    if len(extension) != 0x2000 or sha256(extension) != EXTENSION_SHA256:
        raise ValueError("extension.bin has an unexpected size or SHA-256")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    coff = pe + 4
    optional = coff + 20
    section_count = struct.unpack_from("<H", data, coff + 2)[0]
    if section_count != 5:
        raise ValueError("unexpected PE section count")
    section_alignment = struct.unpack_from("<I", data, optional + 32)[0]
    file_alignment = struct.unpack_from("<I", data, optional + 36)[0]
    if section_alignment != 0x1000 or file_alignment != 0x1000:
        raise ValueError("unexpected PE section alignment")
    section_table = optional + struct.unpack_from("<H", data, coff + 16)[0]
    new_header = section_table + section_count * 40
    if data[new_header:new_header + 40] != b"\x00" * 40:
        raise ValueError("no room for the extension section header")
    last = sections[-1]
    section_rva = align(last[1] + max(last[2], last[4]), section_alignment)
    raw_offset = align(len(patched), file_alignment)
    if IMAGE_BASE + section_rva != EXTENSION_BASE:
        raise ValueError("extension section address changed")
    old_image_size = struct.unpack_from("<I", data, optional + 56)[0]
    if old_image_size != section_rva:
        raise ValueError("unexpected original PE image size")
    old_code_size = struct.unpack_from("<I", data, optional + 4)[0]
    struct.pack_into("<H", patched, coff + 2, section_count + 1)
    struct.pack_into("<I", patched, optional + 4, old_code_size + len(extension))
    struct.pack_into("<I", patched, optional + 56, section_rva + len(extension))
    struct.pack_into("<8sIIIIIIHHI", patched, new_header,
                     b".eden\x00\x00\x00", len(extension), section_rva,
                     len(extension), raw_offset, 0, 0, 0, 0, 0x60000020)
    patched.extend(b"\x00" * (raw_offset - len(patched)))
    patched.extend(extension)
    print("append executable .eden section for the in-game options")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            mode="wb", dir=output.parent, prefix=".eden-windowed-",
            suffix=".tmp", delete=False) as temp:
        temp.write(patched)
        temporary = Path(temp.name)
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"output: {output}")
    print(f"source SHA-256: {sha256(data)}")
    print(f"output SHA-256: {sha256(patched)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.source, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"patch failed: {error}\n")


if __name__ == "__main__":
    main()
