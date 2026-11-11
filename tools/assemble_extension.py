#!/usr/bin/env python3
"""Regenerate extension.bin; requires keystone-engine for development only."""

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test-install" / "analysis-tools"))
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

BASE = 0x0168D000
SIZE = 0x2000
RENDER = BASE + 0x000
EVENT = BASE + 0x300
SET_MODE = BASE + 0x400
LOAD_CONFIG = BASE + 0x600
SAVE_CONFIG = BASE + 0x780
PREPARE_PATH = BASE + 0x900
MOVE_EXIT = BASE + 0xA00
ACTIVATION = BASE + 0xA20
BOOT_AFTER_MOUSE = BASE + 0xA40
PRESENT = BASE + 0xA80
CLEAR_UNUSED = BASE + 0xC00
FORCE_CLEAR = BASE + 0xD00
MOVIE_RENDER = BASE + 0x1000
MOVIE_EVENT = BASE + 0x1100
MOVIE_STARTUP = BASE + 0x1200
MOVIE_LOAD = BASE + 0x1300
MOVIE_SAVE = BASE + 0x1400
MOVIE_ON = BASE + 0x1900
MOVIE_OFF = BASE + 0x1930
MOVIE_SECTION = BASE + 0x1960
MOVIE_KEY = BASE + 0x1980
MOVIE_READ_NAME = BASE + 0x19A0
MOVIE_WRITE_NAME = BASE + 0x19C0
MOVIE_VALUE_ZERO = BASE + 0x19F0
MOVIE_VALUE_ONE = BASE + 0x1A00
LABEL = BASE + 0xE00
WINDOWED = BASE + 0xE20
BORDERLESS = BASE + 0xE40
MONITOR_FROM_NAME = BASE + 0xE60
MONITOR_INFO_NAME = BASE + 0xE80
MODULE_FILE_NAME = BASE + 0xEA0
GET_PROFILE_NAME = BASE + 0xEC0
WRITE_PROFILE_NAME = BASE + 0xEE0
INI_FILE_NAME = BASE + 0xF10
INI_SECTION = BASE + 0xF40
INI_KEY = BASE + 0xF60
KERNEL_NAME = BASE + 0xF80
GET_CLIENT_NAME = BASE + 0xFA0
FILL_RECT_NAME = BASE + 0xFC0

MODE = 0x0168990C
SAVED_STYLE = 0x01689910
SAVED_RECT = 0x01689914
MONITOR_INFO = 0x01689924
CONFIG_LOADED = 0x01689950
CONFIG_RECORD = 0x01689954
CLIENT_RECT = 0x01689980
DEST_RECT = 0x01689990
GET_CLIENT_PTR = 0x016899A0
FILL_RECT_PTR = 0x016899A4
LAST_CLIENT_WIDTH = 0x016899A8
LAST_CLIENT_HEIGHT = 0x016899AC
LAST_DEST_RECT = 0x016899B0
MOVIE_SKIP_STATE = 0x016899D0
CONFIG_PATH = 0x01689A00

