"""
Standalone GUI Game Trainer for Dead or Alive 6 Last Round (DOA6LR.exe).
Offline / single-player only — automatically enforces online safety guard
and cleanly restores all original game bytes on disable or exit.
"""

from __future__ import annotations

import atexit
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Tuple

from memory_engine import DOA6LRMemoryEngine, GameSnapshot


# Win32 Virtual-Key codes for Numpad 0..9
VK_NUMPAD0 = 0x60
VK_NUMPAD1 = 0x61
VK_NUMPAD2 = 0x62
VK_NUMPAD3 = 0x63
VK_NUMPAD4 = 0x64
VK_NUMPAD5 = 0x65
VK_NUMPAD6 = 0x66
VK_NUMPAD7 = 0x67
VK_NUMPAD8 = 0x68
VK_NUMPAD9 = 0x69

POLL_ATTACHED_MS = 120
POLL_WAITING_MS = 400


class DOA6LRTrainerApp:
    """Tkinter trainer GUI driving DOA6LRMemoryEngine."""

    BG = "#12151C"
    CARD_BG = "#1B202B"
    CARD_BORDER = "#2B3242"
    FG = "#E8ECF4"
    MUTED = "#93A0B8"
    ACCENT = "#4F8CFF"
    GREEN = "#35C47C"
    RED = "#F25F5C"
    RED_BG = "#382529"
    GREEN_BG = "#1D3329"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Dead or Alive 6 Last Round — Offline Trainer (DOA6LR.exe)")
        self.root.geometry("920x700")
        self.root.minsize(860, 640)
        self.root.configure(bg=self.BG)

        self.engine = DOA6LRMemoryEngine()
        self._cleaned = False
        atexit.register(self._cleanup_on_exit)

        self._hotkeys_enabled = tk.BooleanVar(value=True)
        self._last_hotkey_state: Dict[int, bool] = {}
        self._ui_cache: Dict[str, object] = {}

        # Toggle states
        self.var_p1_inf_hp = tk.BooleanVar(value=False)
        self.var_p1_max_brk = tk.BooleanVar(value=False)
        self.var_p2_ohko = tk.BooleanVar(value=False)
        self.var_p2_empty_brk = tk.BooleanVar(value=False)
        self.var_freeze_timer = tk.BooleanVar(value=False)
        self.var_clear_chal = tk.BooleanVar(value=False)
        self.var_quest_3_stars = tk.BooleanVar(value=False)
        self.var_score_cheat = tk.BooleanVar(value=False)
        self.var_score_max_mode = tk.BooleanVar(value=True)
        self.var_score_mult = tk.IntVar(value=10)
        self.var_speed_cheat = tk.BooleanVar(value=False)
        self.var_speed_scale = tk.DoubleVar(value=1.5)

        # Profile input fields
        self.entry_money = tk.StringVar(value="999999999")
        self.entry_exp = tk.StringVar(value="99999999")
        self.entry_cp = tk.StringVar(value="999999")
        self.entry_score = tk.StringVar(value="99999999")

        # Live telemetry variables
        self.lbl_attach_var = tk.StringVar(value="WAITING FOR DOA6LR.EXE...")
        self.lbl_guard_var = tk.StringVar(value="OFFLINE GUARD READY")
        self.lbl_match_var = tk.StringVar(value="MENU")
        self.lbl_p1_stats = tk.StringVar(value="HP: -- / --   |   Break: -- / --   |   Ctrl: --")
        self.lbl_p2_stats = tk.StringVar(value="HP: -- / --   |   Break: -- / --   |   Ctrl: --")
        self.lbl_eco_stats = tk.StringVar(
            value="Money: --   |   Owner EXP: --   |   Live Course Score: --"
        )
        self.lbl_status_msg = tk.StringVar(
            value="Offline single-player trainer ready. Waiting to attach..."
        )

        self._build_styles()
        self._build_ui()

        self._hotkey_actions: Dict[int, Callable[[], None]] = {
            VK_NUMPAD1: lambda: self._flip_bool(self.var_p1_inf_hp, self._apply_dmg),
            VK_NUMPAD2: lambda: self._flip_bool(self.var_p1_max_brk, self._apply_brk),
            VK_NUMPAD3: lambda: self._safe_run(self.engine.refill_p1_break, "Refilled P1 Break Gauge to max."),
            VK_NUMPAD4: lambda: self._flip_bool(self.var_p2_ohko, self._apply_dmg),
            VK_NUMPAD5: lambda: self._flip_bool(self.var_p2_empty_brk, self._apply_brk),
            VK_NUMPAD6: lambda: self._flip_bool(self.var_freeze_timer, self._apply_timer),
            VK_NUMPAD7: lambda: self._flip_bool(self.var_clear_chal, self._apply_challenges),
            VK_NUMPAD8: lambda: self._flip_bool(self.var_score_cheat, self._apply_score),
            VK_NUMPAD9: lambda: self._preset_speed(0.4),
            VK_NUMPAD0: lambda: self._preset_speed(2.0),
        }

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._poll_loop)

    def _build_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD_BG)
        style.configure("Header.TLabel", background=self.BG, foreground=self.FG, font=("Segoe UI", 14, "bold"))
        style.configure("Section.TLabel", background=self.CARD_BG, foreground=self.ACCENT, font=("Segoe UI", 10, "bold"))
        style.configure("Body.TLabel", background=self.CARD_BG, foreground=self.FG, font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background=self.CARD_BG, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Toggle.TCheckbutton", background=self.CARD_BG, foreground=self.FG, font=("Segoe UI", 9))
        style.map("Toggle.TCheckbutton", background=[("active", self.CARD_BG)], foreground=[("active", self.ACCENT)])

    def _card(self, parent: tk.Misc, title: str) -> tk.Frame:
        outer = tk.Frame(
            parent,
            bg=self.CARD_BG,
            highlightbackground=self.CARD_BORDER,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        ttk.Label(outer, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        return outer

    def _pill(self, parent: tk.Misc, var: tk.StringVar, bg: str, fg: str, padx_right: int = 4) -> tk.Label:
        lbl = tk.Label(
            parent,
            textvariable=var,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4,
        )
        lbl.pack(side="left", padx=(4, padx_right))
        return lbl

    def _build_ui(self) -> None:
        # Top header bar
        hdr = tk.Frame(self.root, bg=self.BG, padx=16, pady=12)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="DEAD OR ALIVE 6 Last Round — Offline Trainer", style="Header.TLabel").pack(side="left")

        pills = tk.Frame(hdr, bg=self.BG)
        pills.pack(side="right")
        self.pill_match = self._pill(pills, self.lbl_match_var, "#262C3A", self.MUTED)
        self.pill_guard = self._pill(pills, self.lbl_guard_var, self.GREEN_BG, self.GREEN)
        self.pill_attach = self._pill(pills, self.lbl_attach_var, self.RED_BG, self.RED, padx_right=0)

        # Telemetry bar
        telem = self._card(self.root, "LIVE TELEMETRY")
        telem.pack(fill="x", padx=16, pady=(0, 10))
        tgrid = tk.Frame(telem, bg=self.CARD_BG)
        tgrid.pack(fill="x")
        for row, (label, var, pady) in enumerate((
            ("Player 1:", self.lbl_p1_stats, 0),
            ("Player 2:", self.lbl_p2_stats, 2),
            ("Profile:", self.lbl_eco_stats, 0),
        )):
            ttk.Label(tgrid, text=label, style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=pady)
            ttk.Label(tgrid, textvariable=var, style="Body.TLabel").grid(row=row, column=1, sticky="w", padx=8, pady=pady)

        # Two main columns
        cols = tk.Frame(self.root, bg=self.BG)
        cols.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        cols.columnconfigure(0, weight=1, uniform="col")
        cols.columnconfigure(1, weight=1, uniform="col")

        # Left column: Combat + Modes & Speed
        left_col = tk.Frame(cols, bg=self.BG)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        combat = self._card(left_col, "COMBAT & MATCH CHEATS")
        combat.pack(fill="x", pady=(0, 10))
        self._add_toggle(combat, "[Num 1]  Infinite Health (P1)", self.var_p1_inf_hp, self._apply_dmg)
        self._add_toggle(combat, "[Num 2]  Max / Infinite Break Gauge (P1)", self.var_p1_max_brk, self._apply_brk)
        self._add_action_btn(
            combat,
            "[Num 3]  Instant Refill Break Gauge (P1)",
            lambda: self._safe_run(self.engine.refill_p1_break, "Refilled P1 Break Gauge to max."),
        )
        self._add_toggle(combat, "[Num 4]  One-Hit K.O. (P2 / AI)", self.var_p2_ohko, self._apply_dmg)
        self._add_toggle(combat, "[Num 5]  Empty Opponent Break Gauge (P2 / AI)", self.var_p2_empty_brk, self._apply_brk)
        self._add_toggle(combat, "[Num 6]  Freeze Match Timer", self.var_freeze_timer, self._apply_timer)
        self._add_toggle(combat, "[Num 7]  Always Clear Challenges", self.var_clear_chal, self._apply_challenges)
        self._add_toggle(combat, "Quest Mode: Always 3 Stars", self.var_quest_3_stars, self._apply_quest_3_stars)

        modes = self._card(left_col, "SCORE & GAME SPEED")
        modes.pack(fill="both", expand=True)
        self._add_toggle(modes, "[Num 8]  Enable Arcade / Survival Score Cheat", self.var_score_cheat, self._apply_score)

        sc_opts = tk.Frame(modes, bg=self.CARD_BG, padx=18)
        sc_opts.pack(fill="x", pady=(2, 8))
        ttk.Checkbutton(
            sc_opts,
            text="Force Max Gain (99,999,999 per hit)",
            variable=self.var_score_max_mode,
            command=self._apply_score,
            style="Toggle.TCheckbutton",
        ).pack(anchor="w")
        mult_row = tk.Frame(sc_opts, bg=self.CARD_BG)
        mult_row.pack(fill="x", pady=(4, 0))
        ttk.Label(mult_row, text="Multiplier (when Force Off):", style="Muted.TLabel").pack(side="left")
        ttk.Spinbox(
            mult_row, from_=2, to=1000, textvariable=self.var_score_mult, width=6, command=self._apply_score
        ).pack(side="left", padx=8)

        self._add_toggle(modes, "Enable Custom Game Speed Hook", self.var_speed_cheat, self._apply_speed)
        spd_row = tk.Frame(modes, bg=self.CARD_BG, padx=18)
        spd_row.pack(fill="x", pady=2)
        tk.Scale(
            spd_row,
            from_=0.25,
            to=3.0,
            resolution=0.05,
            orient="horizontal",
            variable=self.var_speed_scale,
            bg=self.CARD_BG,
            fg=self.FG,
            highlightthickness=0,
            troughcolor="#262C3A",
            activebackground=self.ACCENT,
            command=lambda _v: self._apply_speed() if self.var_speed_cheat.get() else None,
        ).pack(fill="x")

        spd_btns = tk.Frame(modes, bg=self.CARD_BG, padx=18)
        spd_btns.pack(fill="x", pady=(4, 0))
        self._mini_btn(spd_btns, "[Num 9] Slow 0.4x", lambda: self._preset_speed(0.4)).pack(side="left", padx=(0, 6))
        self._mini_btn(spd_btns, "Normal 1.0x", lambda: self._preset_speed(1.0, disable=True)).pack(side="left", padx=6)
        self._mini_btn(spd_btns, "[Num 0] Fast 2.0x", lambda: self._preset_speed(2.0)).pack(side="left", padx=6)

        # Right column: Money, EXP, CP & Quick Fighter Actions
        right_col = tk.Frame(cols, bg=self.BG)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        profile = self._card(right_col, "PLAYER MONEY, OWNER EXP & CHARACTER POINTS")
        profile.pack(fill="x", pady=(0, 10))
        self._add_editor_row(
            profile,
            "Player Points / Money:",
            self.entry_money,
            "Set",
            lambda: self._apply_numeric_entry(self.entry_money, self.engine.set_money, "Money set to {:,}"),
        )
        self._add_editor_row(
            profile,
            "Owner EXP / Grade:",
            self.entry_exp,
            "Set",
            lambda: self._apply_numeric_entry(self.entry_exp, self.engine.set_owner_exp, "Owner EXP set to {:,}"),
        )
        self._add_editor_row(
            profile,
            "All Chars Points (0..34):",
            self.entry_cp,
            "Set All",
            lambda: self._apply_numeric_entry(
                self.entry_cp, self.engine.set_all_character_points, "Set All Character Points (0..34) to {:,}"
            ),
        )
        self._add_editor_row(
            profile,
            "Live Course Score:",
            self.entry_score,
            "Write",
            lambda: self._apply_numeric_entry(self.entry_score, self.engine.set_live_score, "Live Course Score set to {:,}"),
        )

        presets = tk.Frame(profile, bg=self.CARD_BG)
        presets.pack(fill="x", pady=(8, 0))
        self._mini_btn(presets, "Max Money + EXP + Char Pts", self._preset_max_economy).pack(side="left")

        ctrl = self._card(right_col, "QUICK MATCH ACTIONS")
        ctrl.pack(fill="both", expand=True)
        qrow1 = tk.Frame(ctrl, bg=self.CARD_BG)
        qrow1.pack(fill="x", pady=4)
        self._mini_btn(
            qrow1,
            "Heal P1 Full HP",
            lambda: self._safe_run(self.engine.refill_p1_health, "Restored P1 damage taken to 0 (Full HP)."),
        ).pack(side="left", padx=(0, 6))
        self._mini_btn(
            qrow1,
            "Refill P1 Break",
            lambda: self._safe_run(self.engine.refill_p1_break, "Refilled P1 Break Gauge to max."),
        ).pack(side="left", padx=6)
        self._mini_btn(
            qrow1,
            "Drain P2 Break",
            lambda: self._safe_run(self.engine.drain_p2_break, "Emptied P2 Break Gauge."),
        ).pack(side="left", padx=6)

        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=10)
        self._add_action_btn(
            ctrl,
            "Disable All Active Cheats & Restore Bytes",
            self.disable_all_cheats,
            bg=self.RED_BG,
            fg=self.RED,
        )
        self._add_action_btn(ctrl, "Force Rescan DOA6LR.exe Symbols", self._force_rescan)

        # Bottom status & hotkey bar
        footer = tk.Frame(self.root, bg="#0D1016", padx=16, pady=8)
        footer.pack(fill="x", side="bottom")
        tk.Checkbutton(
            footer,
            text="Global Numpad Hotkeys",
            variable=self._hotkeys_enabled,
            bg="#0D1016",
            fg=self.MUTED,
            selectcolor=self.CARD_BG,
            activebackground="#0D1016",
            activeforeground=self.FG,
            font=("Segoe UI", 8),
        ).pack(side="left")
        tk.Label(
            footer,
            textvariable=self.lbl_status_msg,
            bg="#0D1016",
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(side="right")

    def _add_toggle(self, parent: tk.Misc, text: str, var: tk.BooleanVar, cmd: Callable[[], None]) -> None:
        ttk.Checkbutton(parent, text=text, variable=var, command=cmd, style="Toggle.TCheckbutton").pack(
            anchor="w", pady=3
        )

    def _add_action_btn(
        self,
        parent: tk.Misc,
        text: str,
        cmd: Callable[[], None],
        bg: str = "#263044",
        fg: str = "#E8ECF4",
    ) -> None:
        tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=bg,
            fg=fg,
            activebackground=self.ACCENT,
            activeforeground="#FFFFFF",
            relief="flat",
            font=("Segoe UI", 9),
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(fill="x", pady=3)

    def _mini_btn(self, parent: tk.Misc, text: str, cmd: Callable[[], None]) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg="#263044",
            fg=self.FG,
            activebackground=self.ACCENT,
            activeforeground="#FFFFFF",
            relief="flat",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4,
            cursor="hand2",
        )

    def _add_editor_row(
        self, parent: tk.Misc, label: str, var: tk.StringVar, btn_text: str, cmd: Callable[[], None]
    ) -> None:
        row = tk.Frame(parent, bg=self.CARD_BG)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, style="Muted.TLabel", width=21).pack(side="left")
        tk.Entry(
            row,
            textvariable=var,
            bg="#12151C",
            fg=self.FG,
            insertbackground=self.FG,
            relief="flat",
            highlightbackground=self.CARD_BORDER,
            highlightthickness=1,
            width=14,
            font=("Consolas", 9),
        ).pack(side="left", padx=6)
        self._mini_btn(row, btn_text, cmd).pack(side="left")

    def _flip_bool(self, var: tk.BooleanVar, cb: Callable[[], None]) -> None:
        var.set(not var.get())
        cb()

    def _safe_run(self, fn: Callable[[], None], ok_msg: str) -> None:
        if not self.engine.is_attached:
            self.lbl_status_msg.set("DOA6LR.exe not attached yet.")
            return
        try:
            fn()
            self.lbl_status_msg.set(ok_msg)
        except Exception as exc:
            self.lbl_status_msg.set(f"Blocked/Error: {exc}")
            self._sync_toggles_to_engine_state()

    def _apply_numeric_entry(self, var: tk.StringVar, setter: Callable[[int], None], ok_fmt: str) -> None:
        raw = var.get().replace(",", "").strip()
        try:
            val = int(raw)
        except ValueError:
            self.lbl_status_msg.set(f"Invalid number: {raw!r}")
            return
        self._safe_run(lambda: setter(val), ok_fmt.format(val))

    def _sync_toggles_to_engine_state(self) -> None:
        hooks = self.engine.installed_hooks
        patches = self.engine.installed_patches
        if "apply_dmg" not in hooks:
            self.var_p1_inf_hp.set(False)
            self.var_p2_ohko.set(False)
        if "break_helper" not in hooks:
            self.var_p1_max_brk.set(False)
            self.var_p2_empty_brk.set(False)
        if "score_mul" not in hooks:
            self.var_score_cheat.set(False)
        if "timescale" not in hooks:
            self.var_speed_cheat.set(False)
        self.var_freeze_timer.set("freeze_timer" in patches)
        self.var_clear_chal.set("clear_challenges" in patches)
        self.var_quest_3_stars.set("quest_3_stars" in patches)

    def _apply_dmg(self) -> None:
        p1, p2 = self.var_p1_inf_hp.get(), self.var_p2_ohko.get()
        self._safe_run(
            lambda: self.engine.set_damage_flags(p1, p2),
            f"Health hook updated (P1 Inf={p1}, P2 1-Hit KO={p2})",
        )

    def _apply_brk(self) -> None:
        p1, p2 = self.var_p1_max_brk.get(), self.var_p2_empty_brk.get()
        self._safe_run(
            lambda: self.engine.set_break_flags(p1, p2),
            f"Break hook updated (P1 Max={p1}, P2 Empty={p2})",
        )

    def _apply_timer(self) -> None:
        en = self.var_freeze_timer.get()
        self._safe_run(lambda: self.engine.set_freeze_timer(en), f"Match Timer {'FROZEN' if en else 'UNFROZEN'}")

    def _apply_challenges(self) -> None:
        en = self.var_clear_chal.get()
        self._safe_run(
            lambda: self.engine.set_always_clear_challenges(en),
            f"Always Clear Challenges {'ENABLED' if en else 'DISABLED'}",
        )

    def _apply_quest_3_stars(self) -> None:
        en = self.var_quest_3_stars.get()
        self._safe_run(
            lambda: self.engine.set_quest_always_3_stars(en),
            f"Quest Always 3 Stars {'ENABLED' if en else 'DISABLED'}",
        )

    def _apply_score(self) -> None:
        en, mult, mx = self.var_score_cheat.get(), self.var_score_mult.get(), self.var_score_max_mode.get()
        self._safe_run(
            lambda: self.engine.set_score_cheat(en, mult, mx),
            f"Score cheat {'ENABLED' if en else 'DISABLED'}",
        )

    def _apply_speed(self) -> None:
        en, sc = self.var_speed_cheat.get(), self.var_speed_scale.get()
        self._safe_run(
            lambda: self.engine.set_speed_cheat(en, sc),
            f"Game Speed: {sc:.2f}x" if en else "Game Speed: Normal (1.0x)",
        )

    def _preset_speed(self, rate: float, disable: bool = False) -> None:
        self.var_speed_scale.set(rate)
        self.var_speed_cheat.set(not disable)
        self._apply_speed()

    def _preset_max_economy(self) -> None:
        def apply_all() -> None:
            self.engine.set_money(999999999)
            self.engine.set_owner_exp(99999999)
            self.engine.set_all_character_points(999999)

        self._safe_run(apply_all, "Maxed Money, Owner EXP, and Character Points (0..34).")

    def _force_rescan(self) -> None:
        self.disable_all_cheats()
        self.engine.detach(restore_patches=False)
        self.lbl_status_msg.set("Detached cleanly; rescanning DOA6LR.exe...")

    def disable_all_cheats(self) -> None:
        for var in (
            self.var_p1_inf_hp,
            self.var_p1_max_brk,
            self.var_p2_ohko,
            self.var_p2_empty_brk,
            self.var_freeze_timer,
            self.var_clear_chal,
            self.var_quest_3_stars,
            self.var_score_cheat,
            self.var_speed_cheat,
        ):
            var.set(False)
        if self.engine.is_attached:
            self.engine.disable_all_patches()
            self.engine.uninstall_all_hooks()
        self.lbl_status_msg.set("All cheats disabled and original bytes restored.")

    def _set_if_changed(self, key: str, var: tk.StringVar, value: str) -> None:
        if self._ui_cache.get(key) != value:
            self._ui_cache[key] = value
            var.set(value)

    def _style_pill(self, key: str, lbl: tk.Label, var: tk.StringVar, text: str, bg: str, fg: str) -> None:
        self._set_if_changed(f"{key}_txt", var, text)
        colors: Tuple[str, str] = (bg, fg)
        if self._ui_cache.get(f"{key}_col") != colors:
            self._ui_cache[f"{key}_col"] = colors
            lbl.configure(bg=bg, fg=fg)

    def _poll_hotkeys(self) -> None:
        if not self._hotkeys_enabled.get() or not self.engine.is_attached:
            if self._last_hotkey_state:
                self._last_hotkey_state.clear()
            return
        for vk, action in self._hotkey_actions.items():
            pressed = self.engine.hotkey_pressed(vk)
            was = self._last_hotkey_state.get(vk, False)
            self._last_hotkey_state[vk] = pressed
            if pressed and not was:
                action()

    def _update_ui_from_snapshot(self, snap: GameSnapshot) -> None:
        if not snap.attached:
            self._style_pill("attach", self.pill_attach, self.lbl_attach_var, "WAITING FOR DOA6LR.EXE...", self.RED_BG, self.RED)
            self._style_pill("match", self.pill_match, self.lbl_match_var, "NOT ATTACHED", "#262C3A", self.MUTED)
            self._style_pill("guard", self.pill_guard, self.lbl_guard_var, "OFFLINE GUARD READY", self.GREEN_BG, self.GREEN)
            return

        self._style_pill("attach", self.pill_attach, self.lbl_attach_var, f"ATTACHED (PID {snap.pid})", self.GREEN_BG, self.GREEN)

        if not snap.offline:
            self._style_pill(
                "guard",
                self.pill_guard,
                self.lbl_guard_var,
                f"ONLINE DETECTED ({snap.online_flag}) — CHEATS LOCKED",
                self.RED_BG,
                self.RED,
            )
            if self.engine.installed_hooks or self.engine.installed_patches:
                self.disable_all_cheats()
                self.lbl_status_msg.set("Offline Guard: Online mode entered; all cheats automatically disabled.")
        else:
            self._style_pill(
                "guard", self.pill_guard, self.lbl_guard_var, f"OFFLINE SAFE (FLAG {snap.online_flag})", self.GREEN_BG, self.GREEN
            )

        self._style_pill(
            "match",
            self.pill_match,
            self.lbl_match_var,
            "IN MATCH" if snap.in_match else "MENU / IDLE",
            "#1F2E4D" if snap.in_match else "#262C3A",
            self.ACCENT if snap.in_match else self.MUTED,
        )

        p1_txt = (
            f"HP: {snap.p1.current_hp} / {snap.p1.max_hp} (Dmg {snap.p1.damage_taken})   |   "
            f"Break: {snap.p1.break_cur} / {snap.p1.break_max}   |   DmgMode: {snap.p1.damage_mode}"
            if snap.p1
            else "Fighter 1 unavailable"
        )
        p2_txt = (
            f"HP: {snap.p2.current_hp} / {snap.p2.max_hp} (Dmg {snap.p2.damage_taken})   |   "
            f"Break: {snap.p2.break_cur} / {snap.p2.break_max}   |   DmgMode: {snap.p2.damage_mode}"
            if snap.p2
            else "Fighter 2 unavailable"
        )
        eco_txt = (
            f"Money: {snap.money:,}   |   Owner EXP: {snap.owner_exp:,}   |   "
            f"Live Score: {snap.live_score:,}   |   FrameSpd: {snap.frame_speed:.2f}x"
        )
        self._set_if_changed("p1", self.lbl_p1_stats, p1_txt)
        self._set_if_changed("p2", self.lbl_p2_stats, p2_txt)
        self._set_if_changed("eco", self.lbl_eco_stats, eco_txt)

    def _poll_loop(self) -> None:
        try:
            if not self.engine.is_attached:
                if self.engine.attach():
                    self.lbl_status_msg.set(
                        f"Attached to DOA6LR.exe (PID {self.engine.pid}). Symbols resolved via AOB."
                    )
            elif self.engine.read_bytes(self.engine.syms.base, 2) != b"MZ":  # type: ignore[union-attr]
                self.engine.detach(restore_patches=False)
                self._sync_toggles_to_engine_state()
                self.lbl_status_msg.set("DOA6LR.exe closed. Waiting for game restart...")

            snap = self.engine.read_snapshot()
            if snap.attached and snap.offline:
                if self.var_p1_inf_hp.get() and snap.p1 and snap.p1.damage_taken != 0:
                    self.engine.refill_p1_health(snap.p1.fighter_ptr)
                    snap.p1.damage_taken = 0
                if (
                    self.var_p1_max_brk.get()
                    and snap.p1
                    and snap.p1.break_max > 0
                    and snap.p1.break_cur < snap.p1.break_max
                ):
                    self.engine.refill_p1_break(snap.p1.fighter_ptr, snap.p1.break_max)
                    snap.p1.break_cur = snap.p1.break_max
                if self.var_p2_empty_brk.get() and snap.p2 and snap.p2.break_cur > 0:
                    self.engine.drain_p2_break(snap.p2.fighter_ptr)
                    snap.p2.break_cur = 0

            self._update_ui_from_snapshot(snap)
            self._poll_hotkeys()
        except Exception as exc:
            self.lbl_status_msg.set(f"Scan/Poll notice: {exc}")

        interval = POLL_ATTACHED_MS if self.engine.is_attached else POLL_WAITING_MS
        self.root.after(interval, self._poll_loop)

    def _cleanup_on_exit(self) -> None:
        if not self._cleaned:
            self._cleaned = True
            self.engine.detach(restore_patches=True)

    def _on_close(self) -> None:
        self._cleanup_on_exit()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DOA6LRTrainerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
