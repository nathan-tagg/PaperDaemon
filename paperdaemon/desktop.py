"""The desktop window: a native shell (the OS's own web view, Edge WebView2 on Windows) around
PaperDaemon's local UI. No browser. The window is handed the pairing token in the URL fragment, which is
never sent to the server; the page keeps it in memory for its API calls."""
import webview


def run(port, token):
    webview.create_window("PaperDaemon", "http://127.0.0.1:%d/#pair=%s" % (port, token),
                          width=1160, height=780, min_size=(900, 620))
    webview.start()
