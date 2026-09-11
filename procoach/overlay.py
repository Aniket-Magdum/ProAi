"""Always-on-top advice overlay: borderless, draggable, resizable, closable.
Per-line colors via a tk.Text widget (category -> color)."""
import tkinter as tk

COLORS = {
    "use": "#7CFC00",
    "avoid": "#FF9F43",
    "speed": "#8AB4FF",
    "beware": "#FF6B6B",
    "info": "#CCCCCC",
}

MIN_W, MIN_H = 240, 150


class Overlay:
    def __init__(self, pro_rect, on_tick, on_mode=None, on_scan=None, on_clear=None,
                 get_mode=None, get_scan=None):
        self.root = tk.Tk()
        self.root.title("PRO Instant Coach")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.9)
        self.root.configure(bg="#0d1117")

        x1, y1, x2, y2 = pro_rect
        self._w, self._h = 330, 240
        px = min(x2 + 12, self.root.winfo_screenwidth() - self._w - 8)
        py = max(y1, 40)
        self.root.geometry(f"{self._w}x{self._h}+{px}+{py}")

        # header doubles as the drag handle
        bar = tk.Frame(self.root, bg="#161b22")
        bar.pack(fill="x")
        self.header = tk.Label(
            bar, text=" PRO INSTANT COACH", fg="#FFD700", bg="#161b22",
            font=("Consolas", 9, "bold"), anchor="w", cursor="fleur",
        )
        self.header.pack(side="left", fill="x", expand=True)
        close = tk.Label(bar, text=" ✕ ", fg="#FF6B6B", bg="#161b22",
                         font=("Consolas", 10, "bold"), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.root.destroy())

        # --- callbacks ---
        self._on_tick = on_tick
        self.on_mode = on_mode
        self.on_scan = on_scan
        self.on_clear = on_clear
        self.get_mode = get_mode or (lambda: "random")
        self.get_scan = get_scan or (lambda: "")

        # control bar: mode toggle + team scanner (PvP mode)
        # MUST be packed before the body so tkinter reserves space at bottom
        ctrl = tk.Frame(self.root, bg="#161b22")
        ctrl.pack(side="bottom", fill="x")
        self.mode_btn = tk.Label(
            ctrl, text="MODE: RANDOM", fg="#8AB4FF", bg="#161b22",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=6,
        )
        self.mode_btn.pack(side="left")
        self.mode_btn.bind("<Button-1>", lambda e: self.on_mode and self.on_mode())
        self.scan_btn = tk.Label(
            ctrl, text="SCAN TEAM", fg="#7CFC00", bg="#161b22",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=6,
        )
        self.scan_btn.pack(side="left")
        self.scan_btn.bind("<Button-1>", lambda e: self.on_scan and self.on_scan())
        self.clear_btn = tk.Label(
            ctrl, text="CLEAR", fg="#FF6B6B", bg="#161b22",
            font=("Consolas", 9, "bold"), cursor="hand2", padx=6,
        )
        self.clear_btn.pack(side="left")
        self.clear_btn.bind("<Button-1>", lambda e: self.on_clear and self.on_clear())
        self.scan_status = tk.Label(
            ctrl, text="", fg="#8B949E", bg="#161b22",
            font=("Consolas", 8), anchor="w",
        )
        self.scan_status.pack(side="left", fill="x", expand=True)

        # resize grip (bottom-right corner)
        grip = tk.Label(self.root, text=" ⛶ ", fg="#8B949E", bg="#0d1117",
                        font=("Consolas", 10), cursor="sizing")
        grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)

        # body text: packed LAST so it fills remaining space
        self.body = tk.Text(
            self.root, bg="#0d1117", fg="#CCCCCC", bd=0,
            highlightthickness=0, font=("Consolas", 10),
            state="disabled", wrap="word",
        )
        self.body.pack(fill="both", expand=True, padx=8, pady=(4, 4))
        for cat, col in COLORS.items():
            self.body.tag_configure(cat, foreground=col)

        self.header.bind("<Button-1>", self._drag_start)
        self.header.bind("<B1-Motion>", self._drag_move)
        grip.bind("<Button-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)

        self.root.after(600, self._tick)

    # --- drag ---
    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    # --- resize ---
    def _resize_start(self, e):
        self._rw, self._rh = self.root.winfo_width(), self.root.winfo_height()
        self._rx, self._ry = e.x_root, e.y_root

    def _resize_move(self, e):
        nw = max(MIN_W, self._rw + e.x_root - self._rx)
        nh = max(MIN_H, self._rh + e.y_root - self._ry)
        self._w = nw
        self.root.geometry(f"{nw}x{nh}")

    def _tick(self):
        try:
            try:
                self.mode_btn.config(text=f"MODE: {self.get_mode().upper()}")
                self.scan_status.config(text=self.get_scan())
            except Exception:
                pass
            lines = self._on_tick()
            if lines is None:
                text = [("PROClient not found - open the game", "beware")]
            else:
                def rank(pair):
                    t = pair[1].upper()
                    if t.startswith(("SWITCH", "USE", "FINISH", "YOUR")):
                        return 0
                    if t.startswith(("EXPECT", "PIVOT")):
                        return 1
                    return 2
                lines = sorted(lines, key=rank)[:8]
                text = [(t, cat) for cat, t in lines] or [("waiting for battle...", "info")]
            self.body.config(state="normal")
            self.body.delete("1.0", "end")
            for t, cat in text:
                self.body.insert("end", t + "\n", cat)
            self.body.config(state="disabled")
        finally:
            self.root.after(600, self._tick)

    def run(self):
        self.root.mainloop()