# Eden's arrow helper leaves EBX pointing at its last control. Text layout
# expects EBX to hold the 0.5 scale used by the neighboring graphics rows.
RENDER_ASM = f"""
    mov ebx, 0x3F000000
    fld dword ptr [esp + 0x14]
    fadd dword ptr [esp + 0x24]
    fstp dword ptr [esp + 0x14]
    push 0
    push 0x18
    push 0
    push 0x{LABEL:X}
    push 0xC8
    push -0x61
    mov ecx, esi
    call 0x00401430
    mov ecx, dword ptr [esp + 0x14]
    mov edx, dword ptr [esp + 0x20]
    push ebx
    push ebp
    push -1
    push ecx
    mov ecx, dword ptr [esp + 0x38]
    push edx
    mov edx, dword ptr [esi + 0xC]
    push ecx
    push edx
    mov ecx, eax
    mov dword ptr [esp + 0x2C], eax
    call 0x00401880
    mov ecx, dword ptr [esp + 0x10]
    push 2
    call 0x00401610
    cmp dword ptr [0x{MODE:X}], 0
    jne value_borderless
    mov eax, 0x{WINDOWED:X}
    jmp value_ready
value_borderless:
    mov eax, 0x{BORDERLESS:X}
value_ready:
    push 0
    push 0x18
    push 0
    push eax
    push 0xC9
    push -0x61
    mov ecx, esi
    call 0x00401430
    mov ecx, dword ptr [esp + 0x14]
    mov edx, dword ptr [esi + 0xC]
    push 0
    push ebx
    push ebp
    push -1
    push ecx
    push edi
    push edx
    mov ecx, eax
    mov dword ptr [esp + 0x2C], eax
    call 0x00401910
    mov eax, dword ptr [esp + 0x2C]
    mov ebx, dword ptr [esp + 0x10]
    push eax
    mov ecx, ebx
    call 0x00401600
    push 2
    mov ecx, ebx
    call 0x00401610
    mov ecx, dword ptr [esp + 0x30]
    mov edx, dword ptr [esp + 0x1C]
    fld dword ptr [esp + 0x14]
    fsub dword ptr [esp + 0x34]
    push 0xFFBFBFFF
    push 0xCA
    push 0xC7
    push 6
    push 0xC6
    push 6
    push ecx
    push edx
    push ecx
    mov ecx, esi
    fstp dword ptr [esp]
    push edi
    push 1
    call 0x0040FCC0
    mov ebx, dword ptr [esp + 0x18]
    push 0
    jmp 0x00409917
"""

EVENT_ASM = f"""
    cmp eax, 0xC6
    je choose_windowed
    cmp eax, 0xC7
    jne original_dispatch
    mov eax, 1
    call 0x{SET_MODE:X}
    mov ecx, esi
    call 0x00408440
    pop esi
    ret 4
choose_windowed:
    xor eax, eax
    call 0x{SET_MODE:X}
    mov ecx, esi
    call 0x00408440
    pop esi
    ret 4
original_dispatch:
    cmp eax, 0xBE
    jmp 0x00409A95
"""

