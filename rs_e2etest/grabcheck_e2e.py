"""E2E check for make_docs_images.foreign_windows: a grab box covered by another
process's window is refused, one covered only by this process's windows is not.

Run from the plugin folder:  python rs_e2etest/grabcheck_e2e.py
Puts two small windows at screen position (60, 60) for ~3 s. Exit code 1 on a failure.

Ways it can fail end to end:
1. A foreign window over the box goes unreported (the docs pick up someone's desktop).
2. This process's own windows (backdrop, second Toplevel) are reported as foreign.
3. The check keeps reporting a window after it has closed.
"""

import os
import subprocess
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "rs_tests"))

from make_docs_images import foreign_windows    # noqa: E402

BOX = (60, 60, 360, 260)
FOREIGN = ("import tkinter as tk; r=tk.Tk(); r.title('grabcheck foreign'); "
           "r.geometry('200x120+120+100'); r.attributes('-topmost', True); "
           "r.after(4000, r.destroy); r.mainloop()")


def settle(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def main():
    results = []
    root = tk.Tk()
    root.geometry(f"{BOX[2] - BOX[0]}x{BOX[3] - BOX[1]}+{BOX[0]}+{BOX[1]}")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    own = tk.Toplevel(root)
    own.geometry("120x80+100+100")
    own.attributes("-topmost", True)
    settle(root, 0.5)
    results.append(("2 own windows only: nothing foreign", foreign_windows(*BOX) == []))

    child = subprocess.Popen([sys.executable, "-c", FOREIGN])
    settle(root, 1.5)
    found = foreign_windows(*BOX)
    results.append(("1 foreign window over the box: reported",
                    any("grabcheck foreign" in title for _, _, title in found)))
    child.wait(timeout=10)
    settle(root, 0.5)
    results.append(("3 after it closed: nothing foreign", foreign_windows(*BOX) == []))
    root.destroy()

    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
