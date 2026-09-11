import threading
import tkinter as tk

COLORS = {
    "ai": "#E0D0FF",       # soft bright purple - reasoning
    "action": "#7CFC00",   # vibrant green - actions
    "warn": "#FF9F43",     # orange - warnings
    "info": "#8B949E",     # grey - status
    "title": "#FFD700",    # gold - section headers
    "predict": "#00E5FF",  # cyan - predictive reads
}

MIN_W, MIN_H = 340, 220


class AIOverlay:
    def __init__(self, rect, on_send_to_ai=None, on_set_foe=None, on_mode=None, on_scan=None, on_clear=None,
                 get_mode=None, get_scan=None, get_status=None, get_foe=None,
                 on_toggle_auto=None, get_auto=None, on_reload_state=None, on_ask=None,
                 on_add_foe=None, on_remove_foe=None, on_clear_foe=None, on_set_item=None,
                 on_add_my_mon=None, on_remove_my_mon=None, get_teams=None,
                 on_import_showdown=None, on_save_raw_data=None):
        self.root = tk.Tk()
        self.root.title("PRO AI Coach")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg="#0d1117")

        x1, y1, x2, y2 = rect
        self._w, self._h = 500, 390
        # park below the main coach overlay
        px = min(x2 + 12, self.root.winfo_screenwidth() - self._w - 8)
        py = max(y1 + 240, 40)
        self.root.geometry(f"{self._w}x{self._h}+{px}+{py}")

        # callbacks
        self.on_send_to_ai = on_send_to_ai or on_ask
        self.on_set_foe = on_set_foe
        self.on_mode = on_mode
        self.on_scan = on_scan
        self.on_clear = on_clear
        self.on_toggle_auto = on_toggle_auto
        self.get_auto = get_auto or (lambda: False)
        self.on_reload_state = on_reload_state
        self.get_mode = get_mode or (lambda: "random")
        self.get_scan = get_scan or (lambda: "")
        self.get_status = get_status or (lambda: "")
        self.get_foe = get_foe or (lambda: "")
        self.on_add_foe = on_add_foe
        self.on_remove_foe = on_remove_foe
        self.on_clear_foe = on_clear_foe
        self.on_set_item = on_set_item
        self.on_add_my_mon = on_add_my_mon
        self.on_remove_my_mon = on_remove_my_mon
        self.get_teams = get_teams or (lambda: {"my": [], "their": []})
        self.on_import_showdown = on_import_showdown
        self.on_save_raw_data = on_save_raw_data

        self._current_tab = "advice"
        self._is_user_edited = False
        self._last_state_data = ""
        self._last_calc_sig = object()

        # --- 1. Top Header (Draggable) ---
        bar = tk.Frame(self.root, bg="#1a1040")
        bar.pack(fill="x")
        self.header = tk.Label(
            bar, text=" \U0001f916 PRO AI COACH (Gemini)", fg="#C4A7FF",
            bg="#1a1040", font=("Consolas", 9, "bold"), anchor="w",
            cursor="fleur",
        )
        self.header.pack(side="left", fill="x", expand=True)
        close = tk.Label(bar, text=" \u2715 ", fg="#FF6B6B", bg="#1a1040",
                         font=("Consolas", 10, "bold"), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.root.destroy())

        # --- 2. Tab Navigation Bar ---
        self.nav_bar = tk.Frame(self.root, bg="#120c2b")
        self.nav_bar.pack(fill="x", padx=4, pady=(3, 1))

        self.tab_advice = tk.Label(
            self.nav_bar, text="🎯 AI ADVICE", fg="#FFD700", bg="#251a52",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=8, pady=2,
            bd=1, relief="ridge",
        )
        self.tab_advice.pack(side="left", padx=2)
        self.tab_advice.bind("<Button-1>", lambda e: self.show_tab("advice"))

        self.tab_team = tk.Label(
            self.nav_bar, text="👥 6v6 TEAMS", fg="#8B949E", bg="#120c2b",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=9, pady=2,
            bd=1, relief="ridge",
        )
        self.tab_team.pack(side="left", padx=2)
        self.tab_team.bind("<Button-1>", lambda e: self.show_tab("team"))

        self.tab_import = tk.Label(
            self.nav_bar, text="📋 IMPORT", fg="#8B949E", bg="#120c2b",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=8, pady=2,
            bd=1, relief="ridge",
        )
        self.tab_import.pack(side="left", padx=2)
        self.tab_import.bind("<Button-1>", lambda e: self.show_tab("import"))

        self.tab_data = tk.Label(
            self.nav_bar, text="✏️ RAW DATA", fg="#8B949E", bg="#120c2b",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=8, pady=2,
            bd=1, relief="ridge",
        )
        self.tab_data.pack(side="left", padx=2)
        self.tab_data.bind("<Button-1>", lambda e: self.show_tab("data"))

        self.reload_btn = tk.Label(
            self.nav_bar, text="⟳ RELOAD", fg="#00E5FF", bg="#120c2b",
            font=("Consolas", 8, "bold"), cursor="hand2", padx=6, pady=2,
            bd=1, relief="flat",
        )
        self.reload_btn.pack(side="right", padx=2)
        self.reload_btn.bind("<Button-1>", lambda e: self._reload_data())

        # --- 3. Bottom Control Bar (Streamlined & Minimal) ---
        ctrl = tk.Frame(self.root, bg="#1a1040")
        ctrl.pack(side="bottom", fill="x")

        self.btn_bar = tk.Frame(ctrl, bg="#1a1040")
        self.btn_bar.pack(fill="x", padx=6, pady=(3, 3))

        self.send_btn = tk.Label(
            self.btn_bar, text="🎯 SEND TO AI", fg="#7CFC00", bg="#23174d",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=10, pady=3,
            bd=1, relief="ridge",
        )
        self.send_btn.pack(side="left", padx=(0, 4))
        self.send_btn.bind("<Button-1>", lambda e: self._handle_send_to_ai())

        self.auto_btn = tk.Label(
            self.btn_bar, text="⚡ AUTO: OFF", fg="#8B949E", bg="#1a1040",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=8, pady=3,
            bd=1, relief="ridge",
        )
        self.auto_btn.pack(side="left", padx=2)
        self.auto_btn.bind("<Button-1>", lambda e: self._toggle_auto())

        self.status_lbl = tk.Label(
            self.btn_bar, text="", fg="#8B949E", bg="#1a1040",
            font=("Consolas", 8), anchor="w", padx=6,
        )
        self.status_lbl.pack(side="left", fill="x", expand=True)

        # resize grip
        grip = tk.Label(self.root, text=" \u26F6 ", fg="#8B949E", bg="#0d1117",
                        font=("Consolas", 10), cursor="sizing")
        grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)

        # --- 4. Content Area (3 Views) ---
        self.content_frame = tk.Frame(self.root, bg="#0d1117")
        self.content_frame.pack(fill="both", expand=True, padx=6, pady=(2, 2))

        # View A: Formatted AI Advice + Zero-Latency Tactical Quick-Calc Strip
        self.advice_container = tk.Frame(self.content_frame, bg="#0d1117")
        self.advice_container.pack(fill="both", expand=True)

        # Instant Quick-Calc Header Bar (<1ms local math)
        self.calc_bar = tk.Frame(self.advice_container, bg="#130e26", bd=1, relief="ridge")
        self.calc_bar.pack(fill="x", pady=(0, 2))

        # 1. Stockfish-style Quantum Evaluation Row & Choice-Lock / Bluff Pill
        self.calc_eval_row = tk.Frame(self.calc_bar, bg="#130e26")
        self.calc_eval_row.pack(fill="x", padx=4, pady=(2, 1))

        self.eval_text_lbl = tk.Label(
            self.calc_eval_row, text="♜ EVAL: +0.0 (50% Win Prob)",
            fg="#00E5FF", bg="#130e26", font=("Consolas", 8, "bold"),
        )
        self.eval_text_lbl.pack(side="left")

        self.choice_pill = tk.Label(
            self.calc_eval_row, text="",
            fg="#FF9F43", bg="#130e26", font=("Consolas", 8, "bold"),
        )
        self.choice_pill.pack(side="right", padx=2)

        # Visual Evaluation Gauge Bar (Canvas)
        self.eval_bar_canvas = tk.Canvas(self.calc_bar, height=5, bg="#21262D", highlightthickness=0, bd=0)
        self.eval_bar_canvas.pack(fill="x", padx=4, pady=(1, 2))
        self.eval_bar_canvas.bind("<Configure>", lambda e: self._draw_eval_gauge())

        # 2. Speed Tier Row
        self.calc_speed_row = tk.Frame(self.calc_bar, bg="#130e26")
        self.calc_speed_row.pack(fill="x", padx=4, pady=(1, 1))

        self.speed_pill = tk.Label(
            self.calc_speed_row, text="⚡ Speed Tier: Waiting for matchup...",
            fg="#8B949E", bg="#130e26", font=("Consolas", 8, "bold"),
        )
        self.speed_pill.pack(side="left")

        self.scarf_pill = tk.Label(
            self.calc_speed_row, text="",
            fg="#FF9F43", bg="#130e26", font=("Consolas", 8, "bold"),
        )
        self.scarf_pill.pack(side="right", padx=2)

        self.calc_moves_row = tk.Frame(self.calc_bar, bg="#130e26")
        self.calc_moves_row.pack(fill="x", padx=4, pady=(1, 1))

        self.calc_tactics_row = tk.Frame(self.calc_bar, bg="#130e26")
        self.calc_tactics_row.pack(fill="x", padx=4, pady=(1, 2))

        self.tactics_switch_pill = tk.Label(
            self.calc_tactics_row, text="",
            fg="#D2A8FF", bg="#130e26", font=("Consolas", 8, "bold"),
        )
        self.tactics_switch_pill.pack(side="left")

        self.tactics_trap_pill = tk.Label(
            self.calc_tactics_row, text="",
            fg="#FF9F43", bg="#130e26", font=("Consolas", 8, "bold"),
        )
        self.tactics_trap_pill.pack(side="left", padx=6)

        self.tactics_wincon_pill = tk.Label(
            self.calc_tactics_row, text="",
            fg="#FFD700", bg="#130e26", font=("Consolas", 8, "bold"),
        )
        self.tactics_wincon_pill.pack(side="right", padx=2)

        self.body = tk.Text(
            self.advice_container, bg="#0d1117", fg="#E0D0FF", bd=0,
            highlightthickness=0, font=("Consolas", 10),
            state="disabled", wrap="word",
        )
        self.body.pack(fill="both", expand=True)

        for cat, col in COLORS.items():
            self.body.tag_configure(cat, foreground=col)
        self.body.tag_configure("title", foreground="#FFD700", font=("Consolas", 10, "bold"))
        self.body.tag_configure("title_a", foreground="#7CFC00", font=("Consolas", 10, "bold"))
        self.body.tag_configure("title_b", foreground="#FFD700", font=("Consolas", 10, "bold"))
        self.body.tag_configure("title_context", foreground="#D2A8FF", font=("Consolas", 10, "bold"))
        self.body.tag_configure("action", foreground="#7CFC00", font=("Consolas", 10, "bold"))
        self.body.tag_configure("option_a", foreground="#A3FFA3")
        self.body.tag_configure("option_b", foreground="#FFE5A3")
        self.body.tag_configure("context", foreground="#E0D0FF")
        self.body.tag_configure("predict", foreground="#00E5FF")
        self.body.tag_configure("warn", foreground="#FF9F43")
        self.body.tag_configure("ai", foreground="#E0D0FF")

        # View B: Editable Battle Data Editor with Save Toolbar
        self.data_container = tk.Frame(self.content_frame, bg="#0d1117")
        data_toolbar = tk.Frame(self.data_container, bg="#120c2b")
        data_toolbar.pack(fill="x", pady=(0, 2))

        self.save_data_btn = tk.Label(
            data_toolbar, text="💾 SAVE DATA", fg="#7CFC00", bg="#1f1642",
            font=("Consolas", 8, "bold"), cursor="hand2", padx=8, pady=2, bd=1, relief="ridge",
        )
        self.save_data_btn.pack(side="left", padx=2)
        self.save_data_btn.bind("<Button-1>", lambda e: self._handle_save_raw_data())

        self.reload_data_btn = tk.Label(
            data_toolbar, text="⟳ RE-SYNC OCR", fg="#00E5FF", bg="#1f1642",
            font=("Consolas", 8, "bold"), cursor="hand2", padx=8, pady=2, bd=1, relief="ridge",
        )
        self.reload_data_btn.pack(side="left", padx=2)
        self.reload_data_btn.bind("<Button-1>", lambda e: self._reload_data())

        self.data_status_badge = tk.Label(
            data_toolbar, text="Live Auto-Sync Active", fg="#8B949E", bg="#120c2b",
            font=("Consolas", 8, "italic"), padx=6,
        )
        self.data_status_badge.pack(side="left", padx=4)

        self.data_editor = tk.Text(
            self.data_container, bg="#070a10", fg="#79C0FF", insertbackground="#FFFFFF",
            bd=1, relief="solid", highlightthickness=1, highlightcolor="#8957E5",
            highlightbackground="#30363D", font=("Consolas", 9),
            wrap="word", undo=True,
        )
        self.data_editor.pack(fill="both", expand=True)
        self.data_editor.bind("<Key>", self._on_user_edited)

        # View C: 6v6 Team & Held Item Manager
        self.team_container = tk.Frame(self.content_frame, bg="#0d1117")
        self.team_canvas = tk.Canvas(self.team_container, bg="#0d1117", highlightthickness=0, bd=0)
        self.team_scrollbar = tk.Scrollbar(self.team_container, orient="vertical", command=self.team_canvas.yview)
        self.team_scroll_frame = tk.Frame(self.team_canvas, bg="#0d1117")

        self.team_scroll_frame.bind(
            "<Configure>",
            lambda e: self.team_canvas.configure(scrollregion=self.team_canvas.bbox("all"))
        )
        self._team_window = self.team_canvas.create_window((0, 0), window=self.team_scroll_frame, anchor="nw")
        self.team_canvas.configure(yscrollcommand=self.team_scrollbar.set)

        self.team_scrollbar.pack(side="right", fill="y")
        self.team_canvas.pack(side="left", fill="both", expand=True)
        self.team_canvas.bind(
            "<Configure>",
            lambda e: self.team_canvas.itemconfig(self._team_window, width=e.width)
        )

        def _on_mousewheel(event):
            self.team_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.team_scroll_frame.bind("<Enter>", lambda e: self.team_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.team_scroll_frame.bind("<Leave>", lambda e: self.team_canvas.unbind_all("<MouseWheel>"))

        # View D: Embedded In-Place Team Importer (Showdown & PRO In-Game)
        self.import_container = tk.Frame(self.content_frame, bg="#0d1117")

        import_hdr = tk.Frame(self.import_container, bg="#1a1040")
        import_hdr.pack(fill="x", pady=(0, 2))
        tk.Label(
            import_hdr, text="📋 IMPORT SHOWDOWN / PRO IN-GAME TEAM",
            fg="#FFD700", bg="#1a1040", font=("Consolas", 9, "bold"), padx=6, pady=3,
        ).pack(side="left")

        import_hint = tk.Label(
            self.import_container,
            text="Paste team directly from PRO in-game info or Showdown export. Team is auto-saved to saved_team.txt!",
            fg="#8B949E", bg="#0d1117", font=("Consolas", 8), anchor="w",
        )
        import_hint.pack(fill="x", padx=4, pady=(0, 2))

        self.import_entry = tk.Text(
            self.import_container, bg="#070a10", fg="#79C0FF", insertbackground="#FFFFFF",
            bd=1, relief="solid", highlightthickness=1, highlightcolor="#8957E5",
            highlightbackground="#30363D", font=("Consolas", 9),
            wrap="word", undo=True,
        )
        self.import_entry.pack(fill="both", expand=True, padx=2, pady=2)

        import_btn_bar = tk.Frame(self.import_container, bg="#120c2b")
        import_btn_bar.pack(fill="x", pady=(3, 1))

        self.import_save_btn = tk.Label(
            import_btn_bar, text="✔ SAVE & LOCK TEAM", fg="#7CFC00", bg="#201548",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=10, pady=3, bd=1, relief="ridge",
        )
        self.import_save_btn.pack(side="left", padx=2)
        self.import_save_btn.bind("<Button-1>", lambda e: self._handle_import_submit())

        self.import_paste_btn = tk.Label(
            import_btn_bar, text="📋 PASTE CLIPBOARD", fg="#00E5FF", bg="#201548",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=10, pady=3, bd=1, relief="ridge",
        )
        self.import_paste_btn.pack(side="left", padx=2)
        self.import_paste_btn.bind("<Button-1>", lambda e: self._handle_import_paste_clipboard())

        self.import_clear_btn = tk.Label(
            import_btn_bar, text="✕ CLEAR", fg="#FF6B6B", bg="#201548",
            font=("Consolas", 9), cursor="hand2", padx=8, pady=3, bd=1, relief="ridge",
        )
        self.import_clear_btn.pack(side="left", padx=2)
        self.import_clear_btn.bind("<Button-1>", lambda e: self._handle_import_clear())

        self.import_view_team_btn = tk.Label(
            import_btn_bar, text="👥 6v6 TEAMS", fg="#8B949E", bg="#201548",
            font=("Consolas", 9), cursor="hand2", padx=8, pady=3, bd=1, relief="ridge",
        )
        self.import_view_team_btn.pack(side="right", padx=2)
        self.import_view_team_btn.bind("<Button-1>", lambda e: self.show_tab("team"))

        # Window bindings
        self.header.bind("<Button-1>", self._drag_start)
        self.header.bind("<B1-Motion>", self._drag_move)
        grip.bind("<Button-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)
        self.root.bind("<Control-f>", lambda e: self.show_tab("team"))
        self.root.bind("<Control-F>", lambda e: self.show_tab("team"))

        self.root.after(800, self._tick)

    def show_tab(self, name):
        """Switch between 'advice', 'data' editor, 'team' view, and 'import' tab."""
        self._current_tab = name
        self.advice_container.pack_forget()
        self.data_container.pack_forget()
        self.team_container.pack_forget()
        self.import_container.pack_forget()

        self.tab_advice.config(fg="#8B949E", bg="#120c2b")
        self.tab_data.config(
            fg="#FF9F43" if self._is_user_edited else "#8B949E",
            bg="#201348" if self._is_user_edited else "#120c2b",
        )
        self.tab_team.config(fg="#8B949E", bg="#120c2b")
        self.tab_import.config(fg="#8B949E", bg="#120c2b")

        if name == "import":
            self.import_container.pack(fill="both", expand=True)
            self.tab_import.config(fg="#FFD700", bg="#251a52")
            # If entry empty, prefill from current team
            if not self.import_entry.get("1.0", "end").strip():
                try:
                    from procoach.state import format_showdown_team
                    teams = self.get_teams() if self.get_teams else {}
                    my_team = teams.get("my") or []
                    if my_team:
                        txt = format_showdown_team(my_team)
                        if txt:
                            self.import_entry.insert("1.0", txt.strip() + "\n")
                except Exception:
                    pass
        elif name == "data":
            self.data_container.pack(fill="both", expand=True)
            self.tab_data.config(fg="#FFD700", bg="#251a52")
        elif name == "team":
            self.team_container.pack(fill="both", expand=True)
            self.tab_team.config(fg="#FFD700", bg="#251a52")
            self.refresh_teams_view()
        else:
            self.advice_container.pack(fill="both", expand=True)
            self.tab_advice.config(fg="#FFD700", bg="#251a52")

    def _handle_set_item(self, side, key, item_str, ent_widget=None):
        if not key:
            return
        clean_item = item_str.strip()
        if self.on_set_item:
            self.on_set_item(side, key, clean_item)
            if self.on_reload_state:
                latest = self.on_reload_state()
                if latest:
                    self.set_state_data(latest, force=True)
            if ent_widget:
                try:
                    orig = ent_widget.cget("bg")
                    ent_widget.config(bg="#1c3d28")
                    ent_widget.after(350, lambda: ent_widget.config(bg=orig))
                except Exception:
                    pass

    def _handle_remove_foe(self, key):
        if key and self.on_remove_foe:
            self.on_remove_foe(key)
            if self.on_reload_state:
                latest = self.on_reload_state()
                if latest:
                    self.set_state_data(latest, force=True)
            self.refresh_teams_view()

    def _handle_remove_my(self, key):
        if key and self.on_remove_my_mon:
            self.on_remove_my_mon(key)
            if self.on_reload_state:
                latest = self.on_reload_state()
                if latest:
                    self.set_state_data(latest, force=True)
            self.refresh_teams_view()

    def _handle_clear_foe(self):
        if self.on_clear_foe:
            self.on_clear_foe()
            if self.on_reload_state:
                latest = self.on_reload_state()
                if latest:
                    self.set_state_data(latest, force=True)
            self.refresh_teams_view()

    def _handle_scan_team(self):
        if self.on_scan:
            self.on_scan()
            self.refresh_teams_view()

    def _handle_clear_my_team(self):
        if self.on_clear:
            self.on_clear()
            if self.on_reload_state:
                latest = self.on_reload_state()
                if latest:
                    self.set_state_data(latest, force=True)
            self.refresh_teams_view()

    def _draw_eval_gauge(self, win_pct=None, color=None):
        """Draws a horizontal Stockfish-style win-probability gauge bar."""
        if win_pct is not None:
            self._last_win_pct = win_pct
        if color is not None:
            self._last_eval_color = color
        pct = getattr(self, "_last_win_pct", 50)
        col = getattr(self, "_last_eval_color", "#00E5FF")
        try:
            w = self.eval_bar_canvas.winfo_width()
            h = self.eval_bar_canvas.winfo_height() or 5
            if w <= 1:
                w = self._w - 20
            self.eval_bar_canvas.delete("all")
            fill_w = max(2, int(w * (pct / 100.0)))
            self.eval_bar_canvas.create_rectangle(0, 0, fill_w, h, fill=col, outline="")
            self.eval_bar_canvas.create_rectangle(fill_w, 0, w, h, fill="#21262D", outline="")
        except Exception:
            pass

    def set_quick_calc(self, data):
        """Updates the zero-latency speed, damage, evaluation, and tactical strip instantly (<1ms). Thread-safe & memoized."""
        if not data:
            calc_sig = None
        else:
            sp = data.get("speed", {})
            mvs = tuple(
                (m.get("name"), m.get("damage_str"), m.get("ko_str"), m.get("effectiveness"))
                for m in data.get("moves", [])
            )
            tactics = data.get("tactics") or {}
            sw = tactics.get("switch_pressure") or {}
            tr = tuple(t.get("alert") for t in tactics.get("traps", []))
            wc = tactics.get("win_con") or {}
            tactics_sig = (sw.get("odds"), sw.get("reason"), tr, wc.get("key"))
            ev = data.get("eval") or tactics.get("eval") or {}
            eval_sig = (ev.get("win_pct"), ev.get("eval_str"))
            ci = data.get("choice_intel") or tactics.get("choice_intel") or {}
            choice_sig = (ci.get("th_locked_move"), ci.get("bluff_ready"))
            calc_sig = (sp.get("text"), sp.get("scarf_text"), mvs, tactics_sig, eval_sig, choice_sig)

        if calc_sig == getattr(self, "_last_calc_sig", object()):
            return
        self._last_calc_sig = calc_sig

        def _update():
            if not data:
                self.eval_text_lbl.config(text="♜ EVAL: +0.0 (50% Win Prob)", fg="#8B949E")
                self.choice_pill.config(text="")
                self._draw_eval_gauge(50, "#8B949E")
                self.speed_pill.config(text="⚡ Speed Tier: Waiting for battle turn...", fg="#8B949E")
                self.scarf_pill.config(text="")
                self.tactics_switch_pill.config(text="")
                self.tactics_trap_pill.config(text="")
                self.tactics_wincon_pill.config(text="")
                for child in self.calc_moves_row.winfo_children():
                    child.destroy()
                return

            # Stockfish Evaluation Update
            ev = data.get("eval") or (data.get("tactics", {}).get("eval"))
            if ev:
                win_pct = ev.get("win_pct", 50)
                eval_str = ev.get("eval_str", "+0.0")
                bar_col = ev.get("bar_color", "#00E5FF")
                lead_txt = ev.get("lead_text", "EVEN")
                self.eval_text_lbl.config(text=f"♜ EVAL: {eval_str} | {win_pct}% WIN PROB [{lead_txt}]", fg=bar_col)
                self._draw_eval_gauge(win_pct, bar_col)
            else:
                self.eval_text_lbl.config(text="♜ EVAL: +0.0 (50% Win Prob)", fg="#8B949E")
                self._draw_eval_gauge(50, "#8B949E")

            # Choice-Lock / Bluff Pill Update
            ci = data.get("choice_intel") or (data.get("tactics", {}).get("choice_intel"))
            if ci:
                if ci.get("th_locked_move"):
                    lk_name = ci.get("th_locked_name") or "MOVE"
                    self.choice_pill.config(text=f"🔒 FOE LOCKED: {lk_name.upper()}", fg="#FF4D4D")
                elif ci.get("bluff_ready"):
                    self.choice_pill.config(text="🎭 BLUFF READY", fg="#D2A8FF")
                else:
                    self.choice_pill.config(text="")
            else:
                self.choice_pill.config(text="")

            sp = data.get("speed", {})
            if sp:
                self.speed_pill.config(text=sp.get("text", ""), fg=sp.get("color", "#8B949E"))
                self.scarf_pill.config(text=sp.get("scarf_text", ""))

            for child in self.calc_moves_row.winfo_children():
                child.destroy()

            moves = data.get("moves", [])
            if moves:
                for m in moves:
                    dmg = m.get("damage_str", "")
                    ko = f" ({m['ko_str']})" if m.get("ko_str") else ""
                    chip_text = f"{m['name']}: {dmg}{ko}"
                    eff = m.get("effectiveness", 1.0)
                    chip_fg = "#7CFC00" if eff >= 2.0 else ("#FF6B6B" if eff == 0.0 else ("#FF9F43" if eff < 1.0 else "#79C0FF"))
                    tk.Label(
                        self.calc_moves_row, text=chip_text, fg=chip_fg, bg="#0d1117",
                        font=("Consolas", 8, "bold"), bd=1, relief="solid", padx=4, pady=1,
                    ).pack(side="left", padx=2)

            tactics = data.get("tactics") or {}
            sw = tactics.get("switch_pressure")
            if sw:
                sw_odds = sw.get("odds", 0)
                targets = sw.get("top_targets", [])
                target_str = f" [{targets[0]['name']}]" if targets else ""
                sw_fg = "#7CFC00" if sw_odds >= 75 else ("#D2A8FF" if sw_odds >= 40 else "#8B949E")
                self.tactics_switch_pill.config(text=f"⚡ Switch Odds: {sw_odds}%{target_str}", fg=sw_fg)
            else:
                self.tactics_switch_pill.config(text="")

            traps = tactics.get("traps", [])
            if traps:
                self.tactics_trap_pill.config(text=traps[0].get("alert", ""))
            else:
                self.tactics_trap_pill.config(text="")

            win_con = tactics.get("win_con")
            if win_con:
                self.tactics_wincon_pill.config(text=f"★ Win-Con: {win_con['name']}", fg="#FFD700")
            else:
                self.tactics_wincon_pill.config(text="")


        if threading.current_thread() is threading.main_thread():
            _update()
        else:
            self.root.after(0, _update)

    def _handle_import_submit(self):
        content = self.import_entry.get("1.0", "end").strip()
        if content and self.on_import_showdown:
            count = self.on_import_showdown(content)
            if self.on_reload_state:
                latest = self.on_reload_state()
                if latest:
                    self.set_state_data(latest, force=True)
            self.refresh_teams_view()
            self.set_status(f"✔ Saved & Locked {count} Pokémon into 6v6 Team!")
            self.show_tab("team")
        elif not content:
            self.set_status("Paste Showdown or PRO team text first")

    def _handle_import_paste_clipboard(self):
        try:
            clip = self.root.clipboard_get()
            if clip:
                self.import_entry.delete("1.0", "end")
                self.import_entry.insert("1.0", clip.strip() + "\n")
                self.set_status("Clipboard pasted. Click [✔ SAVE & LOCK TEAM]")
        except Exception:
            self.set_status("Clipboard is empty or inaccessible")

    def _handle_import_clear(self):
        self.import_entry.delete("1.0", "end")
        self.set_status("Import text cleared")

    def _handle_save_raw_data(self):
        text = self.get_state_data()
        if self.on_save_raw_data:
            self.on_save_raw_data(text)
        self._is_user_edited = False
        self.tab_data.config(text="✏️ RAW DATA", fg="#FFD700")
        self.data_status_badge.config(text="✔ Saved to state.txt", fg="#7CFC00")
        self.root.after(2000, lambda: self.data_status_badge.config(text="Live Auto-Sync Active", fg="#8B949E"))
        self.set_status("Raw battle data saved to state.txt")

    def refresh_teams_view(self):
        """Renders the 6v6 rosters and held items for player and opponent."""
        for widget in self.team_scroll_frame.winfo_children():
            widget.destroy()

        teams = self.get_teams() if self.get_teams else {"my": [], "their": []}
        my_team = teams.get("my") or []
        their_team = teams.get("their") or []

        # ==========================================
        # 1. PLAYER TEAM (MY TEAM)
        # ==========================================
        sec1_bar = tk.Frame(self.team_scroll_frame, bg="#1a1040")
        sec1_bar.pack(fill="x", pady=(2, 4), padx=2)

        tk.Label(
            sec1_bar, text=f"MY TEAM ({len(my_team)}/6 Analyzed)", fg="#00E5FF", bg="#1a1040",
            font=("Consolas", 9, "bold"), padx=4,
        ).pack(side="left")

        # Scanner controls and Showdown import in My Team header
        scan_msg = self.get_scan() if self.get_scan else ""
        is_scanning = bool(scan_msg and any(w in scan_msg for w in ("reading", "starting", "open next", "1/", "2/", "3/", "4/", "5/")))
        scan_txt = "STOP SCAN" if is_scanning else "SCAN TEAM"
        scan_fg = "#FF9F43" if is_scanning else "#00E5FF"

        clear_my_btn = tk.Label(
            sec1_bar, text="CLEAR", fg="#FF6B6B", bg="#201548",
            font=("Consolas", 8, "bold"), cursor="hand2", padx=5, pady=1, bd=1, relief="ridge",
        )
        clear_my_btn.pack(side="right", padx=2)
        clear_my_btn.bind("<Button-1>", lambda e: self._handle_clear_my_team())

        scan_btn = tk.Label(
            sec1_bar, text=scan_txt, fg=scan_fg, bg="#201548",
            font=("Consolas", 8, "bold"), cursor="hand2", padx=5, pady=1, bd=1, relief="ridge",
        )
        scan_btn.pack(side="right", padx=2)
        scan_btn.bind("<Button-1>", lambda e: self._handle_scan_team())

        sd_btn = tk.Label(
            sec1_bar, text="📋 IMPORT / SD", fg="#FFD700", bg="#201548",
            font=("Consolas", 8, "bold"), cursor="hand2", padx=5, pady=1, bd=1, relief="ridge",
        )
        sd_btn.pack(side="right", padx=2)
        sd_btn.bind("<Button-1>", lambda e: self.show_tab("import"))

        # Quick add bar for player mon
        my_add_frame = tk.Frame(self.team_scroll_frame, bg="#0d1117")
        my_add_frame.pack(fill="x", padx=4, pady=(0, 4))

        tk.Label(my_add_frame, text="Add Mon:", fg="#8B949E", bg="#0d1117", font=("Consolas", 8)).pack(side="left")
        my_add_ent = tk.Entry(my_add_frame, bg="#161b22", fg="#FFFFFF", font=("Consolas", 8), width=20, bd=1, relief="solid")
        my_add_ent.pack(side="left", padx=3)
        my_add_ent.insert(0, "e.g. Zarude @ Scarf")
        my_add_ent.bind("<FocusIn>", lambda e: my_add_ent.delete(0, "end") if "e.g." in my_add_ent.get() else None)

        def _do_add_my():
            val = my_add_ent.get().strip()
            if val and "e.g." not in val and self.on_add_my_mon:
                self.on_add_my_mon(val)
                if self.on_reload_state:
                    latest = self.on_reload_state()
                    if latest:
                        self.set_state_data(latest, force=True)
                self.refresh_teams_view()

        my_add_btn = tk.Label(my_add_frame, text="+ ADD", fg="#00E5FF", bg="#1f1642", font=("Consolas", 8, "bold"), padx=6, cursor="hand2", bd=1, relief="ridge")
        my_add_btn.pack(side="left", padx=2)
        my_add_btn.bind("<Button-1>", lambda e: _do_add_my())
        my_add_ent.bind("<Return>", lambda e: _do_add_my())

        if not my_team:
            tk.Label(
                self.team_scroll_frame, text="  (No team loaded yet. Click 📋 SHOWDOWN, SCAN TEAM, or add above)",
                fg="#6E7681", bg="#0d1117", font=("Consolas", 8, "italic"),
            ).pack(anchor="w", padx=6, pady=2)
        else:
            for idx, mon in enumerate(my_team[:6], 1):
                card = tk.Frame(self.team_scroll_frame, bg="#13102b", bd=1, relief="solid", highlightthickness=0)
                card.pack(fill="x", padx=4, pady=2)

                top_row = tk.Frame(card, bg="#13102b")
                top_row.pack(fill="x", padx=4, pady=2)

                status = mon.get("status", "")
                badge_fg = "#7CFC00" if status == "ACTIVE" else ("#FF6B6B" if status == "FAINTED" else "#8B949E")
                badge_text = f"[{status}]" if status else f"#{idx}"
                tk.Label(top_row, text=badge_text, fg=badge_fg, bg="#13102b", font=("Consolas", 8, "bold")).pack(side="left")

                tk.Label(
                    top_row, text=f" {mon.get('name', '?')}", fg="#FFFFFF", bg="#13102b",
                    font=("Consolas", 9, "bold"),
                ).pack(side="left")

                types_str = "/".join(mon.get("types", []))
                if types_str:
                    tk.Label(top_row, text=f"({types_str})", fg="#8B949E", bg="#13102b", font=("Consolas", 8)).pack(side="left", padx=3)

                del_btn = tk.Label(top_row, text="✕", fg="#FF6B6B", bg="#13102b", font=("Consolas", 9, "bold"), cursor="hand2")
                del_btn.pack(side="right", padx=2)
                del_btn.bind("<Button-1>", lambda e, k=mon.get("key"): self._handle_remove_my(k))

                cur_item = mon.get("item") or ""
                item_frame = tk.Frame(top_row, bg="#13102b")
                item_frame.pack(side="right", padx=6)
                tk.Label(item_frame, text="Item:", fg="#8B949E", bg="#13102b", font=("Consolas", 8)).pack(side="left")
                item_ent = tk.Entry(item_frame, bg="#0d1117", fg="#79C0FF", insertbackground="#FFF", font=("Consolas", 8), width=14, bd=1, relief="solid")
                item_ent.pack(side="left", padx=2)
                if cur_item:
                    item_ent.insert(0, cur_item)
                item_ent.bind("<Return>", lambda e, k=mon.get("key"), ent=item_ent: self._handle_set_item("my", k, ent.get(), ent))
                item_ent.bind("<FocusOut>", lambda e, k=mon.get("key"), ent=item_ent: self._handle_set_item("my", k, ent.get(), ent))

                mvs = mon.get("moves") or []
                if mvs:
                    bot_row = tk.Frame(card, bg="#13102b")
                    bot_row.pack(fill="x", padx=16, pady=(0, 2))
                    lck = mon.get("locked", False)
                    lck_badge = "[🔒 LOCKED] " if lck else ""
                    lck_fg = "#7CFC00" if lck else "#A5D6FF"
                    tk.Label(bot_row, text=lck_badge + "Moves: " + ", ".join(mvs), fg=lck_fg, bg="#13102b", font=("Consolas", 8)).pack(anchor="w")

        # ==========================================
        # 2. OPPONENT TEAM (THEIR TEAM - 6 SLOTS)
        # ==========================================
        sep = tk.Frame(self.team_scroll_frame, bg="#30363D", height=1)
        sep.pack(fill="x", padx=4, pady=8)

        sec2_bar = tk.Frame(self.team_scroll_frame, bg="#201348")
        sec2_bar.pack(fill="x", pady=(2, 4), padx=2)

        rev_count = min(6, len(their_team))
        tk.Label(
            sec2_bar, text=f"OPPONENT TEAM ({rev_count}/6 Slots Revealed)", fg="#FFD700", bg="#201348",
            font=("Consolas", 9, "bold"), padx=4,
        ).pack(side="left")

        clr_foe_btn = tk.Label(
            sec2_bar, text="CLEAR FOE", fg="#FF6B6B", bg="#201348",
            font=("Consolas", 8, "bold"), cursor="hand2", padx=6, pady=1, bd=1, relief="ridge",
        )
        clr_foe_btn.pack(side="right", padx=2)
        clr_foe_btn.bind("<Button-1>", lambda e: self._handle_clear_foe())

        foe_add_frame = tk.Frame(self.team_scroll_frame, bg="#0d1117")
        foe_add_frame.pack(fill="x", padx=4, pady=(0, 4))

        tk.Label(foe_add_frame, text="Add Foe:", fg="#FFD700", bg="#0d1117", font=("Consolas", 8, "bold")).pack(side="left")
        foe_add_ent = tk.Entry(foe_add_frame, bg="#161b22", fg="#FFFFFF", font=("Consolas", 8), width=20, bd=1, relief="solid")
        foe_add_ent.pack(side="left", padx=3)
        foe_add_ent.insert(0, "e.g. Garchomp @ Scarf")
        foe_add_ent.bind("<FocusIn>", lambda e: foe_add_ent.delete(0, "end") if "e.g." in foe_add_ent.get() else None)

        def _do_add_foe():
            val = foe_add_ent.get().strip()
            if val and "e.g." not in val and self.on_add_foe:
                self.on_add_foe(val)
                if self.on_reload_state:
                    latest = self.on_reload_state()
                    if latest:
                        self.set_state_data(latest, force=True)
                self.refresh_teams_view()

        foe_add_btn = tk.Label(foe_add_frame, text="+ ADD FOE", fg="#7CFC00", bg="#281c4e", font=("Consolas", 8, "bold"), padx=6, cursor="hand2", bd=1, relief="ridge")
        foe_add_btn.pack(side="left", padx=2)
        foe_add_btn.bind("<Button-1>", lambda e: _do_add_foe())
        foe_add_ent.bind("<Return>", lambda e: _do_add_foe())

        for slot_num in range(1, 7):
            if slot_num <= len(their_team):
                mon = their_team[slot_num - 1]
                card = tk.Frame(self.team_scroll_frame, bg="#1d122f", bd=1, relief="solid", highlightthickness=0)
                card.pack(fill="x", padx=4, pady=2)

                top_row = tk.Frame(card, bg="#1d122f")
                top_row.pack(fill="x", padx=4, pady=2)

                status = mon.get("status", "")
                badge_fg = "#7CFC00" if status == "ACTIVE" else ("#FF6B6B" if status == "FAINTED" else "#FFD700")
                badge_text = f"[{status}]" if status else f"Slot {slot_num}"
                tk.Label(top_row, text=badge_text, fg=badge_fg, bg="#1d122f", font=("Consolas", 8, "bold")).pack(side="left")

                tk.Label(
                    top_row, text=f" {mon.get('name', '?')}", fg="#FFD700", bg="#1d122f",
                    font=("Consolas", 9, "bold"),
                ).pack(side="left")

                types_str = "/".join(mon.get("types", []))
                if types_str:
                    tk.Label(top_row, text=f"({types_str})", fg="#8B949E", bg="#1d122f", font=("Consolas", 8)).pack(side="left", padx=3)

                del_btn = tk.Label(top_row, text="✕", fg="#FF6B6B", bg="#1d122f", font=("Consolas", 9, "bold"), cursor="hand2")
                del_btn.pack(side="right", padx=2)
                del_btn.bind("<Button-1>", lambda e, k=mon.get("key"): self._handle_remove_foe(k))

                cur_item = mon.get("item") or ""
                item_frame = tk.Frame(top_row, bg="#1d122f")
                item_frame.pack(side="right", padx=6)
                tk.Label(item_frame, text="Item:", fg="#8B949E", bg="#1d122f", font=("Consolas", 8)).pack(side="left")
                item_ent = tk.Entry(item_frame, bg="#0d1117", fg="#FFD700", insertbackground="#FFF", font=("Consolas", 8), width=14, bd=1, relief="solid")
                item_ent.pack(side="left", padx=2)
                if cur_item:
                    item_ent.insert(0, cur_item)
                item_ent.bind("<Return>", lambda e, k=mon.get("key"), ent=item_ent: self._handle_set_item("their", k, ent.get(), ent))
                item_ent.bind("<FocusOut>", lambda e, k=mon.get("key"), ent=item_ent: self._handle_set_item("their", k, ent.get(), ent))

                mvs = mon.get("moves") or []
                if mvs:
                    bot_row = tk.Frame(card, bg="#1d122f")
                    bot_row.pack(fill="x", padx=16, pady=(0, 2))
                    tk.Label(bot_row, text="Revealed: " + ", ".join(mvs), fg="#FFC078", bg="#1d122f", font=("Consolas", 8)).pack(anchor="w")

                scout_threats = mon.get("scout_threats") or []
                if scout_threats:
                    scout_row = tk.Frame(card, bg="#1d122f")
                    scout_row.pack(fill="x", padx=16, pady=(0, 2))
                    tk.Label(scout_row, text="Scout Threats:", fg="#8B949E", bg="#1d122f", font=("Consolas", 8, "bold")).pack(side="left")
                    for st in scout_threats:
                        warn = " ⚠️" if st.get("is_threat") else ""
                        s_fg = "#FF6B6B" if st.get("is_threat") else "#E3B341"
                        tk.Label(
                            scout_row, text=f"{st['name']} ({st['pct']}%){warn}",
                            fg=s_fg, bg="#0e0a1b", font=("Consolas", 8), bd=1, relief="solid", padx=3,
                        ).pack(side="left", padx=2)
            else:
                empty_card = tk.Frame(self.team_scroll_frame, bg="#0e0a1b", bd=1, relief="flat")
                empty_card.pack(fill="x", padx=4, pady=1)
                tk.Label(
                    empty_card, text=f"  Slot {slot_num}: [ ? UNKNOWN ]",
                    fg="#484F58", bg="#0e0a1b", font=("Consolas", 8, "italic"),
                ).pack(anchor="w", padx=4, pady=2)

    def _on_user_edited(self, e=None):
        if e and e.keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R"):
            return
        self._is_user_edited = True
        self.tab_data.config(text="✏️ RAW DATA [EDITED]", fg="#FF9F43")

    def _reload_data(self):
        """Discards manual edits and re-fetches latest state from game OCR."""
        self._is_user_edited = False
        self.tab_data.config(text="✏️ RAW DATA", fg="#8B949E")
        if self.on_reload_state:
            latest = self.on_reload_state()
            if latest:
                self.set_state_data(latest, force=True)

    def set_state_data(self, text, force=False):
        """Update the battle data editor with latest state if user isn't actively editing."""
        if not text:
            return
        if self._is_user_edited and not force:
            return
        if text == getattr(self, "_last_state_data", None) and not force:
            return

        def _update():
            if not self._is_user_edited or force:
                # Save cursor position if possible
                try:
                    pos = self.data_editor.index("insert")
                except Exception:
                    pos = "1.0"
                self.data_editor.delete("1.0", "end")
                self.data_editor.insert("1.0", text)
                self._last_state_data = text
                try:
                    self.data_editor.mark_set("insert", pos)
                except Exception:
                    pass

        if threading.current_thread() is threading.main_thread():
            _update()
        else:
            self.root.after(0, _update)

    def get_state_data(self):
        """Return the current text from the battle data editor."""
        return self.data_editor.get("1.0", "end-1c").strip()

    def _handle_send_to_ai(self):
        """Sends the current (edited or scanned) battle data to Gemini."""
        text = self.get_state_data()
        self.show_tab("advice")
        if self.on_send_to_ai:
            self.on_send_to_ai(text)

    def _toggle_auto(self):
        if self.on_toggle_auto:
            is_auto = self.on_toggle_auto()
            self.auto_btn.config(
                text="⚡ AUTO: ON" if is_auto else "⚡ AUTO: OFF",
                fg="#7CFC00" if is_auto else "#8B949E",
            )

    def _toggle_foe_input(self):
        self.show_tab("team")

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def _resize_start(self, e):
        self._rw = self.root.winfo_width()
        self._rh = self.root.winfo_height()
        self._rx, self._ry = e.x_root, e.y_root

    def _resize_move(self, e):
        nw = max(MIN_W, self._rw + e.x_root - self._rx)
        nh = max(MIN_H, self._rh + e.y_root - self._ry)
        self.root.geometry(f"{nw}x{nh}")

    def set_text(self, text, tag="ai"):
        """Update the body text (thread-safe via root.after)."""
        def _update():
            self.body.config(state="normal")
            self.body.delete("1.0", "end")
            current_section = None
            for raw_line in text.split("\n"):
                line = raw_line.strip()
                if not line:
                    self.body.insert("end", "\n")
                    continue
                u = line.upper()
                if "OPTION A" in u or u.startswith("▶ OPTION A"):
                    current_section = "option_a"
                    self.body.insert("end", "🛡️ " + line.lstrip("▶*# ") + "\n", "title_a")
                elif "OPTION B" in u or u.startswith("▶ OPTION B"):
                    current_section = "option_b"
                    self.body.insert("end", "⚔️ " + line.lstrip("▶*# ") + "\n", "title_b")
                elif any(u.startswith(h) for h in ("MATCH CONTEXT", "CONTEXT:", "SITUATION:")):
                    current_section = "context"
                    self.body.insert("end", "★ " + line.lstrip("★*# ") + "\n", "title_context")
                elif any(u.startswith(h) for h in ("WHAT TO DO", "WHAT:", "ACTION:", "ACTION")):
                    current_section = "action"
                    self.body.insert("end", "🎯 " + line.lstrip("🎯*# ") + "\n", "title")
                elif any(u.startswith(h) for h in ("WHY", "REASON:", "REASON")):
                    current_section = "why"
                    self.body.insert("end", "💡 " + line.lstrip("💡*# ") + "\n", "title")
                elif any(u.startswith(h) for h in ("PREDICT", "PREDICTION", "OPPONENT", "READ:")):
                    current_section = "predict"
                    self.body.insert("end", "🔮 " + line.lstrip("🔮*# ") + "\n", "title")
                elif any(u.startswith(h) for h in ("NEXT", "PLAN:", "FOLLOW-UP")):
                    current_section = "plan"
                    self.body.insert("end", "📋 " + line.lstrip("📋*# ") + "\n", "title")
                elif any(u.startswith(w) for w in ("USE ", "SWITCH", "DOUBLE", "STAY", "SACK", "BAIT", "TRAP", "FINISH", "PIVOT", "- USE", "- SWITCH")):
                    tag_to_use = "option_a" if current_section == "option_a" else ("option_b" if current_section == "option_b" else "action")
                    self.body.insert("end", line + "\n", tag_to_use)
                elif any(u.startswith(w) for w in ("WARN", "DANGER", "RISK", "CAUTION")):
                    self.body.insert("end", line + "\n", "warn")
                elif current_section == "option_a":
                    self.body.insert("end", line + "\n", "option_a")
                elif current_section == "option_b":
                    self.body.insert("end", line + "\n", "option_b")
                elif current_section == "context":
                    self.body.insert("end", line + "\n", "context")
                elif current_section == "action":
                    self.body.insert("end", line + "\n", "action")
                elif current_section == "predict":
                    self.body.insert("end", line + "\n", "predict")
                elif line.startswith(("---", "===", "***")):
                    continue
                else:
                    self.body.insert("end", line + "\n", tag)
            self.body.config(state="disabled")
        self.root.after(0, _update)

    def set_status(self, text, color="#8B949E"):
        try:
            if hasattr(self, "status_lbl") and self.status_lbl:
                self.status_lbl.config(text=text, fg=color)
        except Exception:
            pass

    def _tick(self):
        try:
            status = self.get_status()
            scan_msg = self.get_scan() if self.get_scan else ""
            if scan_msg and any(w in scan_msg for w in ("SCAN:", "reading", "COMPLETE", "open next", "stopped", "cleared")):
                self.status_lbl.config(text=scan_msg, fg="#FFD700")
            else:
                self.status_lbl.config(text=status, fg="#8B949E")

            if self.get_auto:
                is_auto = self.get_auto()
                self.auto_btn.config(
                    text="⚡ AUTO: ON" if is_auto else "⚡ AUTO: OFF",
                    fg="#7CFC00" if is_auto else "#8B949E",
                )
        except Exception:
            pass
        self.root.after(600, self._tick)

    def run(self):
        self.root.mainloop()
