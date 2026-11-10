# Dead or Alive 6: Last Round — Offline Trainer & Cheat Engine Table

An open-source, **offline / single-player only** game trainer and Cheat Engine table for **Dead or Alive 6: Last Round** (`DOA6LR.exe`, Steam PC).

Includes both:
1. **Standalone Python GUI Trainer** ([`doa6lr_trainer.py`](doa6lr_trainer.py) + [`memory_engine.py`](memory_engine.py)) — zero third-party dependencies (uses Python's built-in `tkinter` and Win32 `ctypes`).
2. **Cheat Engine 7.x Table** ([`DOA6LR_Trainer.ct`](DOA6LR_Trainer.ct)) — AOB scripts, x64 code caves, live pointer telemetry, and embedded Lua safety checks.

> **Offline / Single-Player Only**
> Both the Python trainer and the Cheat Engine table enforce a runtime **Online Safety Guard** (`OnlineLobby + 0x8F8`). If an online match/lobby state is detected (`flag < 5`), enabling cheats is blocked and any active hooks/patches are automatically disabled with original game bytes restored. Never attempt to use memory modification tools in online multiplayer modes.

---

## Features

### Combat & Match
- **Infinite Health (P1)** — Blocks incoming damage for Player 1 inside the `ApplyDamage` x64 hook while leaving P2/AI damage unaffected, and keeps P1 damage taken at `0`.
- **One-Hit K.O. (P2 / AI)** — Scales positive hit damage (`r15d`) against Player 2 / AI to their `MaxHP` inside `ApplyDamage`.
- **Max / Infinite Break Gauge (P1)** — Locks P1 Break Gauge to max via `BreakHelper` and instant refill polling.
- **Empty Opponent Break Gauge (P2 / AI)** — Drains P2/AI Break Gauge to `0` via `BreakHelper`.
- **Quick One-Shot Fighter Actions** — `Heal P1 Full HP`, `Refill P1 Break`, and `Drain P2 Break` (in GUI & CT).
- **Freeze Match Timer** — Prevents the round timer from counting down.

### Modes, Quest, Challenges & Score
- **Always Clear Challenges** — Forces match challenge completion checks (`Challenge1` / `Challenge2`) to evaluate as cleared.
- **Quest Mode: Always 3 Stars** — Forces Quest match end to count as a win and awards all 3 stars regardless of objectives completed.
- **Arcade / Survival Score Cheat** — Hook on score gain (`ScoreMul`) with two modes:
  - **Force Max Gain** (`99,999,999` per hit), or
  - **Configurable Multiplier** (`2x`–`1000x` in GUI; `4 Bytes` value in CT), plus live course score viewing/editing.

### Game Speed
- **Custom Game Speed Hook (`TimeScale`)** — Smooth slider (`0.25x`–`3.0x`) and quick presets (`0.4x Slow Motion`, `1.0x Normal`, `2.0x Fast`).
- **CE Native Speedhack Alternatives** — Included in [`DOA6LR_Trainer.ct`](DOA6LR_Trainer.ct) (`2.0x` and `0.4x`).

### Player Profile, Money, EXP & Character Points
- **Player Points / In-Game Money** (`OwnerStruct + 0x00`)
- **Owner EXP / Grade Points** (`OwnerStruct + 0x08`)
- **All Character Points (Slots `0..34`)** (`SaveData + 0x5EDC`)
- **One-Shot Preset**: Max Money + Owner EXP + Character Points (slots `0..34`).
- **Live Telemetry** — Displays P1/P2 HP, damage taken, Break Gauge, damage mode, online state flag, Money, Owner EXP, pending match reward Money/EXP (in CT), live score, and frame speed.

---

## Numpad Hotkeys (GUI Trainer)

Global hotkeys can be toggled with the **Global Numpad Hotkeys** checkbox at the bottom of the GUI.

| Hotkey | Action |
| :--- | :--- |
| `Num 1` | Toggle Infinite Health (P1) |
| `Num 2` | Toggle Max / Infinite Break Gauge (P1) |
| `Num 3` | Instant Refill Break Gauge (P1) |
| `Num 4` | Toggle One-Hit K.O. (P2 / AI) |
| `Num 5` | Toggle Empty Opponent Break Gauge (P2 / AI) |
| `Num 6` | Toggle Freeze Match Timer |
| `Num 7` | Toggle Always Clear Challenges |
| `Num 8` | Toggle Arcade / Survival Score Cheat |
| `Num 9` | Speed Preset: Slow `0.4x` |
| `Num 0` | Speed Preset: Fast `2.0x` |

> **Note:** `Quest Mode: Always 3 Stars` is toggled from the GUI checkbox (no Numpad hotkey assigned) or enabled in the Cheat Engine table.

---

## Requirements

- **OS:** Windows 10 / Windows 11 (64-bit)
- **Game:** *Dead or Alive 6: Last Round* (`DOA6LR.exe`, Steam PC, offline/single-player)
- **Option A (GUI Trainer):** Python 3.8+ (64-bit recommended) with standard `tkinter` support (included by default in the official python.org Windows installer). **No `pip install` packages required.**
- **Option B (Cheat Table):** [Cheat Engine 7.x](https://www.cheatengine.org/) (table format version `45`).

---

## Usage

### Option A: Standalone Python GUI Trainer (Recommended)
1. Launch **Dead or Alive 6: Last Round** and load into offline menus or an offline match (e.g., Versus CPU, Arcade, Survival, Quest).
2. Double-click [`launch_trainer.bat`](launch_trainer.bat), or run from a terminal:
   ```bat
   python doa6lr_trainer.py
   ```
3. Wait for the top status pill to show **ATTACHED (PID ...)** and **OFFLINE SAFE**.
4. Toggle desired cheats or use `Num 0`–`Num 9`.
5. Click **Disable All Active Cheats & Restore Bytes** (or close the trainer) to restore all patched instructions and free code caves cleanly.

### Option B: Cheat Engine Table (`DOA6LR_Trainer.ct`)
1. Launch `DOA6LR.exe`.
2. Open [`DOA6LR_Trainer.ct`](DOA6LR_Trainer.ct) in Cheat Engine 7.x (when prompted to execute the table's Lua script, allow it so auto-attach, AOB symbol lookup, and the Offline Safety Guard can initialize).
3. If auto-attach hasn't run yet, enable **`[DOA6LR Offline Trainer] Initialize / Rescan Symbols`** first.
4. Enable entries under **Combat**, **Modes, Challenges & Score**, or **Player Profile, Money, EXP & Character Points**.

---

## How It Works

- **Dynamic AOB Scanning:** Resolves pointers (`OwnerStruct`, `RewardStruct`, `SaveData`, `FighterMap`, `ScoreGlobal`, `OnlineLobby`) and hook/patch sites directly from `DOA6LR.exe`'s decrypted `.text` section in runtime memory after game launch — no hardcoded static offsets and no modifications to game executables on disk.
- **Near Code Caves:** Allocates a `4 KB` executable page within ±2 GB of `DOA6LR.exe` so `E9` rel32 jumps work reliably without clobbering extra registers.
- **Clean Restoration:** Tracks original bytes for every hook and inline patch and restores them automatically when disabled, when online state is detected, or on trainer exit.

---

## Project Files

| File | Purpose |
| :--- | :--- |
| [`doa6lr_trainer.py`](doa6lr_trainer.py) | Dark-themed Tkinter GUI, hotkey polling, telemetry display, and safety state sync |
| [`memory_engine.py`](memory_engine.py) | Win32 `ctypes` process wrapper, AOB scanner, x64 `AsmBuilder`, hooks, and profile read/write helpers |
| [`DOA6LR_Trainer.ct`](DOA6LR_Trainer.ct) | Cheat Engine 7.x table (`CT v45`) with Lua auto-attach, offline guard, and Auto Assembler scripts |
| [`launch_trainer.bat`](launch_trainer.bat) | Windows double-click launcher using `pythonw` (or fallback `python`) |
| [`CHANGELOG.md`](CHANGELOG.md) | Release notes and optimization history |
| [`LICENSE`](LICENSE) | MIT License |

---

## Recent Changes

- **v1.1.0:** Replaced `tasklist.exe` polling with native Win32 Toolhelp32 PID lookup, sped up `.text` AOB scanning via literal-anchor search, batched telemetry reads and profile writes, added adaptive GUI polling + dirty-checked redraws + graceful numeric error handling, and cached fighter symbols in [`DOA6LR_Trainer.ct`](DOA6LR_Trainer.ct). See [`CHANGELOG.md`](CHANGELOG.md) for full details.

---

## Troubleshooting

- **"WAITING FOR DOA6LR.EXE..." / Fails to attach (`OpenProcess` error):** Ensure the game is running. If you launch Steam or `DOA6LR.exe` as Administrator, run the trainer or Cheat Engine as Administrator as well.
- **"ONLINE DETECTED — CHEATS LOCKED":** You entered an online lobby/ranked/versus mode (`OnlineLobby + 0x8F8 < 5`). Return to offline single-player modes to use the trainer.
- **Python GUI doesn't open on `launch_trainer.bat`:** Open Command Prompt in this folder and run `python doa6lr_trainer.py` to see if Python is installed and added to `PATH`, or if `tkinter` is missing.
- **AOB signature not found after a game patch:** If a future update to `DOA6LR.exe` changes machine code at a hook site, that specific AOB will need updating.

---

## AI-Assisted Creation Disclosure

This project was created with **AI assistance** (including AOB signature analysis, x64 code-cave hooks, the pure-Python Win32 memory engine, the Tkinter GUI, and the Cheat Engine XML/Lua table) and tested live against the Steam offline build of `DOA6LR.exe`. All files are plain-text and open-source with no compiled binaries or obfuscated code so anyone can audit every address and byte modified.

---

## Disclaimer

- Provided strictly for **offline, single-player, personal, and educational use**.
- **Does not** unlock paid DLC content or circumvent Steam DRM / license checks, and **contains no proprietary game files or binaries**.
- Always **back up your game save files** before modifying currency, EXP, or character points.
- Not affiliated with or endorsed by Koei Tecmo Games Co., Ltd. or Team NINJA. Use at your own risk.
