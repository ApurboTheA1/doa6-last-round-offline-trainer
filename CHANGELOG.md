# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-11-11

### Performance & Memory Engine ([`memory_engine.py`](memory_engine.py))
- **Native Win32 process lookup:** Replaced per-poll `tasklist.exe` subprocess spawning with `CreateToolhelp32Snapshot` / `Process32FirstW` / `Process32NextW` (`Win32Memory.find_pid_by_name`).
- **Anchored `.text` AOB scanner:** Read `.text` chunks directly into a single `bytearray` buffer and implemented `find_aob_unique` using C-level literal anchor scanning (`bytearray.find`) instead of backtracking wildcard-leading regexes.
- **Batched telemetry & writes:**
  - Added reusable `64`-byte scratch buffer and `read_struct` for contiguous game structs (`_PAIR_U64_SKIP8`, `_NODE_HEADER`, `_FIGHTER_BREAK`, `_FIGHTER_HEALTH`, `_OWNER_ECO`, `_REWARD_ECO`).
  - Removed unused `SaveData` character-point sampling from `read_snapshot()`.
  - Batched `set_all_character_points` (slots `0..34`) into a single contiguous `WriteProcessMemory` call and merged `+0x5B4`/`+0x5B8` clear writes in `refill_p1_health` into one `write_u64`.
- **Code cleanup:** Consolidated static inline patches via `_STATIC_PATCH_SPECS` / `_set_static_patch` and factored shared x64 hook assembly (`_emit_fighter_gate`, `_finalize_trampoline`) while preserving exact hook machine code.

### GUI Trainer ([`doa6lr_trainer.py`](doa6lr_trainer.py))
- **Adaptive poll interval:** Polls at `400 ms` while waiting for `DOA6LR.exe` and `120 ms` once attached.
- **Zero redundant snapshot / UI redraws:** Passes cached `fighter_ptr` into refill/drain helpers, updates `FighterSnapshot` values in place instead of triggering a second full memory snapshot, and caches pill/telemetry text & colors (`_set_if_changed`, `_style_pill`).
- **Input & lifecycle hardening:** Consolidated numeric profile setters into `_apply_numeric_entry` with graceful `ValueError` status reporting, cleared stale `_last_hotkey_state` when hotkeys are disabled/detached, and guarded exit cleanup against duplicate calls (`_cleaned`).

### Cheat Engine Table ([`DOA6LR_Trainer.ct`](DOA6LR_Trainer.ct))
- **Cached fighter symbols:** Extracted `read_fighter_node` out of the `250 ms` timer and added `sync_fighter_symbol` with `lastP1` / `lastP2` caching so `DOA6LR_P1Fighter` / `DOA6LR_P2Fighter` are only re-registered when pointers change.
- **Leaner timer loop:** Reused cached fighter pointers directly inside `OnTimer` via `write_p1_health`, `write_p1_break`, and `write_p2_break` instead of re-initializing on every tick.

---

## [1.0.0] - 2026-11-11

### Initial Release
- Added standalone Python 3 Tkinter GUI trainer (`doa6lr_trainer.py` + `memory_engine.py`) and Cheat Engine 7.x table (`DOA6LR_Trainer.ct`, CT v45).
- Implemented offline combat, challenge, Quest 3 Stars, Arcade/Survival score, custom game speed (`TimeScale`), and Money / Owner EXP / Character Points (`0..34`) cheats with automatic Online Safety Guard (`OnlineLobby + 0x8F8`) and byte restoration.
