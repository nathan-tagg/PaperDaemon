"""The machine's graphics cards, as Windows lists them (DXGI): each card's name, the memory of its own, whether it has
Direct3D 12 and Direct3D 11; and the card PaperDaemon draws with -- the one Settings names (render.card), else the
card with Direct3D 12 and the most memory of its own, else the Direct3D 11 card with the most. A card is named by
what it is, "vendor:device:which" (which: its place among identical cards), never by the number Windows gives it for
one session.

THE WINDOW'S WEBGPU. The page editor draws with WebGPU in the window's web view (WebView2, which is Chromium).
Chromium runs WebGPU on Direct3D 12 and keeps its Direct3D 11 backend switched off ("not fully implemented",
crbug.com/41479539), so on a card without Direct3D 12 the window is started with that backend switched on, in
WebGPU's compatibility mode (window_args): the editor draws on the card there too. On a machine with more than one
card the window is told which card to use, the one chosen here (Chromium on Windows does not choose by power).
"""
import ctypes
import os
import sys
import uuid

D3D11_ARGS = ["--enable-unsafe-webgpu", "--use-webgpu-adapter=d3d11", "--force-webgpu-compat"]
CPU_ARGS = ["--disable-gpu"]
OFF_SCREEN_ARGS = ["--disable-gpu-compositing"]


def _guid(s):
    u = uuid.UUID(s)

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]
    return GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))


class _Desc(ctypes.Structure):                       # DXGI_ADAPTER_DESC1
    _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", ctypes.c_uint), ("DeviceId", ctypes.c_uint),
                ("SubSysId", ctypes.c_uint), ("Revision", ctypes.c_uint), ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t), ("SharedSystemMemory", ctypes.c_size_t),
                ("LuidLow", ctypes.c_uint32), ("LuidHigh", ctypes.c_int32), ("Flags", ctypes.c_uint)]


def _method(obj, index, *argtypes):                  # a COM interface's method by its place in the table
    table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])


def cards():
    """[{"name", "vendor", "device", "memory" (bytes of its own), "luid": [high, low], "d3d12", "d3d11", "display"}, ...]:
    every card that is hardware (not Windows' software one), in DXGI's order (the first drives the main display);
    display: a screen is connected to it."""
    if sys.platform != "win32":
        return []
    try:
        dxgi = ctypes.WinDLL("dxgi")
    except OSError:
        return []
    try:
        d3d12 = ctypes.WinDLL("d3d12")
        d3d12.D3D12CreateDevice.restype = ctypes.c_long
        d3d12.D3D12CreateDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    except OSError:
        d3d12 = None
    try:
        d3d11 = ctypes.WinDLL("d3d11")
        d3d11.D3D11CreateDevice.restype = ctypes.c_long
        d3d11.D3D11CreateDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
                                            ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    except OSError:
        d3d11 = None
    dxgi.CreateDXGIFactory1.restype = ctypes.c_long
    dxgi.CreateDXGIFactory1.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    factory = ctypes.c_void_p()
    if dxgi.CreateDXGIFactory1(ctypes.byref(_guid("770aae78-f26f-4dba-a829-253c83d1b387")), ctypes.byref(factory)) < 0:
        return []
    iid12 = _guid("189819f1-1db6-4b57-be54-1821339b85f7")             # ID3D12Device
    levels = (ctypes.c_int * 2)(0xB100, 0xB000)                      # feature levels 11_1, 11_0
    out = []
    try:
        enum = _method(factory, 12, ctypes.c_uint, ctypes.c_void_p)   # IDXGIFactory1::EnumAdapters1
        i = 0
        while True:
            adapter = ctypes.c_void_p()
            if enum(factory, i, ctypes.byref(adapter)) < 0:           # DXGI_ERROR_NOT_FOUND: no more
                break
            i += 1
            try:
                d = _Desc()
                if _method(adapter, 10, ctypes.c_void_p)(adapter, ctypes.byref(d)) < 0 or d.Flags & 2:   # GetDesc1; software
                    continue
                # each asked whether it could make a device, none made (no device pointer given)
                has12 = bool(d3d12) and d3d12.D3D12CreateDevice(adapter, 0xB000, ctypes.byref(iid12), None) >= 0
                got = ctypes.c_int(0)
                has11 = bool(d3d11) and d3d11.D3D11CreateDevice(adapter, 0, None, 0, levels, 2, 7, None,
                                                                ctypes.byref(got), None) >= 0 and got.value >= 0xB000
                output = ctypes.c_void_p()                            # IDXGIAdapter::EnumOutputs: a screen on it?
                shows = _method(adapter, 7, ctypes.c_uint, ctypes.c_void_p)(adapter, 0, ctypes.byref(output)) >= 0
                if shows:
                    _method(output, 2)(output)
                out.append({"name": d.Description, "vendor": d.VendorId, "device": d.DeviceId,
                            "memory": int(d.DedicatedVideoMemory), "luid": [int(d.LuidHigh), int(d.LuidLow)],
                            "d3d12": has12, "d3d11": has11, "display": shows})
            finally:
                _method(adapter, 2)(adapter)                          # Release
    finally:
        _method(factory, 2)(factory)
    named(out)
    return out


def named(cs):
    """Each card's "id": vendor:device in hex, and which of the identical ones it is"""
    seen = {}
    for c in cs:
        k = "%04x:%04x" % (c["vendor"], c["device"])
        c["id"] = "%s:%d" % (k, seen.get(k, 0))
        seen[k] = seen.get(k, 0) + 1
    return cs


def chosen(cs=None, want=""):
    """The card PaperDaemon draws with: `want` (Settings' render.card) where the machine has it, else the Direct3D 12
    card with the most memory of its own, else the Direct3D 11 card with the most, else None (pages are drawn on the
    processor)"""
    cs = cards() if cs is None else cs
    for c in cs:
        if want and c.get("id") == want:
            return c
    for key in ("d3d12", "d3d11"):
        have = [c for c in cs if c[key]]
        if have:
            return max(have, key=lambda c: c["memory"])
    return None


def window_args(cs=None, want="", processor=False):
    """The arguments the window's web view starts with, as a list: the card to use when there is more than one, and
    WebGPU's Direct3D 11 backend when that card has no Direct3D 12. PAPERDAEMON_WEBGPU_D3D11 asks for the Direct3D 11
    backend whatever the card (checking that path on a machine that has Direct3D 12). With the Renderer on the
    processor, the web view's graphics card is switched off: it draws and composes on the processor and holds nothing
    on any card. On a card no screen is connected to, the web view composes the window on the processor: composed on
    the card, the window is shown through the card the screen is on, and that card is taken too (measured: 16 to 25 MB
    there); the page editor's WebGPU still runs on the card chosen, and nothing of PaperDaemon's goes on the other."""
    if processor:
        return list(CPU_ARGS)
    cs = cards() if cs is None else cs
    c = chosen(cs, want)
    args = []
    if c and len(cs) > 1:
        args.append("--use-adapter-luid=%d,%d" % (c["luid"][0], c["luid"][1]))
    if (c and not c["d3d12"]) or os.environ.get("PAPERDAEMON_WEBGPU_D3D11"):
        args += D3D11_ARGS
    if c and len(cs) > 1 and not c.get("display", True) and any(o.get("display") for o in cs if o is not c):
        args += OFF_SCREEN_ARGS
    return args


def window_for(s):
    """window_args for settings s: the Renderer (render.processor) and its card (render.card)"""
    from . import settings
    return window_args(want=settings._get_path(s, "render.card") or "",
                       processor=bool(settings._get_path(s, "render.processor")))
