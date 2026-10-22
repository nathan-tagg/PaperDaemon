"""A folder opened for the user, IN FRONT, over PaperDaemon's window.

The engine runs in the background, and Windows does not let a background process put a window in front: a folder
opened with os.startfile alone came up behind every other app. So the window in front when the user asked (theirs:
PaperDaemon's, they just clicked in it) is noted first; once Explorer's window for the folder is up, it is centered
over that window and brought to the front, the engine's thread joined to that window's input for the moment it takes
(AttachThreadInput: what lets a process that is not in front set what is). Not on Windows: the folder is opened as
the system opens it, where it opens.
"""
import os
import sys
import time

WAIT_STEPS = 40                    # looks for Explorer's window, a tenth of a second apart


def open_folder(path):
    """Open `path` in the file manager, in front, over the window that was in front. -> True when it was brought
    forward."""
    if sys.platform != "win32":
        import subprocess
        subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", path])
        return False
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    over = user32.GetForegroundWindow()
    os.startfile(path)
    name = os.path.basename(os.path.normpath(path)).lower()
    hwnd = None
    for _ in range(WAIT_STEPS):
        hwnd = _explorer_window(user32, name)
        if hwnd:
            break
        time.sleep(0.1)
    if not hwnd:
        return False
    rect = wintypes.RECT()
    if over and user32.GetWindowRect(over, ctypes.byref(rect)):
        # centered over PaperDaemon's window, three quarters of its size (at least a usable size)
        w = max(640, int((rect.right - rect.left) * 0.75))
        h = max(420, int((rect.bottom - rect.top) * 0.75))
        x = rect.left + ((rect.right - rect.left) - w) // 2
        y = rect.top + ((rect.bottom - rect.top) - h) // 2
        user32.ShowWindow(hwnd, 9)                                  # SW_RESTORE: not minimized or maximized
        user32.MoveWindow(hwnd, x, y, w, h, True)
    fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    joined = fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True)
    try:
        user32.BringWindowToTop(hwnd)
        ok = bool(user32.SetForegroundWindow(hwnd))
    finally:
        if joined:
            user32.AttachThreadInput(me, fg_thread, False)
    return ok


def _explorer_window(user32, name):
    """The visible Explorer window titled with the folder's name, or None."""
    import ctypes
    from ctypes import wintypes
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _l):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == "CabinetWClass" and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            if title.value.lower() == name or title.value.lower().startswith(name + " "):
                found.append(hwnd)
        return True
    user32.EnumWindows(each, 0)
    return found[0] if found else None