# DirectInput can retain the old cursor clip after a frame-style change.
# Release and reacquire it when returning to a resizable window.
SET_MODE_ASM = f"""
    push ebx
    push esi
    push edi
    push ebp
    mov ebp, eax
    cmp dword ptr [0x{MODE:X}], eax
    je mode_done
    call dword ptr [0x0061526C]
    test eax, eax
    je mode_done
    mov ebx, eax
    test ebp, ebp
    je restore_windowed
    push 0x{SAVED_RECT:X}
    push ebx
    call dword ptr [0x00615204]
    test eax, eax
    je mode_done
    push -16
    push ebx
    call dword ptr [0x00615234]
    mov dword ptr [0x{SAVED_STYLE:X}], eax
    push 0x00623840
    call dword ptr [0x00615164]
    test eax, eax
    je primary_monitor
    push 0x{MONITOR_FROM_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je primary_monitor
    push 2
    push ebx
    call eax
    test eax, eax
    je primary_monitor
    mov esi, eax
    push 0x00623840
    call dword ptr [0x00615164]
    test eax, eax
    je primary_monitor
    push 0x{MONITOR_INFO_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je primary_monitor
    mov dword ptr [0x{MONITOR_INFO:X}], 40
    push 0x{MONITOR_INFO:X}
    push esi
    call eax
    test eax, eax
    jne have_monitor
primary_monitor:
    mov dword ptr [0x{MONITOR_INFO + 4:X}], 0
    mov dword ptr [0x{MONITOR_INFO + 8:X}], 0
    push 0
    call dword ptr [0x00615250]
    mov dword ptr [0x{MONITOR_INFO + 12:X}], eax
    push 1
    call dword ptr [0x00615250]
    mov dword ptr [0x{MONITOR_INFO + 16:X}], eax
have_monitor:
    mov eax, dword ptr [0x{SAVED_STYLE:X}]
    and eax, 0xFF30FFFF
    or eax, 0x80000000
    push eax
    push -16
    push ebx
    call dword ptr [0x00615230]
    mov eax, dword ptr [0x{MONITOR_INFO + 12:X}]
    sub eax, dword ptr [0x{MONITOR_INFO + 4:X}]
    mov ecx, dword ptr [0x{MONITOR_INFO + 16:X}]
    sub ecx, dword ptr [0x{MONITOR_INFO + 8:X}]
    push 0x34
    push ecx
    push eax
    push dword ptr [0x{MONITOR_INFO + 8:X}]
    push dword ptr [0x{MONITOR_INFO + 4:X}]
    push 0
    push ebx
    call dword ptr [0x00615208]
    test eax, eax
    je restore_windowed
    mov eax, ebx
    call 0x{FORCE_CLEAR:X}
    mov dword ptr [0x{MODE:X}], 1
    mov eax, ebx
    call 0x{SAVE_CONFIG:X}
    jmp mode_done
restore_windowed:
    mov eax, dword ptr [0x{SAVED_STYLE:X}]
    push eax
    push -16
    push ebx
    call dword ptr [0x00615230]
    mov eax, dword ptr [0x{SAVED_RECT + 8:X}]
    sub eax, dword ptr [0x{SAVED_RECT:X}]
    mov ecx, dword ptr [0x{SAVED_RECT + 12:X}]
    sub ecx, dword ptr [0x{SAVED_RECT + 4:X}]
    push 0x34
    push ecx
    push eax
    push dword ptr [0x{SAVED_RECT + 4:X}]
    push dword ptr [0x{SAVED_RECT:X}]
    push 0
    push ebx
    call dword ptr [0x00615208]
    mov eax, ebx
    call 0x{FORCE_CLEAR:X}
    mov esi, dword ptr [0x01689900]
    test esi, esi
    je restored_input
    mov eax, dword ptr [esi]
    push esi
    call dword ptr [eax + 0x20]
    mov eax, dword ptr [esi]
    push esi
    call dword ptr [eax + 0x1C]
restored_input:
    mov dword ptr [0x{MODE:X}], 0
    mov eax, ebx
    call 0x{SAVE_CONFIG:X}
mode_done:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
"""

LOAD_CONFIG_ASM = f"""
    push ebx
    push esi
    push edi
    push ebp
    mov ebx, eax
    cmp dword ptr [0x{CONFIG_LOADED:X}], 0
    jne load_done
    cmp dword ptr [0x01689900], 0
    je load_done
    mov dword ptr [0x{CONFIG_LOADED:X}], 1
    call 0x{MOVIE_LOAD:X}
    call 0x{PREPARE_PATH:X}
    cmp byte ptr [0x{CONFIG_PATH:X}], 0
    je load_done
    push 0x{KERNEL_NAME:X}
    call dword ptr [0x00615164]
    test eax, eax
    je load_done
    push 0x{GET_PROFILE_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je load_done
    push 0x{CONFIG_PATH:X}
    push 24
    push 0x{CONFIG_RECORD:X}
    push 0x{INI_KEY:X}
    push 0x{INI_SECTION:X}
    call eax
    test eax, eax
    je load_done
    cmp dword ptr [0x{CONFIG_RECORD:X}], 1
    jne load_done
    cmp dword ptr [0x{CONFIG_RECORD + 4:X}], 1
    ja load_done
    mov esi, dword ptr [0x{CONFIG_RECORD + 16:X}]
    sub esi, dword ptr [0x{CONFIG_RECORD + 8:X}]
    cmp esi, 200
    jl load_done
    cmp esi, 10000
    jg load_done
    mov edi, dword ptr [0x{CONFIG_RECORD + 20:X}]
    sub edi, dword ptr [0x{CONFIG_RECORD + 12:X}]
    cmp edi, 150
    jl load_done
    cmp edi, 10000
    jg load_done
    push 0x34
    push edi
    push esi
    push dword ptr [0x{CONFIG_RECORD + 12:X}]
    push dword ptr [0x{CONFIG_RECORD + 8:X}]
    push 0
    push ebx
    call dword ptr [0x00615208]
    cmp dword ptr [0x{CONFIG_RECORD + 4:X}], 0
    je load_done
    mov eax, 1
    call 0x{SET_MODE:X}
load_done:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
"""

