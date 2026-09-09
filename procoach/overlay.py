"""Always-on-top advice overlay: borderless, draggable, resizable, closable."""
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
    def __init__(self, pro_rect, on_tick):
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

        self.body = tk.Label(
            self.root, text="starting...", fg="#CCCCCC", bg="#0d1117",
            font=("Consolas", 10), anchor="nw", justify="left",
            wraplength=self._w - 16,
        )
        self.body.pack(fill="both", expand=True, padx=8, pady=(4, 18))

        # resize grip (bottom-right corner)
        grip = tk.Label(self.root, text=" ⛶ ", fg="#8B949E", bg="#0d1117",
                        font=("Consolas", 10), cursor="sizing")
        grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)

        # drag bindings
        self.header.bind("<Button-1>", self._drag_start)
        self.header.bind("<B1-Motion>", self._drag_move)
        # resize bindings
        for wdg in (grip,):
            wdg.bind("<Button-1>", self._resize_start)
            wdg.bind("<B1-Motion>", self._resize_move)

        self._on_tick = on_tick
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
        self.body.config(wraplength=nw - 16)

    def _tick(self):
        try:
            lines = self._on_tick()
            if lines is None:
                self.body.config(text="PROClient not found - open the game", fg="#FF6B6B")
            else:
                def rank(pair):
                    t = pair[1].upper()
                    if t.startswith(("SWITCH", "USE", "FINISH", "YOUR")):
                        return 0
                    if t.startswith(("EXPECT", "PIVOT")):
                        return 1
                    return 2
                lines = sorted(lines, key=rank)[:8]
                self.body.config(
                    text="\n".join(t for _, t in lines) or "waiting for battle...",
                    fg="#7CFC00" if lines and rank(lines[0]) == 0 else "#CCCCCC",
                )
        finally:
            self.root.after(600, self._tick)

    def run(self):
        self.root.mainloop()
