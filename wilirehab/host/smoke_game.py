import math, sys, time, tkinter as tk
sys.argv = ["brick_break", "--port", "COM99", "--face", "--face-rest-s", "3", "--log-dir", "sessions_smoke"]
from wilirehab import brick_break
holder = {}
orig_init = brick_break.BrickApp.__init__
def init(self, *a, **k):
    orig_init(self, *a, **k)
    holder["app"] = self
brick_break.BrickApp.__init__ = init

orig_main = tk.Tk.mainloop
def mainloop(self, n=0):
    t0 = time.monotonic()
    def inject():
        t = time.monotonic() - t0
        ms = int(t * 1000)
        x = 4 * ((ms // 20) % 3 - 1)                       # tiny sensor noise
        y = 170 * math.sin(2 * math.pi * 0.5 * t)          # about +-10 degrees of roll
        if 15.0 <= t < 15.5:
            x = 1500 if (ms // 20) % 2 else -1500          # a hard shake
        raw = lambda mg: (int(mg) // 4) << 6
        holder["app"].events.put(("acc", (ms // 20, ms, raw(x), raw(y), raw(1000)), "right_hand"))
        self.after(20, inject)
    self.attributes('-topmost', True); self.after(500, inject)
    self.after(16000, lambda: self.tk.call(self.protocol("WM_DELETE_WINDOW")))
    return orig_main(self, n)
tk.Tk.mainloop = mainloop
brick_break.main()
print("closed cleanly")

