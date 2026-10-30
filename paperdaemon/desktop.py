"""The desktop window: a native shell (the OS's own web view, Edge WebView2 on Windows) around
PaperDaemon's local UI. No browser. The window is handed the pairing token in the URL fragment, which is
never sent to the server; the page keeps it in memory for its API calls. Its web view is started for the
graphics card PaperDaemon draws with (gpus.window_args), as the packaged shell's is."""
import os

import webview

from . import gpus


def run(port, token):
    from . import settings
    args = gpus.window_args(want=settings._get_path(settings.load(), "render.card") or "")
    if args:
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = " ".join(args)
    webview.create_window("PaperDaemon", "http://127.0.0.1:%d/#pair=%s" % (port, token),
                          width=1160, height=780, min_size=(900, 620))
    webview.start()
