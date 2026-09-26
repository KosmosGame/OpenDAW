import os
import tkinter as tk
from .shared import APP_NAME
from .app import DawApp
def _configure_windows_window(root):
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenDAW.OpenDAW")
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
                )
                break
            except Exception:
                pass
    except Exception:
        pass
def main():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenDAW.OpenDAW")
    except Exception:
        pass
    root = tk.Tk()
    icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "opendaw_icon.ico")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except tk.TclError:
            pass
    _configure_windows_window(root)
    app = DawApp(root)
    root.mainloop()
if __name__ == "__main__":
    main()