SAVE_CONFIG_ASM = f"""
    push ebx
    push esi
    push edi
    push ebp
    mov ebx, eax
    test ebx, ebx
    je save_done
    call 0x{PREPARE_PATH:X}
    cmp byte ptr [0x{CONFIG_PATH:X}], 0
    je save_done
    mov dword ptr [0x{CONFIG_RECORD:X}], 1
    mov eax, dword ptr [0x{MODE:X}]
    mov dword ptr [0x{CONFIG_RECORD + 4:X}], eax
    test eax, eax
    jne save_windowed_rect
    push 0x{CONFIG_RECORD + 8:X}
    push ebx
    call dword ptr [0x00615204]
    test eax, eax
    je save_done
    jmp have_saved_rect
save_windowed_rect:
    mov eax, dword ptr [0x{SAVED_RECT:X}]
    mov dword ptr [0x{CONFIG_RECORD + 8:X}], eax
    mov eax, dword ptr [0x{SAVED_RECT + 4:X}]
    mov dword ptr [0x{CONFIG_RECORD + 12:X}], eax
    mov eax, dword ptr [0x{SAVED_RECT + 8:X}]
    mov dword ptr [0x{CONFIG_RECORD + 16:X}], eax
    mov eax, dword ptr [0x{SAVED_RECT + 12:X}]
    mov dword ptr [0x{CONFIG_RECORD + 20:X}], eax
have_saved_rect:
    push 0x{KERNEL_NAME:X}
    call dword ptr [0x00615164]
    test eax, eax
    je save_done
    push 0x{WRITE_PROFILE_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je save_done
    push 0x{CONFIG_PATH:X}
    push 24
    push 0x{CONFIG_RECORD:X}
    push 0x{INI_KEY:X}
    push 0x{INI_SECTION:X}
    call eax
save_done:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
"""

PREPARE_PATH_ASM = f"""
    push ebx
    push esi
    push edi
    cmp byte ptr [0x{CONFIG_PATH:X}], 0
    jne path_done
    push 0x{KERNEL_NAME:X}
    call dword ptr [0x00615164]
    test eax, eax
    je path_done
    push 0x{MODULE_FILE_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je path_done
    push 480
    push 0x{CONFIG_PATH:X}
    push 0
    call eax
    test eax, eax
    je path_fail
    cmp eax, 480
    jae path_fail
    lea edi, [eax + 0x{CONFIG_PATH:X}]
find_separator:
    cmp edi, 0x{CONFIG_PATH:X}
    jbe path_fail
    dec edi
    cmp byte ptr [edi], 0x5C
    jne find_separator
    inc edi
    mov esi, 0x{INI_FILE_NAME:X}
copy_name:
    lodsb
    stosb
    test al, al
    jne copy_name
    jmp path_done
path_fail:
    mov byte ptr [0x{CONFIG_PATH:X}], 0
path_done:
    pop edi
    pop esi
    pop ebx
    ret
"""

MOVE_EXIT_ASM = f"""
    mov dword ptr [0x01689904], 0
    pushad
    mov eax, ebp
    call 0x{FORCE_CLEAR:X}
    mov eax, ebp
    call 0x{SAVE_CONFIG:X}
    popad
    jmp 0x0045C745
"""

