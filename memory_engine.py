"""
Win32 memory engine, dynamic AOB resolver, and x64 code-cave manager
for Dead or Alive 6 Last Round (DOA6LR.exe).

Offline / single-player only: continuously verifies the game's online
match state flag and refuses to enable or maintain cheats online.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import re
import struct
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# Win32 constants
PROCESS_ALL_ACCESS_NEEDED = (
    0x0008  # PROCESS_VM_OPERATION
    | 0x0010  # PROCESS_VM_READ
    | 0x0020  # PROCESS_VM_WRITE
    | 0x0400  # PROCESS_QUERY_INFORMATION
)
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
MEM_FREE = 0x10000
PAGE_EXECUTE_READWRITE = 0x40
LIST_MODULES_ALL = 0x03


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_uint64),
        ("AllocationBase", ctypes.c_uint64),
        ("AllocationProtect", wt.DWORD),
        ("PartitionId", wt.WORD),
        ("Reserved1", wt.WORD),
        ("RegionSize", ctypes.c_uint64),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


class Win32Memory:
    """Thin ctypes wrapper around Win32 process memory operations."""

    def __init__(self) -> None:
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.u32 = ctypes.WinDLL("user32", use_last_error=True)

        self.k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        self.k32.OpenProcess.restype = wt.HANDLE
        self.k32.CloseHandle.argtypes = [wt.HANDLE]
        self.k32.CloseHandle.restype = wt.BOOL
        self.k32.ReadProcessMemory.argtypes = [
            wt.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.k32.ReadProcessMemory.restype = wt.BOOL
        self.k32.WriteProcessMemory.argtypes = [
            wt.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.k32.WriteProcessMemory.restype = wt.BOOL
        self.k32.VirtualAllocEx.argtypes = [
            wt.HANDLE,
            ctypes.c_void_p,
            ctypes.c_size_t,
            wt.DWORD,
            wt.DWORD,
        ]
        self.k32.VirtualAllocEx.restype = ctypes.c_uint64
        self.k32.VirtualFreeEx.argtypes = [
            wt.HANDLE,
            ctypes.c_void_p,
            ctypes.c_size_t,
            wt.DWORD,
        ]
        self.k32.VirtualFreeEx.restype = wt.BOOL
        self.k32.VirtualProtectEx.argtypes = [
            wt.HANDLE,
            ctypes.c_void_p,
            ctypes.c_size_t,
            wt.DWORD,
            ctypes.POINTER(wt.DWORD),
        ]
        self.k32.VirtualProtectEx.restype = wt.BOOL
        self.k32.VirtualQueryEx.argtypes = [
            wt.HANDLE,
            ctypes.c_void_p,
            ctypes.POINTER(MEMORY_BASIC_INFORMATION),
            ctypes.c_size_t,
        ]
        self.k32.VirtualQueryEx.restype = ctypes.c_size_t
        self.u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.u32.GetAsyncKeyState.restype = ctypes.c_short


class AsmBuilder:
    """Minimal deterministic x64 machine-code assembler with label & RIP fixups."""

    def __init__(self, base_va: int) -> None:
        self.base_va = base_va
        self.buf = bytearray()
        self.labels: Dict[str, int] = {}
        # (offset_of_rel8, label)
        self._rel8_fixups: List[Tuple[int, str]] = []
        # (offset_of_rel32, instr_end_offset, target_va_or_label, is_label)
        self._rel32_fixups: List[Tuple[int, int, object, bool]] = []

    @property
    def pos(self) -> int:
        return len(self.buf)

    @property
    def va(self) -> int:
        return self.base_va + len(self.buf)

    def label(self, name: str) -> None:
        self.labels[name] = len(self.buf)

    def emit(self, raw: bytes) -> None:
        self.buf.extend(raw)

    def jcc_short(self, opcode: int, target: str) -> None:
        self.buf.append(opcode)
        self._rel8_fixups.append((len(self.buf), target))
        self.buf.append(0)

    def jcc_near(self, short_opcode: int, target: str) -> None:
        self.buf.append(0x0F)
        self.buf.append(short_opcode + 0x10)
        rel_off = len(self.buf)
        self.buf.extend(b"\x00\x00\x00\x00")
        self._rel32_fixups.append((rel_off, len(self.buf), target, True))

    def jmp_short(self, target: str) -> None:
        self.jcc_short(0xEB, target)

    def jmp_near(self, target: str) -> None:
        self.buf.append(0xE9)
        rel_off = len(self.buf)
        self.buf.extend(b"\x00\x00\x00\x00")
        self._rel32_fixups.append((rel_off, len(self.buf), target, True))

    def jmp_abs_rel32(self, target_va: int) -> None:
        self.buf.append(0xE9)
        rel_off = len(self.buf)
        self.buf.extend(b"\x00\x00\x00\x00")
        self._rel32_fixups.append((rel_off, len(self.buf), target_va, False))

    def rip_mem_op(self, prefix: bytes, target_va: int, trailing: bytes = b"") -> None:
        """Emit instruction whose disp32 is relative to end of full instruction."""
        self.buf.extend(prefix)
        rel_off = len(self.buf)
        self.buf.extend(b"\x00\x00\x00\x00")
        self.buf.extend(trailing)
        self._rel32_fixups.append((rel_off, len(self.buf), target_va, False))

    def finalize(self) -> bytes:
        for off, lbl in self._rel8_fixups:
            if lbl not in self.labels:
                raise KeyError(f"Unknown label {lbl!r}")
            rel = self.labels[lbl] - (off + 1)
            if not (-128 <= rel <= 127):
                raise ValueError(f"Short jump to {lbl!r} out of range: {rel}")
            struct.pack_into("<b", self.buf, off, rel)

        for rel_off, end_off, target, is_lbl in self._rel32_fixups:
            t_va = (self.base_va + self.labels[str(target)]) if is_lbl else int(target)
            rel = t_va - (self.base_va + end_off)
            if not (-0x80000000 <= rel <= 0x7FFFFFFF):
                raise ValueError(f"rel32 out of ±2GB range: 0x{rel:X}")
            struct.pack_into("<i", self.buf, rel_off, rel)

        return bytes(self.buf)


def compile_aob(pattern: str) -> re.Pattern[bytes]:
    tokens = pattern.strip().split()
    parts: List[bytes] = []
    for tok in tokens:
        if tok in ("?", "??", "*"):
            parts.append(b".")
        else:
            parts.append(re.escape(bytes([int(tok, 16)])))
    return re.compile(b"".join(parts), re.DOTALL)


def parse_rel32(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<i", buf, offset)[0]


@dataclass
class ResolvedSymbols:
    base: int
    text_va: int
    text_size: int
    owner_ptr_va: int
    reward_ptr_va: int
    save_data_ptr_va: int
    fighter_map_ptr_va: int
    score_global_ptr_va: int
    online_obj_ptr_va: int
    apply_dmg_va: int
    break_helper_va: int
    score_mul_va: int
    timescale_va: int
    timer1_patch_va: int
    timer2_patch_va: int
    chal1_patch_va: int
    chal2_patch_va: int
    quest_win_patch_va: int
    quest_stars_patch_va: int


@dataclass
class FighterSnapshot:
    fighter_ptr: int
    damage_taken: int
    max_hp: int
    break_cur: int
    break_max: int
    damage_mode: int
    active: int
    dmg_active: int = 0

    @property
    def current_hp(self) -> int:
        return max(0, self.max_hp - self.damage_taken)


@dataclass
class GameSnapshot:
    attached: bool = False
    pid: int = 0
    offline: bool = True
    online_flag: int = 255
    in_match: bool = False
    money: int = 0
    owner_exp: int = 0
    reward_money: int = 0
    reward_exp: int = 0
    frame_speed: float = 1.0
    live_score: int = 0
    p1: Optional[FighterSnapshot] = None
    p2: Optional[FighterSnapshot] = None
    chara_points_sample: Tuple[int, ...] = ()


# Shared config layout inside our 4KB near-cave page (starting at offset 0x000)
CFG_P1_INF_HP = 0x00       # u32
CFG_P2_OHKO = 0x04         # u32
CFG_P1_MAX_BRK = 0x08      # u32
CFG_P2_EMPTY_BRK = 0x0C    # u32
CFG_SCORE_MULT = 0x10      # u32
CFG_SCORE_MAX_MODE = 0x14  # u32
CFG_SPEED_ENABLED = 0x18   # u32
CFG_SPEED_SCALE = 0x1C     # f32
CFG_SCORE_TASK_PTR = 0x20  # u64
CFG_ONLINE_OBJ_PTR = 0x28  # u64
CFG_FIGHTER_MAP_PTR = 0x30 # u64

CAVE_APPLY_DMG_OFF = 0x100
CAVE_BREAK_HELPER_OFF = 0x300
CAVE_SCORE_MUL_OFF = 0x500
CAVE_TIMESCALE_OFF = 0x700


AOBS = {
    "OwnerStruct": ("48 8B 05 ?? ?? ?? ?? 48 83 C4 38 C3 48 8D 0D 30", 3),
    "RewardStruct": ("48 8B 05 ?? ?? ?? ?? 8B 40 10 48 83 C4 28", 3),
    "FighterMap": ("48 8B 05 ?? ?? ?? ?? 48 85 C0 75 22 48 89 37 48", 3),
    "ScoreGlobal": ("48 8B 05 ?? ?? ?? ?? 8B 90 10 05 00 00 33 C0 89 54 24 38 83 7C 84 38 00 75 27", 3),
    "OnlineLobby": ("48 8B 05 ?? ?? ?? ?? 48 85 C0 74 11 0F B6 80 F8 08 00 00 3C 01 0F 94 C0 48 83 C4 28 C3 B0 FF", 3),
    "SaveDataCall": ("E8 ?? ?? ?? ?? 48 8B 0D ?? ?? ?? ?? 44 8B C3 48 83 C1 78 BA 5E F5 4B 4F 48 8B F8 E8 ?? ?? ?? ?? 48 98 48 83 F8 64", 1),
    # Wildcarded at patched bytes so re-attaching succeeds even if orphaned hooks/patches remain
    "ApplyDamage": ("?? ?? ?? ?? ?? ?? ?? 44 3B F0 41 0F 9D C4 43 8D 0C 3E 3B C8 89 4E 20 0F 9D 45 67 7C 05 89 46 20 8B C8 85 C9 79 05 89 56 20 8B CA 83 7E 18 02", 0),
    "BreakHelper": ("?? ?? ?? ?? ?? ?? ?? 66 89 3B 74 0C 66 85 FF 75 07 0F B7 43 02 66", 0),
    "ScoreMul": ("?? ?? ?? ?? ?? ?? ?? ?? 48 C7 83 60 01 00 00 00 00 00 00 48 01 83 68 01 00 00 48 83", 0),
    "TimeScale": ("?? ?? ?? ?? ?? ?? ?? ?? F3 48 0F 2A C0 F3 0F 5E C8 F3 0F 58 8B 70 01 00 00", 0),
    "Timer1": ("F3 0F 5E C1 F3 0F 59 41 14 F3 0F 58 45 08 ?? ?? ?? ?? ?? 0F B6 87 20 02", 0x0E),
    "Timer2": ("F3 0F 5E C1 F3 0F 59 41 14 F3 0F 58 46 08 ?? ?? ?? ?? ?? 0F B6 87 20 02", 0x0E),
    "Challenge1": ("24 01 00 00 ?? ?? ?? EB 4F 83 F9 01 75 37 44 88 7C 24", 0x04),
    "Challenge2": ("24 01 00 00 ?? ?? ?? EB 02 32 C0 4C 8D 5C 24 60 49 8B", 0x04),
    "QuestWin": ("0F B6 4E 58 48 8B 45 48 ?? ?? ?? ?? ?? ?? 44 8B 46 38 48 8B 4D F0", 0x08),
    "QuestStars": ("88 5D 50 48 8B 0F 48 8B 01 48 8B 50 28 49 3B D4 0F 85 ?? ?? ?? ?? 0F B6 81 ?? 01 00 00 88 45 51", 0x16),
}


class DOA6LRMemoryEngine:
    """Manages attachment, scanning, live telemetry, inline patches, and code caves."""

    PROCESS_NAME = "DOA6LR.exe"

    def __init__(self) -> None:
        self.w32 = Win32Memory()
        self.handle: Optional[int] = None
        self.pid: int = 0
        self.syms: Optional[ResolvedSymbols] = None
        self.cave_base: int = 0
        self.installed_hooks: Dict[str, Tuple[int, bytes]] = {}
        self.installed_patches: Dict[str, List[Tuple[int, bytes]]] = {}

    @property
    def is_attached(self) -> bool:
        return bool(self.handle and self.syms)

    def find_pid(self) -> int:
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"IMAGENAME eq {self.PROCESS_NAME}", "/FO", "CSV", "/NH"],
                text=True,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            ).strip()
            for line in out.splitlines():
                if self.PROCESS_NAME.lower() in line.lower():
                    parts = [p.strip('"') for p in line.split(",")]
                    if len(parts) >= 2 and parts[1].isdigit():
                        return int(parts[1])
        except Exception:
            pass
        return 0

    def detach(self, restore_patches: bool = True) -> None:
        if self.handle and restore_patches:
            try:
                self.disable_all_patches()
                self.uninstall_all_hooks()
                if self.cave_base:
                    self.w32.k32.VirtualFreeEx(self.handle, ctypes.c_void_p(self.cave_base), 0, MEM_RELEASE)
            except Exception:
                pass
        self.cave_base = 0
        self.installed_hooks.clear()
        self.installed_patches.clear()
        if self.handle:
            self.w32.k32.CloseHandle(self.handle)
        self.handle = None
        self.pid = 0
        self.syms = None

    def attach(self) -> bool:
        pid = self.find_pid()
        if not pid:
            self.detach(restore_patches=False)
            return False
        if self.handle and self.pid == pid and self.syms:
            # Verify process still alive by reading MZ header
            hdr = self.read_bytes(self.syms.base, 2)
            if hdr == b"MZ":
                return True
            self.detach(restore_patches=False)

        self.detach(restore_patches=False)
        h = self.w32.k32.OpenProcess(PROCESS_ALL_ACCESS_NEEDED, False, pid)
        if not h:
            return False
        self.handle = h
        self.pid = pid

        mods = (wt.HMODULE * 1024)()
        needed = wt.DWORD()
        if not self.w32.psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(needed), LIST_MODULES_ALL):
            self.detach(restore_patches=False)
            return False
        base = mods[0]
        if not base:
            self.detach(restore_patches=False)
            return False

        try:
            self.syms = self._scan_symbols(base)
        except Exception:
            self.detach(restore_patches=False)
            raise
        return True

    def read_bytes(self, addr: int, size: int) -> bytes:
        if not self.handle or not addr or size <= 0:
            return b""
        buf = (ctypes.c_ubyte * size)()
        read_len = ctypes.c_size_t()
        ok = self.w32.k32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(read_len)
        )
        return bytes(buf[: read_len.value]) if ok else b""

    def write_bytes(self, addr: int, data: bytes, protect_rwx: bool = False) -> bool:
        if not self.handle or not addr or not data:
            return False
        old_prot = wt.DWORD()
        changed = False
        if protect_rwx:
            changed = bool(
                self.w32.k32.VirtualProtectEx(
                    self.handle,
                    ctypes.c_void_p(addr),
                    len(data),
                    PAGE_EXECUTE_READWRITE,
                    ctypes.byref(old_prot),
                )
            )
        written = ctypes.c_size_t()
        ok = bool(
            self.w32.k32.WriteProcessMemory(
                self.handle, ctypes.c_void_p(addr), data, len(data), ctypes.byref(written)
            )
        )
        if changed:
            dummy = wt.DWORD()
            self.w32.k32.VirtualProtectEx(
                self.handle, ctypes.c_void_p(addr), len(data), old_prot.value, ctypes.byref(dummy)
            )
        return ok and written.value == len(data)

    def read_u8(self, addr: int) -> int:
        b = self.read_bytes(addr, 1)
        return b[0] if len(b) == 1 else 0

    def read_u16(self, addr: int) -> int:
        b = self.read_bytes(addr, 2)
        return struct.unpack("<H", b)[0] if len(b) == 2 else 0

    def read_u32(self, addr: int) -> int:
        b = self.read_bytes(addr, 4)
        return struct.unpack("<I", b)[0] if len(b) == 4 else 0

    def read_u64(self, addr: int) -> int:
        b = self.read_bytes(addr, 8)
        return struct.unpack("<Q", b)[0] if len(b) == 8 else 0

    def read_f32(self, addr: int) -> float:
        b = self.read_bytes(addr, 4)
        return struct.unpack("<f", b)[0] if len(b) == 4 else 0.0

    def write_u8(self, addr: int, val: int) -> bool:
        return self.write_bytes(addr, struct.pack("<B", val & 0xFF))

    def write_u16(self, addr: int, val: int) -> bool:
        return self.write_bytes(addr, struct.pack("<H", val & 0xFFFF))

    def write_u32(self, addr: int, val: int) -> bool:
        return self.write_bytes(addr, struct.pack("<I", val & 0xFFFFFFFF))

    def write_u64(self, addr: int, val: int) -> bool:
        return self.write_bytes(addr, struct.pack("<Q", val & 0xFFFFFFFFFFFFFFFF))

    def write_f32(self, addr: int, val: float) -> bool:
        return self.write_bytes(addr, struct.pack("<f", float(val)))

    def _get_text_section(self, base: int) -> Tuple[int, int]:
        hdr = self.read_bytes(base, 0x1000)
        if len(hdr) < 0x100 or hdr[:2] != b"MZ":
            raise RuntimeError("Invalid PE header in DOA6LR.exe memory.")
        e_lfanew = struct.unpack_from("<I", hdr, 0x3C)[0]
        num_sec = struct.unpack_from("<H", hdr, e_lfanew + 0x06)[0]
        opt_sz = struct.unpack_from("<H", hdr, e_lfanew + 0x14)[0]
        sec_off = e_lfanew + 0x18 + opt_sz
        for i in range(num_sec):
            off = sec_off + i * 40
            if off + 40 > len(hdr):
                break
            name = hdr[off : off + 8].rstrip(b"\x00")
            if name == b".text":
                vsize = struct.unpack_from("<I", hdr, off + 8)[0]
                vaddr = struct.unpack_from("<I", hdr, off + 12)[0]
                return vaddr, vsize
        raise RuntimeError("Could not locate .text section header.")

    def _scan_symbols(self, base: int) -> ResolvedSymbols:
        text_rva, text_sz = self._get_text_section(base)
        chunks: List[bytes] = []
        valid_bytes = 0
        for off in range(0, text_sz, 0x100000):
            sz = min(0x100000, text_sz - off)
            d = self.read_bytes(base + text_rva + off, sz)
            valid_bytes += len(d)
            if len(d) != sz:
                d = d + b"\x00" * (sz - len(d))
            chunks.append(d)
        text = b"".join(chunks)
        if valid_bytes < text_sz // 2:
            raise RuntimeError("Failed to read decrypted .text section from DOA6LR.exe.")

        hits_va: Dict[str, int] = {}
        for name, (pat, _) in AOBS.items():
            rx = compile_aob(pat)
            m = rx.search(text)
            if not m:
                raise RuntimeError(f"AOB signature '{name}' not found in live DOA6LR.exe.")
            if rx.search(text, m.start() + 1):
                raise RuntimeError(f"AOB signature '{name}' matched multiple locations.")
            hits_va[name] = base + text_rva + m.start()

        def rip_at(name: str) -> int:
            va = hits_va[name]
            off = va - (base + text_rva)
            op_disp = AOBS[name][1]
            disp = parse_rel32(text, off + op_disp)
            return va + op_disp + 4 + disp

        # Resolve SaveData through GetSaveData call
        save_call_va = hits_va["SaveDataCall"]
        save_call_off = save_call_va - (base + text_rva)
        get_save_va = save_call_va + 5 + parse_rel32(text, save_call_off + 1)
        get_save_bytes = self.read_bytes(get_save_va, 0x60)
        save_ptr_va = 0
        for o in range(0x20, 0x55):
            if get_save_bytes[o : o + 3] == b"\x48\x8B\x05":
                save_ptr_va = get_save_va + o + 7 + parse_rel32(get_save_bytes, o + 3)
                break
        if not save_ptr_va:
            raise RuntimeError("Failed to resolve SaveData pointer inside GetSaveData.")

        return ResolvedSymbols(
            base=base,
            text_va=text_rva,
            text_size=text_sz,
            owner_ptr_va=rip_at("OwnerStruct"),
            reward_ptr_va=rip_at("RewardStruct"),
            save_data_ptr_va=save_ptr_va,
            fighter_map_ptr_va=rip_at("FighterMap"),
            score_global_ptr_va=rip_at("ScoreGlobal"),
            online_obj_ptr_va=rip_at("OnlineLobby"),
            apply_dmg_va=hits_va["ApplyDamage"],
            break_helper_va=hits_va["BreakHelper"],
            score_mul_va=hits_va["ScoreMul"],
            timescale_va=hits_va["TimeScale"],
            timer1_patch_va=hits_va["Timer1"] + AOBS["Timer1"][1],
            timer2_patch_va=hits_va["Timer2"] + AOBS["Timer2"][1],
            chal1_patch_va=hits_va["Challenge1"] + AOBS["Challenge1"][1],
            chal2_patch_va=hits_va["Challenge2"] + AOBS["Challenge2"][1],
            quest_win_patch_va=hits_va["QuestWin"] + AOBS["QuestWin"][1],
            quest_stars_patch_va=hits_va["QuestStars"] + AOBS["QuestStars"][1],
        )

    def ensure_cave_page(self) -> int:
        if self.cave_base:
            return self.cave_base
        if not self.handle or not self.syms:
            raise RuntimeError("Not attached.")

        # Search for MEM_FREE region within ±1.5 GB of DOA6LR.exe .text (above base first, then below)
        center = self.syms.base + self.syms.text_va
        low = max(0x10000000, center - 0x60000000)
        high = center + 0x60000000
        mbi = MEMORY_BASIC_INFORMATION()
        mbi_sz = ctypes.sizeof(mbi)

        for r_start, r_end in ((max(low, self.syms.base), high), (low, self.syms.base)):
            addr = r_start
            while addr < r_end:
                res = self.w32.k32.VirtualQueryEx(
                    self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), mbi_sz
                )
                if not res:
                    break
                if mbi.State == MEM_FREE and mbi.RegionSize >= 0x10000:
                    cand = (mbi.BaseAddress + 0xFFFF) & ~0xFFFF
                    if (
                        cand + 0x1000 <= mbi.BaseAddress + mbi.RegionSize
                        and abs(cand - center) < 0x70000000
                    ):
                        alloc = self.w32.k32.VirtualAllocEx(
                            self.handle,
                            ctypes.c_void_p(cand),
                            0x1000,
                            MEM_COMMIT | MEM_RESERVE,
                            PAGE_EXECUTE_READWRITE,
                        )
                        if alloc:
                            self.cave_base = alloc
                            self._init_cave_memory()
                            return alloc
                addr = mbi.BaseAddress + mbi.RegionSize

        raise RuntimeError("Could not allocate executable code cave within ±2GB of DOA6LR.exe.")

    def _init_cave_memory(self) -> None:
        assert self.syms and self.cave_base
        self.write_bytes(self.cave_base, b"\x00" * 0x100)
        self.write_u32(self.cave_base + CFG_SCORE_MULT, 10)
        self.write_f32(self.cave_base + CFG_SPEED_SCALE, 1.5)
        self.write_u64(self.cave_base + CFG_ONLINE_OBJ_PTR, self.syms.online_obj_ptr_va)
        self.write_u64(self.cave_base + CFG_FIGHTER_MAP_PTR, self.syms.fighter_map_ptr_va)

    def _emit_online_guard(self, asm: AsmBuilder, lbl_online_abort: str, lbl_ok: str) -> None:
        """Uses RCX as scratch. Jumps to lbl_online_abort if Online flag < 5."""
        ptr_slot = self.cave_base + CFG_ONLINE_OBJ_PTR
        asm.rip_mem_op(b"\x48\x8B\x0D", ptr_slot)      # mov rcx, [rip + slot]
        asm.emit(b"\x48\x8B\x09")                        # mov rcx, [rcx]
        asm.emit(b"\x48\x85\xC9")                        # test rcx, rcx
        asm.jcc_short(0x74, lbl_ok)                      # jz lbl_ok
        asm.emit(b"\x80\xB9\xF8\x08\x00\x00\x05")        # cmp byte ptr [rcx+0x8F8], 5
        asm.jcc_near(0x72, lbl_online_abort)             # jb near lbl_online_abort
        asm.label(lbl_ok)

    def _emit_fmap_head(self, asm: AsmBuilder, lbl_fail: str) -> None:
        """Loads FighterMap RB-tree head into RCX. Jumps to lbl_fail if null."""
        fmap_slot = self.cave_base + CFG_FIGHTER_MAP_PTR
        asm.rip_mem_op(b"\x48\x8B\x0D", fmap_slot)       # mov rcx, [rip + slot]
        asm.emit(b"\x48\x8B\x09")                        # mov rcx, [rcx] (fmap)
        asm.emit(b"\x48\x85\xC9")                        # test rcx, rcx
        asm.jcc_near(0x74, lbl_fail)
        asm.emit(b"\x48\x8B\x09")                        # mov rcx, [rcx] (head)
        asm.emit(b"\x48\x85\xC9")                        # test rcx, rcx
        asm.jcc_near(0x74, lbl_fail)

    def _emit_read_node_fighter_into_rdx(
        self, asm: AsmBuilder, head_offset: int, expected_key: int, lbl_fail: str
    ) -> None:
        """Assuming RCX == head, resolves Fighter* into RDX or jumps to lbl_fail."""
        if head_offset == 0:
            asm.emit(b"\x48\x8B\x11")                    # mov rdx, [rcx]
        else:
            asm.emit(b"\x48\x8B\x51" + bytes([head_offset]))  # mov rdx, [rcx+off]
        asm.emit(b"\x48\x85\xD2")                        # test rdx, rdx
        asm.jcc_near(0x74, lbl_fail)
        asm.emit(b"\x80\x7A\x19\x00")                    # cmp byte ptr [rdx+0x19], 0
        asm.jcc_near(0x75, lbl_fail)
        asm.emit(b"\x80\x7A\x20" + bytes([expected_key]))  # cmp byte ptr [rdx+0x20], key
        asm.jcc_near(0x75, lbl_fail)
        asm.emit(b"\x48\x8B\x52\x28")                    # mov rdx, [rdx+0x28] (slot)
        asm.emit(b"\x48\x85\xD2")                        # test rdx, rdx
        asm.jcc_near(0x74, lbl_fail)
        asm.emit(b"\x48\x8B\x92\x88\x00\x00\x00")        # mov rdx, [rdx+0x88] (fighter)

    def _read_canonical_or_verify(self, patch_va: int, canonical_orig: bytes, label: str) -> bytes:
        cur = self.read_bytes(patch_va, len(canonical_orig))
        if cur == canonical_orig:
            return canonical_orig
        # Allow cleanly re-hooking an orphaned E9 trampoline left by an unexpected exit
        if len(cur) == len(canonical_orig) and cur[:1] == b"\xE9":
            return canonical_orig
        raise RuntimeError(f"Unexpected bytes at {label} (0x{patch_va:X}): {cur.hex()}")

    def build_apply_damage_stub(self) -> Tuple[int, bytes, int, bytes, bytes]:
        assert self.syms and self.cave_base
        patch_va = self.syms.apply_dmg_va
        cave_va = self.cave_base + CAVE_APPLY_DMG_OFF
        orig = self._read_canonical_or_verify(patch_va, b"\x44\x8B\x76\x20\x8B\x46\x1C", "ApplyDamage")

        asm = AsmBuilder(cave_va)
        asm.emit(orig)                                   # mov r14d,[rsi+20]; mov eax,[rsi+1C]
        asm.emit(b"\x51\x52")                            # push rcx; push rdx
        self._emit_online_guard(asm, "done", "online_ok")
        self._emit_fmap_head(asm, "done")

        # P1 Infinite HP check
        asm.rip_mem_op(b"\x83\x3D", self.cave_base + CFG_P1_INF_HP, b"\x00")
        asm.jcc_near(0x74, "chk_p2")
        self._emit_read_node_fighter_into_rdx(asm, 0x00, 0, "chk_p2")
        asm.emit(b"\x48\x3B\x56\x08")                    # cmp rdx, [rsi+0x08]
        asm.jcc_near(0x75, "chk_p2")
        asm.emit(b"\x45\x33\xF6")                        # xor r14d, r14d
        asm.emit(b"\x45\x33\xFF")                        # xor r15d, r15d
        asm.jmp_near("done")

        # P2 One-Hit KO check
        asm.label("chk_p2")
        asm.rip_mem_op(b"\x83\x3D", self.cave_base + CFG_P2_OHKO, b"\x00")
        asm.jcc_near(0x74, "done")
        asm.emit(b"\x45\x85\xFF")                        # test r15d, r15d
        asm.jcc_near(0x7E, "done")                       # jle near done
        self._emit_read_node_fighter_into_rdx(asm, 0x10, 1, "done")
        asm.emit(b"\x48\x3B\x56\x08")                    # cmp rdx, [rsi+0x08]
        asm.jcc_near(0x75, "done")
        asm.emit(b"\x44\x8B\xF8")                        # mov r15d, eax

        asm.label("done")
        asm.emit(b"\x5A\x59")                            # pop rdx; pop rcx
        asm.jmp_abs_rel32(patch_va + 7)
        code = asm.finalize()
        jmp = b"\xE9" + struct.pack("<i", cave_va - (patch_va + 5)) + b"\x90\x90"
        return cave_va, code, patch_va, jmp, orig

    def build_break_helper_stub(self) -> Tuple[int, bytes, int, bytes, bytes]:
        assert self.syms and self.cave_base
        patch_va = self.syms.break_helper_va
        cave_va = self.cave_base + CAVE_BREAK_HELPER_OFF
        orig = self._read_canonical_or_verify(patch_va, b"\x80\x7B\x06\x00\x0F\xB7\xC7", "BreakHelper")

        asm = AsmBuilder(cave_va)
        asm.emit(b"\x50\x51\x52")                        # push rax; push rcx; push rdx
        self._emit_online_guard(asm, "done", "online_ok")
        self._emit_fmap_head(asm, "done")
        asm.emit(b"\x48\x8D\x83\x80\xFA\xFF\xFF")        # lea rax, [rbx-0x580]

        # P1 Max Break check
        asm.rip_mem_op(b"\x83\x3D", self.cave_base + CFG_P1_MAX_BRK, b"\x00")
        asm.jcc_near(0x74, "chk_p2")
        self._emit_read_node_fighter_into_rdx(asm, 0x00, 0, "chk_p2")
        asm.emit(b"\x48\x39\xD0")                        # cmp rax, rdx
        asm.jcc_near(0x75, "chk_p2")
        asm.emit(b"\x0F\xB7\x7B\x02")                    # movzx edi, word ptr [rbx+2]
        asm.jmp_near("done")

        # P2 Empty Break check
        asm.label("chk_p2")
        asm.rip_mem_op(b"\x83\x3D", self.cave_base + CFG_P2_EMPTY_BRK, b"\x00")
        asm.jcc_near(0x74, "done")
        self._emit_read_node_fighter_into_rdx(asm, 0x10, 1, "done")
        asm.emit(b"\x48\x39\xD0")                        # cmp rax, rdx
        asm.jcc_near(0x75, "done")
        asm.emit(b"\x31\xFF")                            # xor edi, edi

        asm.label("done")
        asm.emit(b"\x5A\x59\x58")                        # pop rdx; pop rcx; pop rax
        # Original 7 bytes run last so ZF is set cleanly for 'je' after patch point
        asm.emit(orig)
        asm.jmp_abs_rel32(patch_va + 7)
        code = asm.finalize()
        jmp = b"\xE9" + struct.pack("<i", cave_va - (patch_va + 5)) + b"\x90\x90"
        return cave_va, code, patch_va, jmp, orig

    def build_score_mul_stub(self) -> Tuple[int, bytes, int, bytes, bytes]:
        assert self.syms and self.cave_base
        patch_va = self.syms.score_mul_va
        cave_va = self.cave_base + CAVE_SCORE_MUL_OFF
        orig = self._read_canonical_or_verify(patch_va, b"\x48\x0F\xAF\x83\x60\x01\x00\x00", "ScoreMul")

        asm = AsmBuilder(cave_va)
        asm.rip_mem_op(b"\x48\x89\x1D", self.cave_base + CFG_SCORE_TASK_PTR)  # mov [slot], rbx
        asm.emit(orig)                                   # imul rax, [rbx+0x160]
        asm.emit(b"\x51")                                # push rcx
        asm.rip_mem_op(b"\x8B\x0D", self.cave_base + CFG_SCORE_MULT)          # mov ecx, [mult]
        asm.emit(b"\x83\xF9\x01")                        # cmp ecx, 1
        asm.jcc_short(0x7E, "chk_max")
        asm.emit(b"\x48\x63\xC9")                        # movsxd rcx, ecx
        asm.emit(b"\x48\x0F\xAF\xC1")                    # imul rax, rcx
        asm.label("chk_max")
        asm.rip_mem_op(b"\x83\x3D", self.cave_base + CFG_SCORE_MAX_MODE, b"\x00")
        asm.jcc_short(0x74, "done")
        asm.emit(b"\xB8\xFF\xE0\xF5\x05")                # mov eax, 99999999
        asm.label("done")
        asm.emit(b"\x59")                                # pop rcx
        asm.jmp_abs_rel32(patch_va + 8)
        code = asm.finalize()
        jmp = b"\xE9" + struct.pack("<i", cave_va - (patch_va + 5)) + b"\x90\x90\x90"
        return cave_va, code, patch_va, jmp, orig

    def build_timescale_stub(self) -> Tuple[int, bytes, int, bytes, bytes]:
        assert self.syms and self.cave_base
        patch_va = self.syms.timescale_va
        cave_va = self.cave_base + CAVE_TIMESCALE_OFF
        orig = self._read_canonical_or_verify(patch_va, b"\x8B\x41\x10\xF3\x0F\x10\x49\x14", "TimeScale")

        asm = AsmBuilder(cave_va)
        asm.emit(orig)
        asm.rip_mem_op(b"\x83\x3D", self.cave_base + CFG_SPEED_ENABLED, b"\x00")
        asm.jcc_short(0x74, "done")
        asm.rip_mem_op(b"\xF3\x0F\x59\x0D", self.cave_base + CFG_SPEED_SCALE)  # mulss xmm1, [scale]
        asm.label("done")
        asm.jmp_abs_rel32(patch_va + 8)
        code = asm.finalize()
        jmp = b"\xE9" + struct.pack("<i", cave_va - (patch_va + 5)) + b"\x90\x90\x90"
        return cave_va, code, patch_va, jmp, orig

    def _install_hook(self, name: str, builder_fn) -> None:
        if name in self.installed_hooks:
            return
        self.ensure_cave_page()
        cave_va, cave_code, patch_va, jmp_bytes, orig = builder_fn()
        if not self.write_bytes(cave_va, cave_code, protect_rwx=False):
            raise RuntimeError(f"Failed writing cave for hook {name}")
        if not self.write_bytes(patch_va, jmp_bytes, protect_rwx=True):
            raise RuntimeError(f"Failed patching jump for hook {name}")
        self.installed_hooks[name] = (patch_va, orig)

    def _uninstall_hook(self, name: str) -> None:
        item = self.installed_hooks.pop(name, None)
        if item:
            patch_va, orig = item
            self.write_bytes(patch_va, orig, protect_rwx=True)

    def uninstall_all_hooks(self) -> None:
        for name in list(self.installed_hooks.keys()):
            self._uninstall_hook(name)

    def set_damage_flags(self, p1_inf: bool, p2_ohko: bool) -> None:
        if p1_inf or p2_ohko:
            self.assert_offline()
            self._install_hook("apply_dmg", self.build_apply_damage_stub)
        if self.cave_base:
            self.write_u32(self.cave_base + CFG_P1_INF_HP, 1 if p1_inf else 0)
            self.write_u32(self.cave_base + CFG_P2_OHKO, 1 if p2_ohko else 0)
        if p1_inf:
            self.refill_p1_health()
        if not p1_inf and not p2_ohko:
            self._uninstall_hook("apply_dmg")

    def set_break_flags(self, p1_max: bool, p2_empty: bool) -> None:
        if p1_max or p2_empty:
            self.assert_offline()
            self._install_hook("break_helper", self.build_break_helper_stub)
        if self.cave_base:
            self.write_u32(self.cave_base + CFG_P1_MAX_BRK, 1 if p1_max else 0)
            self.write_u32(self.cave_base + CFG_P2_EMPTY_BRK, 1 if p2_empty else 0)
        if p1_max:
            self.refill_p1_break()
        if p2_empty:
            self.drain_p2_break()
        if not p1_max and not p2_empty:
            self._uninstall_hook("break_helper")

    def set_score_cheat(self, enabled: bool, multiplier: int = 10, max_mode: bool = True) -> None:
        if enabled:
            self.assert_offline()
            self._install_hook("score_mul", self.build_score_mul_stub)
        if self.cave_base:
            self.write_u32(self.cave_base + CFG_SCORE_MULT, max(1, int(multiplier)))
            self.write_u32(self.cave_base + CFG_SCORE_MAX_MODE, 1 if max_mode else 0)
        if not enabled:
            self._uninstall_hook("score_mul")

    def set_speed_cheat(self, enabled: bool, scale: float = 1.5) -> None:
        if enabled:
            self.assert_offline()
            self._install_hook("timescale", self.build_timescale_stub)
        if self.cave_base:
            self.write_u32(self.cave_base + CFG_SPEED_ENABLED, 1 if enabled else 0)
            self.write_f32(self.cave_base + CFG_SPEED_SCALE, float(scale))
        if not enabled:
            self._uninstall_hook("timescale")

    def set_freeze_timer(self, enabled: bool) -> None:
        if not self.syms:
            return
        if enabled:
            self.assert_offline()
            self._enable_patch(
                "freeze_timer",
                [
                    (self.syms.timer1_patch_va, b"\xF3\x0F\x11\x45\x08", b"\x90" * 5),
                    (self.syms.timer2_patch_va, b"\xF3\x0F\x11\x46\x08", b"\x90" * 5),
                ],
            )
        else:
            self._disable_patch("freeze_timer")

    def set_always_clear_challenges(self, enabled: bool) -> None:
        if not self.syms:
            return
        if enabled:
            self.assert_offline()
            self._enable_patch(
                "clear_challenges",
                [
                    (self.syms.chal1_patch_va, b"\x0F\x9D\xC0", b"\xB0\x01\x90"),
                    (self.syms.chal2_patch_va, b"\x0F\x9D\xC0", b"\xB0\x01\x90"),
                ],
            )
        else:
            self._disable_patch("clear_challenges")

    def set_quest_always_3_stars(self, enabled: bool) -> None:
        """Force Quest match end to award win status and all 3 star objectives."""
        if not self.syms:
            return
        if enabled:
            self.assert_offline()
            self._enable_patch(
                "quest_3_stars",
                [
                    (self.syms.quest_win_patch_va, b"\x38\x08\x0F\x94\x45\xD8", b"\xC6\x45\xD8\x01\x90\x90"),
                    (self.syms.quest_stars_patch_va, b"\x0F\xB6\x81\x24\x01\x00\x00", b"\x0F\xB6\x81\x28\x01\x00\x00"),
                ],
            )
        else:
            self._disable_patch("quest_3_stars")

    def _enable_patch(self, name: str, entries: List[Tuple[int, bytes, bytes]]) -> None:
        if name in self.installed_patches:
            return
        saved: List[Tuple[int, bytes]] = []
        for va, expected_orig, repl in entries:
            cur = self.read_bytes(va, len(expected_orig))
            if cur != expected_orig and cur != repl:
                raise RuntimeError(f"Unexpected bytes at patch '{name}' (0x{va:X}): {cur.hex()}")
            if not self.write_bytes(va, repl, protect_rwx=True):
                raise RuntimeError(f"Failed applying patch '{name}' at 0x{va:X}")
            saved.append((va, expected_orig))
        self.installed_patches[name] = saved

    def _disable_patch(self, name: str) -> None:
        saved = self.installed_patches.pop(name, None)
        if saved:
            for va, orig in saved:
                self.write_bytes(va, orig, protect_rwx=True)

    def disable_all_patches(self) -> None:
        for name in list(self.installed_patches.keys()):
            self._disable_patch(name)

    def is_offline(self) -> Tuple[bool, int]:
        if not self.syms:
            return True, 255
        obj = self.read_u64(self.syms.online_obj_ptr_va)
        if not obj:
            return True, 255
        flag = self.read_u8(obj + 0x8F8)
        return flag >= 5, flag

    def assert_offline(self) -> None:
        offline, flag = self.is_offline()
        if not offline:
            raise RuntimeError(f"Offline guard blocked cheat (online state={flag}).")

    def _read_fighters(self) -> Tuple[Optional[FighterSnapshot], Optional[FighterSnapshot]]:
        if not self.syms:
            return None, None
        fmap = self.read_u64(self.syms.fighter_map_ptr_va)
        if not fmap:
            return None, None
        head = self.read_u64(fmap)
        if not head:
            return None, None

        def read_side(node_off: int, expected_key: int) -> Optional[FighterSnapshot]:
            node = self.read_u64(head + node_off)
            if not node or self.read_u8(node + 0x19) != 0 or self.read_u8(node + 0x20) != expected_key:
                return None
            slot = self.read_u64(node + 0x28)
            if not slot:
                return None
            f = self.read_u64(slot + 0x88)
            if not f:
                return None
            fstatus = self.read_u64(f + 0xDF0)
            active = self.read_u8(fstatus + 0x3F0) if fstatus else 0
            return FighterSnapshot(
                fighter_ptr=f,
                damage_taken=self.read_u32(f + 0x1758),
                max_hp=self.read_u32(f + 0x1754),
                break_cur=self.read_u16(f + 0x580),
                break_max=self.read_u16(f + 0x582),
                damage_mode=self.read_u32(f + 0x1750),
                active=active,
                dmg_active=self.read_u8(f + 0x175C),
            )

        return read_side(0x00, 0), read_side(0x10, 1)

    def read_snapshot(self) -> GameSnapshot:
        if not self.is_attached or not self.syms:
            return GameSnapshot(attached=False)
        offline, flag = self.is_offline()
        owner = self.read_u64(self.syms.owner_ptr_va)
        reward = self.read_u64(self.syms.reward_ptr_va)
        sd = self.read_u64(self.syms.save_data_ptr_va)
        sg = self.read_u64(self.syms.score_global_ptr_va)
        p1, p2 = self._read_fighters()

        live_score = 0
        if self.cave_base:
            st = self.read_u64(self.cave_base + CFG_SCORE_TASK_PTR)
            if st:
                live_score = self.read_u64(st + 0x168)

        cp_sample: Tuple[int, ...] = ()
        if sd:
            raw_cp = self.read_bytes(sd + 0x5EDC, 16)
            if len(raw_cp) == 16:
                cp_sample = struct.unpack("<4I", raw_cp)

        return GameSnapshot(
            attached=True,
            pid=self.pid,
            offline=offline,
            online_flag=flag,
            in_match=bool((p1 and (p1.active or p1.dmg_active)) or (p2 and (p2.active or p2.dmg_active))),
            money=self.read_u32(owner + 0x00) if owner else 0,
            owner_exp=self.read_u32(owner + 0x08) if owner else 0,
            reward_money=self.read_u32(reward + 0x10) if reward else 0,
            reward_exp=self.read_u32(reward + 0x18) if reward else 0,
            frame_speed=self.read_f32(sg + 0x560) if sg else 1.0,
            live_score=live_score,
            p1=p1,
            p2=p2,
            chara_points_sample=cp_sample,
        )

    # Direct one-shot / profile write helpers
    def set_money(self, amount: int) -> None:
        self.assert_offline()
        if not self.syms:
            return
        owner = self.read_u64(self.syms.owner_ptr_va)
        if owner:
            self.write_u32(owner + 0x00, max(0, min(999999999, int(amount))))

    def set_owner_exp(self, amount: int) -> None:
        self.assert_offline()
        if not self.syms:
            return
        owner = self.read_u64(self.syms.owner_ptr_va)
        if owner:
            self.write_u32(owner + 0x08, max(0, min(999999999, int(amount))))

    def set_all_character_points(self, amount: int, count: int = 35) -> None:
        self.assert_offline()
        if not self.syms:
            return
        sd = self.read_u64(self.syms.save_data_ptr_va)
        if sd:
            val = max(0, min(9999999, int(amount)))
            for idx in range(count):
                self.write_u32(sd + 0x5EDC + idx * 4, val)

    def refill_p1_break(self) -> None:
        self.assert_offline()
        p1, _ = self._read_fighters()
        if p1 and p1.break_max > 0:
            self.write_u16(p1.fighter_ptr + 0x580, p1.break_max)

    def refill_p1_health(self) -> None:
        self.assert_offline()
        p1, _ = self._read_fighters()
        if p1:
            self.write_u32(p1.fighter_ptr + 0x1758, 0)
            self.write_u32(p1.fighter_ptr + 0x5B4, 0)
            self.write_u32(p1.fighter_ptr + 0x5B8, 0)

    def drain_p2_break(self) -> None:
        self.assert_offline()
        _, p2 = self._read_fighters()
        if p2:
            self.write_u16(p2.fighter_ptr + 0x580, 0)

    def set_live_score(self, value: int) -> None:
        self.assert_offline()
        if self.cave_base:
            st = self.read_u64(self.cave_base + CFG_SCORE_TASK_PTR)
            if st:
                self.write_u64(st + 0x168, max(0, int(value)))

    def hotkey_pressed(self, vk: int) -> bool:
        return bool(self.w32.u32.GetAsyncKeyState(vk) & 0x8000)