ACTIVATION_ASM = f"""
    cmp word ptr [esp + 0x20], 0
    je original_activation
    pushad
    mov eax, ebp
    call 0x{LOAD_CONFIG:X}
    popad
original_activation:
    jmp 0x00614F00
"""

BOOT_AFTER_MOUSE_ASM = f"""
    pushad
    mov eax, dword ptr [esp + 0x40]
    call 0x{LOAD_CONFIG:X}
    popad
    xor edx, edx
    mov esi, dword ptr [esi]
    mov dword ptr [esp + 8], edx
    jmp 0x00526854
"""

# D3DSWAPEFFECT_COPY permits a destination RECT. Present only the centered
# back buffer rectangle so changing the client size does not stretch it.
PRESENT_ASM = f"""
    push ebx
    push ebp
    push edi
    xor edx, edx
    mov ebx, dword ptr [esi + 0x6F98C]
    test ebx, ebx
    je present_default
    mov ebp, dword ptr [0x{GET_CLIENT_PTR:X}]
    test ebp, ebp
    jne have_client_api
    push 0x00623840
    call dword ptr [0x00615164]
    test eax, eax
    je present_default
    push 0x{GET_CLIENT_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je present_default
    mov dword ptr [0x{GET_CLIENT_PTR:X}], eax
    mov ebp, eax
have_client_api:
    push 0x{CLIENT_RECT:X}
    push ebx
    call ebp
    test eax, eax
    je present_default
    mov ecx, dword ptr [0x{CLIENT_RECT + 8:X}]
    mov edx, dword ptr [0x{CLIENT_RECT + 12:X}]
    test ecx, ecx
    jle present_default
    test edx, edx
    jle present_default
    mov eax, dword ptr [esi + 0x6F974]
    mov ebp, dword ptr [esi + 0x6F978]
    test eax, eax
    jle present_default
    test ebp, ebp
    jle present_default
    mov ebx, ecx
    imul ebx, ebp
    mov edi, edx
    imul edi, eax
    cmp ebx, edi
    jle fit_width
    mov eax, edi
    cdq
    idiv ebp
    mov ecx, dword ptr [0x{CLIENT_RECT + 8:X}]
    sub ecx, eax
    sar ecx, 1
    mov dword ptr [0x{DEST_RECT:X}], ecx
    mov dword ptr [0x{DEST_RECT + 4:X}], 0
    add eax, ecx
    mov dword ptr [0x{DEST_RECT + 8:X}], eax
    mov ecx, dword ptr [0x{CLIENT_RECT + 12:X}]
    mov dword ptr [0x{DEST_RECT + 12:X}], ecx
    jmp present_rect
fit_width:
    mov edi, eax
    mov eax, ebx
    cdq
    idiv edi
    mov ecx, dword ptr [0x{CLIENT_RECT + 12:X}]
    sub ecx, eax
    sar ecx, 1
    mov dword ptr [0x{DEST_RECT:X}], 0
    mov dword ptr [0x{DEST_RECT + 4:X}], ecx
    mov edx, dword ptr [0x{CLIENT_RECT + 8:X}]
    mov dword ptr [0x{DEST_RECT + 8:X}], edx
    add eax, ecx
    mov dword ptr [0x{DEST_RECT + 12:X}], eax
present_rect:
    mov eax, dword ptr [esi + 0x6F98C]
    call 0x{CLEAR_UNUSED:X}
    mov edx, 0x{DEST_RECT:X}
    jmp present_now
present_default:
    xor edx, edx
present_now:
    pop edi
    pop ebp
    pop ebx
    mov eax, dword ptr [esi + 0x6EC6C]
    push 0
    push 0
    push edx
    push 0
    mov ecx, dword ptr [eax]
    push eax
    call dword ptr [ecx + 0x3C]
    jmp 0x0051957B
"""

# Present updates only its destination rectangle. Clear the whole client once
# when that rectangle changes; the next Present draws the centered image.
CLEAR_UNUSED_ASM = f"""
    push ebx
    push esi
    push edi
    push ebp
    mov ebx, eax
    mov eax, dword ptr [0x{CLIENT_RECT + 8:X}]
    cmp eax, dword ptr [0x{LAST_CLIENT_WIDTH:X}]
    jne clear_client
    mov eax, dword ptr [0x{CLIENT_RECT + 12:X}]
    cmp eax, dword ptr [0x{LAST_CLIENT_HEIGHT:X}]
    jne clear_client
    mov eax, dword ptr [0x{DEST_RECT:X}]
    cmp eax, dword ptr [0x{LAST_DEST_RECT:X}]
    jne clear_client
    mov eax, dword ptr [0x{DEST_RECT + 4:X}]
    cmp eax, dword ptr [0x{LAST_DEST_RECT + 4:X}]
    jne clear_client
    mov eax, dword ptr [0x{DEST_RECT + 8:X}]
    cmp eax, dword ptr [0x{LAST_DEST_RECT + 8:X}]
    jne clear_client
    mov eax, dword ptr [0x{DEST_RECT + 12:X}]
    cmp eax, dword ptr [0x{LAST_DEST_RECT + 12:X}]
    je clear_done
clear_client:
    mov ebp, dword ptr [0x{FILL_RECT_PTR:X}]
    test ebp, ebp
    jne have_fill_api
    push 0x00623840
    call dword ptr [0x00615164]
    test eax, eax
    je clear_done
    push 0x{FILL_RECT_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je clear_done
    mov dword ptr [0x{FILL_RECT_PTR:X}], eax
    mov ebp, eax
have_fill_api:
    push ebx
    call dword ptr [0x006152A8]
    test eax, eax
    je clear_done
    mov esi, eax
    push 4
    call dword ptr [0x00615030]
    test eax, eax
    je release_dc
    mov edi, eax
    push edi
    push 0x{CLIENT_RECT:X}
    push esi
    call ebp
    test eax, eax
    je release_dc
    mov eax, dword ptr [0x{CLIENT_RECT + 8:X}]
    mov dword ptr [0x{LAST_CLIENT_WIDTH:X}], eax
    mov eax, dword ptr [0x{CLIENT_RECT + 12:X}]
    mov dword ptr [0x{LAST_CLIENT_HEIGHT:X}], eax
    mov eax, dword ptr [0x{DEST_RECT:X}]
    mov dword ptr [0x{LAST_DEST_RECT:X}], eax
    mov eax, dword ptr [0x{DEST_RECT + 4:X}]
    mov dword ptr [0x{LAST_DEST_RECT + 4:X}], eax
    mov eax, dword ptr [0x{DEST_RECT + 8:X}]
    mov dword ptr [0x{LAST_DEST_RECT + 8:X}], eax
    mov eax, dword ptr [0x{DEST_RECT + 12:X}]
    mov dword ptr [0x{LAST_DEST_RECT + 12:X}], eax
release_dc:
    push esi
    push ebx
    call dword ptr [0x006152A4]
clear_done:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
"""

FORCE_CLEAR_ASM = f"""
    pushad
    mov ebx, eax
    mov eax, dword ptr [0x{GET_CLIENT_PTR:X}]
    test eax, eax
    jne have_force_client_api
    push 0x00623840
    call dword ptr [0x00615164]
    test eax, eax
    je force_done
    push 0x{GET_CLIENT_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je force_done
    mov dword ptr [0x{GET_CLIENT_PTR:X}], eax
have_force_client_api:
    push 0x{CLIENT_RECT:X}
    push ebx
    call eax
    test eax, eax
    je force_done
    mov dword ptr [0x{LAST_CLIENT_WIDTH:X}], 0
    mov eax, ebx
    call 0x{CLEAR_UNUSED:X}
force_done:
    popad
    ret
"""

MOVIE_RENDER_ASM = f"""
    fstp dword ptr [esp + 0x8]
    pushad
    mov eax, 0x{MOVIE_ON:X}
    cmp dword ptr [0x{MOVIE_SKIP_STATE:X}], 0
    je movie_text_ready
    mov eax, 0x{MOVIE_OFF:X}
movie_text_ready:
    push 0
    push 0
    push 0
    push eax
    push 0xCC
    push 6
    mov ecx, esi
    call 0x00401430
    mov ebx, eax
    push 0
    push 0x3F800000
    push 0x3F000000
    push 0xFFBFBFFF
    push dword ptr [esp + 0x38]
    push dword ptr [0x00644AE8]
    push dword ptr [esi + 0xC]
    mov ecx, ebx
    call 0x00401910
    push dword ptr [0x00644A74]
    mov ecx, ebx
    call 0x00401600
    popad
    fld dword ptr [esp + 0x8]
    fadd dword ptr [esp + 0xC]
    fld dword ptr [esp + 0x10]
    fsubr st(0), st(1)
    jmp 0x004043DD
"""

MOVIE_EVENT_ASM = f"""
    mov eax, dword ptr [eax + 0x10]
    cmp eax, 0xCC
    jne original_option
    xor dword ptr [0x{MOVIE_SKIP_STATE:X}], 1
    pushad
    call 0x{MOVIE_SAVE:X}
    popad
    jmp 0x004046BD
original_option:
    add eax, -0xD
    jmp 0x00404535
"""

MOVIE_STARTUP_ASM = f"""
    mov dword ptr [esp + 0x14], 0x0063697C
    pushad
    call 0x{MOVIE_LOAD:X}
    popad
    cmp dword ptr [0x{MOVIE_SKIP_STATE:X}], 0
    jne skip_startup_movies
    jmp 0x0045E4A0
skip_startup_movies:
    jmp 0x0045E54D
"""

MOVIE_LOAD_ASM = f"""
    push ebx
    call 0x{PREPARE_PATH:X}
    cmp byte ptr [0x{CONFIG_PATH:X}], 0
    je movie_load_done
    push 0x{KERNEL_NAME:X}
    call dword ptr [0x00615164]
    test eax, eax
    je movie_load_done
    push 0x{MOVIE_READ_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je movie_load_done
    push 0x{CONFIG_PATH:X}
    push 0
    push 0x{MOVIE_KEY:X}
    push 0x{MOVIE_SECTION:X}
    call eax
    cmp eax, 1
    jne movie_load_done
    mov dword ptr [0x{MOVIE_SKIP_STATE:X}], 1
movie_load_done:
    pop ebx
    ret
"""

MOVIE_SAVE_ASM = f"""
    push ebx
    call 0x{PREPARE_PATH:X}
    cmp byte ptr [0x{CONFIG_PATH:X}], 0
    je movie_save_done
    push 0x{KERNEL_NAME:X}
    call dword ptr [0x00615164]
    test eax, eax
    je movie_save_done
    push 0x{MOVIE_WRITE_NAME:X}
    push eax
    call dword ptr [0x00615148]
    test eax, eax
    je movie_save_done
    mov ebx, 0x{MOVIE_VALUE_ZERO:X}
    cmp dword ptr [0x{MOVIE_SKIP_STATE:X}], 0
    je movie_value_ready
    mov ebx, 0x{MOVIE_VALUE_ONE:X}
movie_value_ready:
    push 0x{CONFIG_PATH:X}
    push ebx
    push 0x{MOVIE_KEY:X}
    push 0x{MOVIE_SECTION:X}
    call eax
movie_save_done:
    pop ebx
    ret
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "extension.bin")
    args = parser.parse_args()
    assembler = Ks(KS_ARCH_X86, KS_MODE_32)
    payload = bytearray(SIZE)
    regions = []
    for name, address, source in (
        ("render", RENDER, RENDER_ASM),
        ("event", EVENT, EVENT_ASM),
        ("window mode", SET_MODE, SET_MODE_ASM),
        ("load config", LOAD_CONFIG, LOAD_CONFIG_ASM),
        ("save config", SAVE_CONFIG, SAVE_CONFIG_ASM),
        ("prepare path", PREPARE_PATH, PREPARE_PATH_ASM),
        ("move exit", MOVE_EXIT, MOVE_EXIT_ASM),
        ("activation", ACTIVATION, ACTIVATION_ASM),
        ("boot after mouse", BOOT_AFTER_MOUSE, BOOT_AFTER_MOUSE_ASM),
        ("present", PRESENT, PRESENT_ASM),
        ("clear unused", CLEAR_UNUSED, CLEAR_UNUSED_ASM),
        ("force clear", FORCE_CLEAR, FORCE_CLEAR_ASM),
        ("startup movie menu row", MOVIE_RENDER, MOVIE_RENDER_ASM),
        ("startup movie click", MOVIE_EVENT, MOVIE_EVENT_ASM),
        ("startup movie guard", MOVIE_STARTUP, MOVIE_STARTUP_ASM),
        ("load startup movie setting", MOVIE_LOAD, MOVIE_LOAD_ASM),
        ("save startup movie setting", MOVIE_SAVE, MOVIE_SAVE_ASM),
    ):
        encoded, _ = assembler.asm(source, addr=address)
        start = address - BASE
        end = start + len(encoded)
        regions.append((name, start, end, bytes(encoded)))
    for name, address, value in (
        ("label", LABEL, b"DISPLAY MODE\0"),
        ("windowed", WINDOWED, b"WINDOWED\0"),
        ("borderless", BORDERLESS, b"BORDERLESS\0"),
        ("monitor from", MONITOR_FROM_NAME, b"MonitorFromWindow\0"),
        ("monitor info", MONITOR_INFO_NAME, b"GetMonitorInfoA\0"),
        ("module file", MODULE_FILE_NAME, b"GetModuleFileNameA\0"),
        ("read profile", GET_PROFILE_NAME, b"GetPrivateProfileStructA\0"),
        ("write profile", WRITE_PROFILE_NAME, b"WritePrivateProfileStructA\0"),
        ("ini file", INI_FILE_NAME, b"ProjectEdenPatch.ini\0"),
        ("ini section", INI_SECTION, b"Display\0"),
        ("ini key", INI_KEY, b"State\0"),
        ("kernel32", KERNEL_NAME, b"kernel32.dll\0"),
        ("get client", GET_CLIENT_NAME, b"GetClientRect\0"),
        ("fill rect", FILL_RECT_NAME, b"FillRect\0"),
        ("startup movies on", MOVIE_ON, b"STARTUP MOVIES: ON\0"),
        ("startup movies off", MOVIE_OFF, b"STARTUP MOVIES: OFF\0"),
        ("movie section", MOVIE_SECTION, b"General\0"),
        ("movie key", MOVIE_KEY, b"SkipStartupMovies\0"),
        ("movie read API", MOVIE_READ_NAME, b"GetPrivateProfileIntA\0"),
        ("movie write API", MOVIE_WRITE_NAME, b"WritePrivateProfileStringA\0"),
        ("movie value zero", MOVIE_VALUE_ZERO, b"0\0"),
        ("movie value one", MOVIE_VALUE_ONE, b"1\0"),
    ):
        start = address - BASE
        regions.append((name, start, start + len(value), value))
    for name, start, end, value in regions:
        if end > SIZE:
            raise ValueError(f"{name} extends beyond the section")
        for other_name, other_start, other_end, _ in regions:
            if other_name != name and start < other_end and other_start < end:
                raise ValueError(f"{name} overlaps {other_name}")
        payload[start:end] = value
        print(f"{name}: 0x{BASE + start:08X}..0x{BASE + end:08X}")
    args.output.write_bytes(payload)
    print(f"SHA-256: {hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
