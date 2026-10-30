"""THE ENGINE'S RENDERER ON THE GRAPHICS CARD: the page editor's own shaders (ui/shaders.js's WGSL), run here through
Dawn's WebGPU, for every picture of strokes the engine draws -- what the model is shown of a page, the host's drafts and
checks, the page pictures. paint.paint() comes here first and draws with render.c (the CPU renderer) only when the card
cannot be used.

Takes what render.c takes (paint.Flat: points and widths in the target's pixels, each stroke's kind and color, a
density per point) and draws by the same rules (render.c's note): a pen segment a capsule whose pixels are inked when
their CENTER is within r of it; a highlighter its rectangles and outer bevels, a per-channel MINIMUM; a shader's wash and
a grain stroke's pixels decided ONCE per stroke (each such stroke at its own depth, nearer than the last; a grain pixel
left uninked still claims its place, at alpha 0); in file order, runs of plain pens and of highlighters in one draw
each, a shader or grain stroke in a draw of its own.

THE FEEDING (_feed: each stroke's segments, radii, colors, densities, seeds and highlighter triangles) is written twice:
here, and in partOf() in ui/editor.html, which feeds the same shaders for the page editor. A change to one MUST be made
to the other.

ON DAWN: webgpu_dawn.dll, our own build (tools/build_dawn.py), through cffi over its own webgpu.h -- the WebGPU the page
editor draws with in WebView2 is Dawn too, so the shaders run as written and both sides draw alike. On the card Settings
chose (gpus.py): on Direct3D 12, else on Direct3D 11 in WebGPU's compatibility mode.

ONE THREAD owns the card's device: pictures are drawn there one at a time, so no more than one page's worth of the
card's memory is ever in use, and the device is destroyed at a job's end, the daemon paused, a decompose done
(release()) -- Direct3D gives back everything it held then. A job's start makes it (warm()), so its first picture does
not wait. A card that cannot be used (no WebGPU, a device that will not open, a shader the card refuses, a page past
its largest texture) is told once a session (failure()), and render.c draws instead.
"""
import math
import os
import queue
import re
import threading

import numpy as np

WASH_EPS = 0.35                    # render.c's: how far past its exact footprint the device paints a wash, target pixels
RF_PEN, RF_HIGHLIGHTER, RF_SHADER = 0, 1, 2
_KINDS = {"pen": RF_PEN, "highlighter": RF_HIGHLIGHTER, "shader": RF_SHADER}
_SHADERS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ui", "shaders.js")

_state = {"thread": None, "jobs": None, "failed": None, "told": False, "off": bool(os.environ.get("PAPERDAEMON_CPU_RENDER")),
          "cpu": False}
_start = threading.Lock()


def failure():
    """Why the card is not drawing (a sentence), or None. Asked once a session by whoever tells the user (taken())."""
    return _state["failed"]


def taken():
    """The failure, the first time it is asked for in this session; None after (and when there is none)."""
    if _state["failed"] and not _state["told"]:
        _state["told"] = True
        return _state["failed"]
    return None


# ---------------------------------------------------------------- the feeding (partOf in ui/editor.html, mirrored)

def _seeds(x, y):
    """render.c's stroke_seed for many strokes at once: from where each starts, in target pixels."""
    M = np.uint64(0xFFFFFFFF)

    def llround(v):
        return (np.floor(np.abs(v) + 0.5) * np.sign(v)).astype(np.int64)

    def mix(h):
        h = h & M
        h ^= h >> np.uint64(16); h = (h * np.uint64(0x7FEB352D)) & M
        h ^= h >> np.uint64(15); h = (h * np.uint64(0x846CA68B)) & M
        h ^= h >> np.uint64(16)
        return h
    a = llround(x * 16).astype(np.uint64) & M
    b = llround(y * 16).astype(np.uint64) & M
    return mix(((a * np.uint64(0x27D4EB2D)) & M) ^ mix(b)).astype(np.uint32)


# THE POINT RECORD (ui/shaders.js): x, y, the width (float32 each), the flags, the color -- 16 bytes, each point once
PT = np.dtype([("x", "<f4"), ("y", "<f4"), ("w", "<f4"), ("f", "u1"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
GR = np.dtype([("d", "<f4"), ("u", "<f4")])           # a grain stroke's point: its density, its length along the stroke
SEG, DOT, BEVEL, OTHER, KEPT = 1, 2, 4, 8, 128


def _feed(flat):
    """A page's strokes (paint.Flat) -> (the points, PT, one record each side of them; the grain strokes' points, GR, one
    after; the plan: [(kind, first point, count, grain, alpha, seed, first grain point)] in file order -- "pen" a run of
    plain pens, "own" one shader or grain stroke, "hl" a run of highlighters). The whole page at once, in flat arrays;
    the rules are render.c's, stroke by stroke (a highlighter's repeats and bevels by its own pass, rf_hl_marks)."""
    empty = (np.zeros(2, PT), np.zeros(1, GR), [])
    keep = np.asarray(flat.counts) > 0
    if not keep.any():
        return empty
    counts = np.asarray(flat.counts, np.int64)
    kinds = np.asarray(flat.kinds, np.int8)
    rgba = np.asarray(flat.rgba).reshape(-1, 4)
    if not keep.all():                                       # strokes of no points: nothing of theirs is in the run
        counts, kinds, rgba = counts[keep], kinds[keep], rgba[keep]
    nS = len(counts)
    xy = np.ascontiguousarray(np.asarray(flat.xy, np.float64).reshape(-1, 2))
    w = np.asarray(flat.w, np.float64)
    dens = np.asarray(flat.dens, np.float64)
    start = np.concatenate([[0], np.cumsum(counts)[:-1]])
    sid = np.repeat(np.arange(nS), counts)
    hl = kinds == RF_HIGHLIGHTER
    grain = (kinds == RF_PEN) & (np.minimum.reduceat(dens, start) < 1)
    own = grain | (kinds == RF_SHADER)
    alpha = np.where(kinds == RF_SHADER, rgba[:, 3] / 255.0, 1.0)

    # THE FLAGS: a pen's point a segment to the next unless it is its stroke's last, a dot when it is its stroke's only
    # one; a highlighter's by render.c's pass (its kept points, their segments and bevels)
    flags = np.zeros(len(xy), np.uint8)
    nxt = np.concatenate([sid[1:] == sid[:-1], [False]])
    pen = ~hl[sid]
    flags[pen & nxt] = SEG
    flags[start[~hl & (counts == 1)]] = DOT
    if hl.any():
        import ctypes
        from paperdaemon.pipeline.page.paint import _lib
        marks = np.zeros(len(xy), np.uint8)
        P = lambda a, t: a.ctypes.data_as(ctypes.POINTER(t))
        cnt_c, kd_c = np.ascontiguousarray(counts, np.int32), np.ascontiguousarray(kinds, np.int32)
        _lib().rf_hl_marks(P(xy, ctypes.c_double), P(cnt_c, ctypes.c_int32), P(kd_c, ctypes.c_int32), nS, P(marks, ctypes.c_uint8))
        hp = ~pen
        flags[hp] = marks[hp] & (SEG | BEVEL | OTHER)
        kept = pen | ((marks & KEPT) != 0)
    else:
        kept = np.ones(len(xy), bool)
    K = int(kept.sum())
    pts = np.zeros(K + 2, PT)                                 # one record each side: the point before the first, after the last
    ks = sid[kept]
    pts["x"][1:-1], pts["y"][1:-1] = xy[kept, 0], xy[kept, 1]
    pts["w"][1:-1], pts["f"][1:-1] = w[kept], flags[kept]
    c = np.clip(np.round(rgba[:, :3].astype(np.float64)), 0, 255).astype(np.uint8)
    pts["r"][1:-1], pts["g"][1:-1], pts["b"][1:-1] = c[ks, 0], c[ks, 1], c[ks, 2]
    n = np.bincount(ks, minlength=nS)                         # each stroke's points on the card
    first = np.concatenate([[0], np.cumsum(n)[:-1]]) + 1

    # THE GRAIN: a grain stroke's points' densities and lengths along it (render.c's g.u0, summed as it goes), and its seed
    gp = grain[sid]
    gcount = np.where(grain, counts, 0)
    gfirst = np.concatenate([[0], np.cumsum(gcount)[:-1]])
    gr = np.zeros(int(gcount.sum()) + 1, GR)
    if gp.any():
        gx, gs = xy[gp], sid[gp]
        step = np.concatenate([[0.0], np.hypot(np.diff(gx[:, 0]), np.diff(gx[:, 1]))])
        step[np.concatenate([[True], gs[1:] != gs[:-1]])] = 0.0
        run = np.cumsum(step)
        firsts = np.flatnonzero(np.concatenate([[True], gs[1:] != gs[:-1]]))
        gr["u"][:-1] = run - np.repeat(run[firsts], np.diff(np.concatenate([firsts, [len(gs)]])))
        gr["d"][:-1] = dens[gp]
    seeds = _seeds(xy[start, 0], xy[start, 1])

    # THE PLAN, in file order: runs of plain pens and of highlighters, each one draw; a shader or grain stroke a draw of
    # its own (found for the whole page at once; a stroke with no point on the card has no part in it)
    has = n > 0
    if not has.any():
        return pts, gr, []
    key = np.where(hl, 1, np.where(own, 2, 0))[has]
    idx = np.nonzero(has)[0]
    starts = np.nonzero(np.concatenate([[True], (key[1:] != key[:-1]) | (key[1:] == 2)]))[0]
    cnt = np.add.reduceat(n[has], starts)
    names = {0: "pen", 1: "hl", 2: "own"}
    s0 = idx[starts]
    plan = [[names[k], f, c_, g, a, sd, gf] for k, f, c_, g, a, sd, gf in zip(
        key[starts].tolist(), first[s0].tolist(), cnt.tolist(), grain[s0].tolist(), alpha[s0].tolist(),
        seeds[s0].tolist(), gfirst[s0].tolist())]
    return pts, gr, plan


# ---------------------------------------------------------------- the card

def _sources():
    """The shaders, as ui/shaders.js has them (WGSL: what the page editor runs in WebView2's WebGPU)."""
    text = open(_SHADERS, encoding="utf-8").read()
    return {m.group(1): m.group(2) for m in re.finditer(r"\b([A-Z_]+): `([^`]*)`", text)}


# DAWN: webgpu_dawn.dll, built by tools/build_dawn.py (pinned; Direct3D 12 and 11 only) into the dawn folder beside this
# file, which the app carries as it carries the rest of the pipeline's files, with its webgpu.h as plain C declarations
# (webgpu.cdef, read by cffi: every struct as that build lays it out) and its flag constants (webgpu.flags.json)
DAWN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dawn")
# THE CARD BY ITS LUID: Dawn's dawn::native::d3d::RequestAdapterOptionsLUID, a chained struct and then the LUID, chained
# on the adapter's options (the C++ struct's layout, declared in C)
_LUID = "typedef struct PDAdapterLUID { WGPUChainedStruct chain; uint32_t low; int32_t high; } PDAdapterLUID;"
_API = {}
DEPTHS = 65000                    # the strokes decided whole drawn before the depth is cleared and the pass begun again
TW = 4096                         # PIXELS' TW: the bytes of the canvas put up a texel each, this many to a row
# THE DECLARATIONS READ ONCE, AT BUILD TIME: cffi's out-of-line module of them (made_module(), which tools/build_dawn.py
# runs), beside the DLL. Without it cffi reads the declarations, and every type a call names the first time a process
# names it, with its C parser in Python -- about half a second of a fresh engine's first context and first picture
MODULE = "_dawn_cffi.py"


def _declarations():
    with open(os.path.join(DAWN_DIR, "webgpu.cdef"), encoding="utf-8") as f:
        return f.read() + "\n" + _LUID


def made_module():
    """cffi's out-of-line module of webgpu.cdef and _LUID, written into the dawn folder, marked with the declarations'
    digest (a module of other declarations is not used: _api()) -> its path"""
    import hashlib
    import cffi
    text = _declarations()
    b = cffi.FFI()
    b.cdef(text)
    b.set_source("_dawn_cffi", None)
    path = os.path.join(DAWN_DIR, MODULE)
    b.emit_python_code(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write("DECLARATIONS = %r\n" % hashlib.sha256(text.encode("utf-8")).hexdigest())
    return path


def _api():
    """cffi's view of Dawn -> (ffi, lib, flags), made once a process: the module made_module() wrote, when it is of these
    declarations; else the declarations read here"""
    if not _API:
        import hashlib
        import importlib.util
        import json
        text, ffi = _declarations(), None
        try:
            spec = importlib.util.spec_from_file_location("_dawn_cffi", os.path.join(DAWN_DIR, MODULE))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            if getattr(m, "DECLARATIONS", None) == hashlib.sha256(text.encode("utf-8")).hexdigest():
                ffi = m.ffi
        except (OSError, ImportError, SyntaxError):
            ffi = None
        if ffi is None:
            import cffi
            ffi = cffi.FFI()
            ffi.cdef(text)
        with open(os.path.join(DAWN_DIR, "webgpu.flags.json"), encoding="utf-8") as f:
            flags = json.load(f)
        _API.update(ffi=ffi, lib=ffi.dlopen(os.path.join(DAWN_DIR, "webgpu_dawn.dll")), flags=flags)
    return _API["ffi"], _API["lib"], _API["flags"]


class _Card:
    """The renderer on the card: the page editor's draws, call for call (ui/editor.html's GL), through Dawn on the card
    Settings chose (gpus.py) -- on Direct3D 12, else on Direct3D 11 in WebGPU's compatibility mode. What it makes on the
    card is KEPT from one picture to the next -- the point and grain buffers (grown when a page needs more), the canvas,
    its depth, the small picture and the buffer it is read back through (made again only for another size) -- so
    pictures one after another make nothing new; the device is destroyed on release(), and Direct3D gives back all it
    held."""

    def __init__(self):
        ffi, lib, F = _api()
        self.ffi, self.lib, self.F = ffi, lib, F
        self.errors, self.keep = [], []
        from paperdaemon import gpus, settings
        card = gpus.chosen(gpus.cards(), settings._get_path(settings.load(), "render.card") or "")
        if card is None:
            raise OSError("no graphics card here runs WebGPU")
        feat = ffi.new("WGPUInstanceFeatureName[1]", [lib.WGPUInstanceFeatureName_TimedWaitAny])
        self.instance = lib.wgpuCreateInstance(ffi.new("WGPUInstanceDescriptor *", {"requiredFeatureCount": 1, "requiredFeatures": feat}))
        if self.instance == ffi.NULL:
            raise OSError("Dawn would not start")
        luid = ffi.new("PDAdapterLUID *", {"chain": {"sType": lib.WGPUSType_RequestAdapterOptionsLUID},
                                           "low": card["luid"][1], "high": card["luid"][0]})
        d12 = card["d3d12"]
        opts = ffi.new("WGPURequestAdapterOptions *", {
            "nextInChain": ffi.cast("WGPUChainedStruct *", luid),
            "featureLevel": lib.WGPUFeatureLevel_Core if d12 else lib.WGPUFeatureLevel_Compatibility,
            "powerPreference": lib.WGPUPowerPreference_HighPerformance,
            "backendType": lib.WGPUBackendType_D3D12 if d12 else lib.WGPUBackendType_D3D11})
        got = {}

        @ffi.callback("void(WGPURequestAdapterStatus, WGPUAdapter, WGPUStringView, void*, void*)")
        def on_adapter(status, adapter, message, u1, u2):
            got.update(status=status, adapter=adapter, why=self.text(message))
        self.wait(lib.wgpuInstanceRequestAdapter(self.instance, opts, self.info("WGPURequestAdapterCallbackInfo", on_adapter)))
        if got.get("status") != lib.WGPURequestAdapterStatus_Success:
            raise OSError("WebGPU found no adapter on the card (%s)" % (got.get("why") or "no reason given"))
        self.adapter = got["adapter"]
        info = ffi.new("WGPUAdapterInfo *")
        lib.wgpuAdapterGetInfo(self.adapter, info)
        self.renderer = "Dawn %s, %s" % (self.text(info.description) or card["name"], "Direct3D 12" if d12 else "Direct3D 11")
        lib.wgpuAdapterInfoFreeMembers(info[0])
        # THE DEVICE: the vertex stage's storage buffers asked for (compatibility mode gives none unless asked; the
        # strokes' vertex shaders read three), every other limit left as it comes
        have = ffi.new("WGPULimits *")
        want = ffi.new("WGPULimits *")
        for name, field in ffi.typeof("WGPULimits").fields:
            if name != "nextInChain":
                setattr(want, name, 0xFFFFFFFF if field.type.cname == "uint32_t" else 2 ** 64 - 1)
        if not d12:                                           # compatibility mode's own limits, chained on the core ones
            hc = ffi.new("WGPUCompatibilityModeLimits *", {"chain": {"sType": lib.WGPUSType_CompatibilityModeLimits}})
            have.nextInChain = ffi.cast("WGPUChainedStruct *", hc)
            lib.wgpuAdapterGetLimits(self.adapter, have)
            if hc.maxStorageBuffersInVertexStage < 3:
                raise OSError("the card's WebGPU cannot read storage buffers in a vertex shader")
            wc = ffi.new("WGPUCompatibilityModeLimits *", {"chain": {"sType": lib.WGPUSType_CompatibilityModeLimits},
                                                           "maxStorageBuffersInVertexStage": hc.maxStorageBuffersInVertexStage,
                                                           "maxStorageTexturesInVertexStage": 0xFFFFFFFF,
                                                           "maxStorageBuffersInFragmentStage": 0xFFFFFFFF,
                                                           "maxStorageTexturesInFragmentStage": 0xFFFFFFFF})
            want.nextInChain = ffi.cast("WGPUChainedStruct *", wc)
            self.keep += [hc, wc]
        else:
            lib.wgpuAdapterGetLimits(self.adapter, have)
        self.most = want.maxTextureDimension2D = have.maxTextureDimension2D   # (asked for: the device's default is less,
                                                                               # and a page past it was refused there)

        @ffi.callback("void(WGPUDevice const *, WGPUErrorType, WGPUStringView, void*, void*)")
        def on_error(device, kind, message, u1, u2):
            self.errors.append(self.text(message) or "an error of type %d" % kind)

        @ffi.callback("void(WGPUDevice const *, WGPUDeviceLostReason, WGPUStringView, void*, void*)")
        def on_lost(device, reason, message, u1, u2):
            if reason != lib.WGPUDeviceLostReason_Destroyed:
                self.errors.append("the card was lost: " + (self.text(message) or str(reason)))
        self.keep += [on_adapter, on_error, on_lost]
        desc = ffi.new("WGPUDeviceDescriptor *", {
            "nextInChain": ffi.cast("WGPUChainedStruct *", self._cache(card)),
            "requiredLimits": want,
            "deviceLostCallbackInfo": {"mode": lib.WGPUCallbackMode_AllowSpontaneous, "callback": on_lost},
            "uncapturedErrorCallbackInfo": {"callback": on_error}})

        @ffi.callback("void(WGPURequestDeviceStatus, WGPUDevice, WGPUStringView, void*, void*)")
        def on_device(status, device, message, u1, u2):
            got.update(dstatus=status, device=device, why=self.text(message))
        self.keep.append(on_device)
        self.wait(lib.wgpuAdapterRequestDevice(self.adapter, desc, self.info("WGPURequestDeviceCallbackInfo", on_device)))
        if got.get("dstatus") != lib.WGPURequestDeviceStatus_Success:
            raise OSError("WebGPU would not open the card (%s)" % (got.get("why") or "no reason given"))
        self.device = got["device"]
        self.queue = lib.wgpuDeviceGetQueue(self.device)
        self._pipelines()
        self.pb = self.gb = self.ob = None
        self.pcap = self.gcap = self.ocap = 0
        self.g0 = self.g1 = None
        self.size = self.small_size = None
        self.tex = self.depth = self.small = self.read = self.packed = self.bytes = None
        self.gUnpack = self.gPack = None
        self.check()

    # THE SHADERS COMPILED ONCE, kept on disk (Dawn's cache, as the browser keeps the page editor's): a context made after
    # the first loads what the card's compiler made instead of compiling it again, which was most of a context's making.
    # Dawn asks for an entry twice, its size and then its bytes, and both must agree: the bytes read for the first are
    # what the second is given. A folder grown past CACHE_CAP is emptied (whatever is still used is made again)
    CACHE_CAP = 64 * 1024 * 1024

    def _cache(self, card):
        import hashlib
        from paperdaemon import paths
        ffi = self.ffi
        folder = paths.cache_dir("dawn")
        try:
            names = [os.path.join(folder, n) for n in os.listdir(folder)]
            if sum(os.path.getsize(p) for p in names) > self.CACHE_CAP:
                for p in names:
                    os.remove(p)
        except OSError:
            pass
        read = {}

        def path(ksize, key):
            return os.path.join(folder, hashlib.sha256(ffi.buffer(key, ksize)).hexdigest())

        @ffi.callback("size_t(size_t, uint8_t const *, size_t, uint8_t *, void*, void*)")
        def load(ksize, key, vsize, value, u1, u2):
            try:
                p = path(ksize, key)
                if value == ffi.NULL:                         # its size (0: not kept)
                    if not os.path.exists(p):
                        return 0
                    with open(p, "rb") as f:
                        read[p] = f.read()
                    return len(read[p])
                data = read.pop(p, b"")
                if len(data) > vsize:
                    return 0
                ffi.memmove(value, data, len(data))
                return len(data)
            except Exception:
                return 0

        @ffi.callback("void(size_t, uint8_t const *, size_t, uint8_t const *, void*, void*)")
        def store(ksize, key, vsize, value, u1, u2):
            try:
                paths.write_atomic(path(ksize, key), bytes(ffi.buffer(value, vsize)))
            except Exception:
                pass
        cache = ffi.new("WGPUDawnCacheDeviceDescriptor *", {
            "chain": {"sType": self.lib.WGPUSType_DawnCacheDeviceDescriptor},
            "isolationKey": self.sv("PaperDaemon %s %s" % (card["name"], "Direct3D 12" if card["d3d12"] else "Direct3D 11")),
            "dawnLoadCacheDataCallbackInfo": {"callback": load},
            "dawnStoreCacheDataCallbackInfo": {"callback": store}})
        self.keep += [load, store, cache]
        return cache

    # ---- the calls, in Dawn's terms
    def text(self, sv):
        if sv.data == self.ffi.NULL or sv.length == 0:
            return ""
        n = sv.length if sv.length != 2 ** 64 - 1 else len(self.ffi.string(sv.data))
        return bytes(self.ffi.buffer(sv.data, n)).decode("utf-8", "replace")

    def sv(self, s):
        b = self.ffi.new("char[]", s.encode())
        self.keep.append(b)
        return {"data": b, "length": len(b) - 1}

    def info(self, kind, cb):
        return self.ffi.new(kind + " *", {"mode": self.lib.WGPUCallbackMode_WaitAnyOnly, "callback": cb})[0]

    def wait(self, future):
        w = self.ffi.new("WGPUFutureWaitInfo *", {"future": future})
        while True:                                   # until it is done: a card that stops answering is a lost device
            st = self.lib.wgpuInstanceWaitAny(self.instance, 1, w, 1000000000)
            if st == self.lib.WGPUWaitStatus_Success and w.completed:
                return
            if st != self.lib.WGPUWaitStatus_TimedOut:
                raise OSError("Dawn could not wait on the card (status %d)" % st)

    def check(self):
        self.lib.wgpuInstanceProcessEvents(self.instance)
        if self.errors:
            raise OSError(self.errors[0][:300])

    def buffer(self, size, usage):
        return self.lib.wgpuDeviceCreateBuffer(self.device, self.ffi.new("WGPUBufferDescriptor *", {"usage": usage, "size": size}))

    def texture(self, w, h, fmt, usage):
        return self.lib.wgpuDeviceCreateTexture(self.device, self.ffi.new("WGPUTextureDescriptor *", {
            "usage": usage, "dimension": self.lib.WGPUTextureDimension_2D, "size": {"width": w, "height": h, "depthOrArrayLayers": 1},
            "format": fmt, "mipLevelCount": 1, "sampleCount": 1}))

    def _pipelines(self):
        ffi, lib, F = self.ffi, self.lib, self.F
        S = _sources()
        mods = {}
        for key in ("STROKES", "AREA", "PIXELS"):
            wgsl = ffi.new("WGPUShaderSourceWGSL *", {"chain": {"sType": lib.WGPUSType_ShaderSourceWGSL}, "code": self.sv(S[key])})
            self.keep.append(wgsl)
            mods[key] = lib.wgpuDeviceCreateShaderModule(self.device, ffi.new("WGPUShaderModuleDescriptor *",
                                                                             {"nextInChain": ffi.cast("WGPUChainedStruct *", wgsl)}))
        V, Fr = F["WGPUShaderStage_Vertex"], F["WGPUShaderStage_Fragment"]
        U, RO = lib.WGPUBufferBindingType_Uniform, lib.WGPUBufferBindingType_ReadOnlyStorage

        def layout(entries):
            arr = ffi.new("WGPUBindGroupLayoutEntry[]", entries)
            return lib.wgpuDeviceCreateBindGroupLayout(self.device, ffi.new("WGPUBindGroupLayoutDescriptor *", {"entryCount": len(entries), "entries": arr}))
        # 0: the view and the frame's table of strokes drawn on their own; 1: the records and the grain; the shrink's
        self.L0 = layout([{"binding": 0, "visibility": V | Fr, "buffer": {"type": U}}, {"binding": 1, "visibility": V, "buffer": {"type": RO}}])
        self.L1 = layout([{"binding": 0, "visibility": V, "buffer": {"type": RO}}, {"binding": 1, "visibility": V, "buffer": {"type": RO}}])
        self.LA = layout([{"binding": 0, "visibility": Fr, "texture": {"sampleType": lib.WGPUTextureSampleType_Float,
                                                                         "viewDimension": lib.WGPUTextureViewDimension_2D}},
                          {"binding": 1, "visibility": Fr, "buffer": {"type": U}}])

        def playout(*ls):
            arr = ffi.new("WGPUBindGroupLayout[]", list(ls))
            self.keep.append(arr)
            return lib.wgpuDeviceCreatePipelineLayout(self.device, ffi.new("WGPUPipelineLayoutDescriptor *", {"bindGroupLayoutCount": len(ls), "bindGroupLayouts": arr}))
        strokes, area = playout(self.L0, self.L1), playout(self.LA)
        RGBA, D16 = lib.WGPUTextureFormat_RGBA8Unorm, lib.WGPUTextureFormat_Depth16Unorm
        add, mn = lib.WGPUBlendOperation_Add, lib.WGPUBlendOperation_Min
        alpha = {"color": {"operation": add, "srcFactor": lib.WGPUBlendFactor_SrcAlpha, "dstFactor": lib.WGPUBlendFactor_OneMinusSrcAlpha},
                 "alpha": {"operation": add, "srcFactor": lib.WGPUBlendFactor_SrcAlpha, "dstFactor": lib.WGPUBlendFactor_OneMinusSrcAlpha}}
        least = {"color": {"operation": mn, "srcFactor": lib.WGPUBlendFactor_One, "dstFactor": lib.WGPUBlendFactor_One},
                 "alpha": {"operation": mn, "srcFactor": lib.WGPUBlendFactor_One, "dstFactor": lib.WGPUBlendFactor_One}}

        def pipe(layout_, mod, vs, fs, topo, blend=None, depth=None):
            target = {"format": RGBA, "writeMask": F["WGPUColorWriteMask_All"]}
            if blend:
                b = ffi.new("WGPUBlendState *", blend)
                self.keep.append(b)
                target["blend"] = b
            tg = ffi.new("WGPUColorTargetState[1]", [target])
            frag = ffi.new("WGPUFragmentState *", {"module": mod, "entryPoint": self.sv(fs), "targetCount": 1, "targets": tg})
            self.keep += [tg, frag]
            d = {"layout": layout_, "vertex": {"module": mod, "entryPoint": self.sv(vs)}, "primitive": {"topology": topo},
                 "multisample": {"count": 1, "mask": 0xFFFFFFFF}, "fragment": frag}
            if depth:
                ds = ffi.new("WGPUDepthStencilState *", {"format": D16, "depthWriteEnabled": depth[1], "depthCompare": depth[0]})
                self.keep.append(ds)
                d["depthStencil"] = ds
            return lib.wgpuDeviceCreateRenderPipeline(self.device, ffi.new("WGPURenderPipelineDescriptor *", d))
        strip, tri = lib.WGPUPrimitiveTopology_TriangleStrip, lib.WGPUPrimitiveTopology_TriangleList
        never = (lib.WGPUCompareFunction_Always, lib.WGPUOptionalBool_False)
        M = mods["STROKES"]
        # each twice: for a pass with the depth buffer (a page with a wash or a grain stroke) and for one without
        self.sets = [{"pen": pipe(strokes, M, "vsSeg", "fsSeg", strip, None, never if z else None),
                      "own": pipe(strokes, M, "vsSeg", "fsSeg", strip, alpha, (lib.WGPUCompareFunction_Less, lib.WGPUOptionalBool_True)) if z else None,
                      "hl": pipe(strokes, M, "vsHl", "fsHl", tri, least, never if z else None)} for z in (False, True)]
        self.pArea = pipe(area, mods["AREA"], "vsFull", "fsArea", tri)
        # the canvas's bytes laid on the working canvas, and the picture made packed into bytes, on the card (PIXELS):
        # each with the layout its shader asks for
        self.pUnpack = pipe(ffi.NULL, mods["PIXELS"], "vsFull", "fsUnpack", tri)
        self.cpPack = lib.wgpuDeviceCreateComputePipeline(self.device, ffi.new("WGPUComputePipelineDescriptor *", {
            "compute": {"module": mods["PIXELS"], "entryPoint": self.sv("pack")}}))
        self.LU = lib.wgpuRenderPipelineGetBindGroupLayout(self.pUnpack, 0)
        self.LK = lib.wgpuComputePipelineGetBindGroupLayout(self.cpPack, 0)
        self.pxU = self.buffer(16, F["WGPUBufferUsage_Uniform"] | F["WGPUBufferUsage_CopyDst"])
        self.viewBuf = self.buffer(48, F["WGPUBufferUsage_Uniform"] | F["WGPUBufferUsage_CopyDst"])
        self.areaU = self.buffer(16, F["WGPUBufferUsage_Uniform"] | F["WGPUBufferUsage_CopyDst"])
        self.idx = self.buffer(12, F["WGPUBufferUsage_Index"] | F["WGPUBufferUsage_CopyDst"])
        self.put(self.idx, np.array([0, 1, 2, 0, 2, 3], np.uint16))

    def put(self, buf, arr, at=0):
        a = np.ascontiguousarray(arr)
        self.lib.wgpuQueueWriteBuffer(self.queue, buf, at, self.ffi.from_buffer(a), a.nbytes)

    def group(self, layout, entries):
        arr = self.ffi.new("WGPUBindGroupEntry[]", entries)
        return self.lib.wgpuDeviceCreateBindGroup(self.device, self.ffi.new("WGPUBindGroupDescriptor *",
                                                                             {"layout": layout, "entryCount": len(entries), "entries": arr}))

    def _grow(self, name, cap, need, usage):
        """a buffer kept, made again larger when a page needs more -> grown?"""
        if need <= getattr(self, cap):
            return False
        old = getattr(self, name)
        if old is not None:
            self.lib.wgpuBufferDestroy(old)
            self.lib.wgpuBufferRelease(old)
        size = (int(need * 1.25) + 4096 + 15) // 16 * 16
        setattr(self, name, self.buffer(size, usage))
        setattr(self, cap, size)
        return True

    def _canvas(self, WW, HH, W, H, ss):
        lib, F = self.lib, self.F
        if self.size != (WW, HH):
            for t in (self.tex, self.depth):
                if t is not None:
                    lib.wgpuTextureDestroy(t)
                    lib.wgpuTextureRelease(t)
            self.tex = self.texture(WW, HH, lib.WGPUTextureFormat_RGBA8Unorm, F["WGPUTextureUsage_RenderAttachment"] |
                                    F["WGPUTextureUsage_TextureBinding"] | F["WGPUTextureUsage_CopyDst"] | F["WGPUTextureUsage_CopySrc"])
            self.texView = lib.wgpuTextureCreateView(self.tex, self.ffi.NULL)
            self.depth, self.size, self.gArea, self.gPack = None, (WW, HH), None, None
        if self.small_size != (W, H, ss):
            for t in (self.small, self.bytes):
                if t is not None:
                    lib.wgpuTextureDestroy(t)
                    lib.wgpuTextureRelease(t)
            self.small = None
            if ss > 1:
                self.small = self.texture(W, H, lib.WGPUTextureFormat_RGBA8Unorm, F["WGPUTextureUsage_RenderAttachment"] | F["WGPUTextureUsage_TextureBinding"])
                self.smallView = lib.wgpuTextureCreateView(self.small, self.ffi.NULL)
            for b in (self.read, self.packed):
                if b is not None:
                    lib.wgpuBufferDestroy(b)
                    lib.wgpuBufferRelease(b)
            # the canvas's bytes as they come, a byte a texel, TW across; the picture's, packed, and read back from there
            n = W * H * 3
            self.bytes = self.texture(TW, (n + TW - 1) // TW, lib.WGPUTextureFormat_R8Uint, F["WGPUTextureUsage_TextureBinding"] | F["WGPUTextureUsage_CopyDst"])
            self.bytesView = lib.wgpuTextureCreateView(self.bytes, self.ffi.NULL)
            self.words = (n + 3) // 4
            self.packed = self.buffer(self.words * 4, F["WGPUBufferUsage_Storage"] | F["WGPUBufferUsage_CopySrc"])
            self.read = self.buffer(self.words * 4, F["WGPUBufferUsage_CopyDst"] | F["WGPUBufferUsage_MapRead"])
            self.small_size, self.gArea, self.gUnpack, self.gPack = (W, H, ss), None, None, None

    def release(self):
        lib = self.lib
        try:
            lib.wgpuDeviceDestroy(self.device)
            lib.wgpuDeviceRelease(self.device)
            lib.wgpuAdapterRelease(self.adapter)
            lib.wgpuInstanceRelease(self.instance)
        finally:
            self.keep = []

    def draw(self, px, flat, ss):
        """px: the canvas, RGB uint8 (H, W, 3) -> the canvas with the strokes drawn, or None (too large)."""
        ffi, lib, F = self.ffi, self.lib, self.F
        H, W = px.shape[:2]
        WW, HH = W * ss, H * ss
        if WW > self.most or HH > self.most or (W * H * 3 + TW - 1) // TW > self.most:
            return None
        pts, gr, plan = _feed(flat)
        z = any(p[0] == "own" for p in plan)
        self._canvas(WW, HH, W, H, ss)
        if z and self.depth is None:                          # the depth only for a page that needs it
            self.depth = self.texture(WW, HH, lib.WGPUTextureFormat_Depth16Unorm, F["WGPUTextureUsage_RenderAttachment"])
            self.depthView = lib.wgpuTextureCreateView(self.depth, ffi.NULL)
        # what is under the ink: the canvas's bytes put up as they are (its whole rows of TW, then what is left), laid on
        # the working canvas on the card below, each pixel ss x ss (PIXELS' fsUnpack, as render.c copies it)
        data, n = px.reshape(-1), W * H * 3
        full = n // TW
        for y, at, w_, h_ in ((0, 0, TW, full), (full, full * TW, n - full * TW, 1)):
            if w_ and h_:
                lib.wgpuQueueWriteTexture(self.queue, ffi.new("WGPUTexelCopyTextureInfo *", {"texture": self.bytes, "origin": {"x": 0, "y": y, "z": 0},
                                                                                              "aspect": lib.WGPUTextureAspect_All}),
                                          ffi.from_buffer(data), n, ffi.new("WGPUTexelCopyBufferLayout *", {"offset": at, "bytesPerRow": TW, "rowsPerImage": h_}),
                                          ffi.new("WGPUExtent3D *", {"width": w_, "height": h_, "depthOrArrayLayers": 1}))
        self.put(self.pxU, np.array([W, H, ss, 0], np.uint32))
        if self.gUnpack is None:
            self.gUnpack = self.group(self.LU, [{"binding": 0, "buffer": self.pxU, "size": 16}, {"binding": 1, "textureView": self.bytesView}])
        ST = F["WGPUBufferUsage_Storage"] | F["WGPUBufferUsage_CopyDst"]
        grown = self._grow("pb", "pcap", pts.nbytes, ST) | self._grow("gb", "gcap", max(16, gr.nbytes), ST)
        nown = sum(1 for p in plan if p[0] == "own")
        grown_o = self._grow("ob", "ocap", 20 * (nown + 1), ST)
        if grown or self.g1 is None:
            self.g1 = self.group(self.L1, [{"binding": 0, "buffer": self.pb, "size": self.pcap}, {"binding": 1, "buffer": self.gb, "size": self.gcap}])
        if grown_o or self.g0 is None:
            self.g0 = self.group(self.L0, [{"binding": 0, "buffer": self.viewBuf, "size": 48}, {"binding": 1, "buffer": self.ob, "size": self.ocap}])
        self.put(self.pb, pts.view(np.uint8))
        self.put(self.gb, gr.view(np.uint8))
        self.put(self.viewBuf, np.array([WW, HH, 0, 0, ss, WASH_EPS, 0, 0, 0, 0, 0, 0], np.float32))   # (whole pixels 0)
        rows = np.zeros(nown + 1, np.dtype([("grain", "<u4"), ("gfirst", "<u4"), ("first", "<u4"), ("alpha", "<f4"), ("depth", "<f4")]))
        rows[0] = (0, 0, 0, 1.0, 0.0)                         # row 0: the pens' (no grain, alpha 1)
        enc = lib.wgpuDeviceCreateCommandEncoder(self.device, ffi.NULL)
        cu = ffi.new("WGPURenderPassColorAttachment[1]", [{"view": self.texView, "depthSlice": 0xFFFFFFFF,
                                                           "loadOp": lib.WGPULoadOp_Clear, "storeOp": lib.WGPUStoreOp_Store}])
        pu = lib.wgpuCommandEncoderBeginRenderPass(enc, ffi.new("WGPURenderPassDescriptor *", {"colorAttachmentCount": 1, "colorAttachments": cu}))
        lib.wgpuRenderPassEncoderSetPipeline(pu, self.pUnpack)
        lib.wgpuRenderPassEncoderSetBindGroup(pu, 0, self.gUnpack, 0, ffi.NULL)
        lib.wgpuRenderPassEncoderDraw(pu, 3, 1, 0, 0)
        lib.wgpuRenderPassEncoderEnd(pu)
        lib.wgpuRenderPassEncoderRelease(pu)
        color = ffi.new("WGPURenderPassColorAttachment[1]", [{"view": self.texView, "depthSlice": 0xFFFFFFFF,
                                                              "loadOp": lib.WGPULoadOp_Load, "storeOp": lib.WGPUStoreOp_Store}])
        dsa = ffi.new("WGPURenderPassDepthStencilAttachment *", {"view": self.depthView if z else ffi.NULL, "depthLoadOp": lib.WGPULoadOp_Clear,
                                                                 "depthStoreOp": lib.WGPUStoreOp_Discard, "depthClearValue": 1.0})
        rp = ffi.new("WGPURenderPassDescriptor *", {"colorAttachmentCount": 1, "colorAttachments": color,
                                                    "depthStencilAttachment": dsa if z else ffi.NULL})

        def begin():
            p = lib.wgpuCommandEncoderBeginRenderPass(enc, rp)
            lib.wgpuRenderPassEncoderSetBindGroup(p, 0, self.g0, 0, ffi.NULL)
            lib.wgpuRenderPassEncoderSetBindGroup(p, 1, self.g1, 0, ffi.NULL)
            lib.wgpuRenderPassEncoderSetIndexBuffer(p, self.idx, lib.WGPUIndexFormat_Uint16, 0, 12)
            return p
        P = self.sets[1 if z else 0]
        p, pipe, ref, row = begin(), None, 0, 0
        for kind, first, count, grain, alpha_, seed, gfirst in plan:
            if kind == "hl":                                  # a run of highlighters: a quad a point, indexed
                if pipe is not P["hl"]:
                    lib.wgpuRenderPassEncoderSetPipeline(p, P["hl"])
                    pipe = P["hl"]
                lib.wgpuRenderPassEncoderDrawIndexed(p, 6, count, 0, 0, first)
                continue
            if kind == "pen":                                 # a run of plain pens: row 0
                if pipe is not P["pen"]:
                    lib.wgpuRenderPassEncoderSetPipeline(p, P["pen"])
                    pipe = P["pen"]
                lib.wgpuRenderPassEncoderDraw(p, 4, count, 0, first)
                continue
            ref = ref % DEPTHS + 1                            # a wash or a grain stroke: its own row, nearer than the last
            if ref == 1 and row:
                lib.wgpuRenderPassEncoderEnd(p)
                lib.wgpuRenderPassEncoderRelease(p)
                p, pipe = begin(), None
            row += 1
            rows[row] = (1 if grain else 0, gfirst, first, float(alpha_), 1.0 - ref / 65535.0)
            if pipe is not P["own"]:
                lib.wgpuRenderPassEncoderSetPipeline(p, P["own"])
                pipe = P["own"]
            lib.wgpuRenderPassEncoderDraw(p, 4, count, row * 16, first)
        lib.wgpuRenderPassEncoderEnd(p)
        lib.wgpuRenderPassEncoderRelease(p)
        self.put(self.ob, rows.view(np.uint8))
        src = self.tex
        if ss > 1:                                            # each ss x ss block averaged down (AREA's fsArea, as render.c rounds)
            self.put(self.areaU, np.array([WW, W, H, W], np.int32))     # (g: WW is ss times W)
            if self.gArea is None:
                self.gArea = self.group(self.LA, [{"binding": 0, "textureView": self.texView}, {"binding": 1, "buffer": self.areaU, "size": 16}])
            ca = ffi.new("WGPURenderPassColorAttachment[1]", [{"view": self.smallView, "depthSlice": 0xFFFFFFFF,
                                                               "loadOp": lib.WGPULoadOp_Clear, "storeOp": lib.WGPUStoreOp_Store}])
            pa = lib.wgpuCommandEncoderBeginRenderPass(enc, ffi.new("WGPURenderPassDescriptor *", {"colorAttachmentCount": 1, "colorAttachments": ca}))
            lib.wgpuRenderPassEncoderSetPipeline(pa, self.pArea)
            lib.wgpuRenderPassEncoderSetBindGroup(pa, 0, self.gArea, 0, ffi.NULL)
            lib.wgpuRenderPassEncoderDraw(pa, 3, 1, 0, 0)
            lib.wgpuRenderPassEncoderEnd(pa)
            lib.wgpuRenderPassEncoderRelease(pa)
        # the picture read back three bytes a pixel, packed on the card (PIXELS' pack): the processor takes it as it is
        if self.gPack is None:
            self.gPack = self.group(self.LK, [{"binding": 0, "buffer": self.pxU, "size": 16},
                                              {"binding": 2, "textureView": self.smallView if ss > 1 else self.texView},
                                              {"binding": 3, "buffer": self.packed, "size": self.words * 4}])
        cp = lib.wgpuCommandEncoderBeginComputePass(enc, ffi.NULL)
        lib.wgpuComputePassEncoderSetPipeline(cp, self.cpPack)
        lib.wgpuComputePassEncoderSetBindGroup(cp, 0, self.gPack, 0, ffi.NULL)
        groups = (self.words + 63) // 64
        lib.wgpuComputePassEncoderDispatchWorkgroups(cp, min(groups, 65535), (groups + 65534) // 65535, 1)
        lib.wgpuComputePassEncoderEnd(cp)
        lib.wgpuComputePassEncoderRelease(cp)
        lib.wgpuCommandEncoderCopyBufferToBuffer(enc, self.packed, 0, self.read, 0, self.words * 4)
        cb = lib.wgpuCommandEncoderFinish(enc, ffi.NULL)
        lib.wgpuQueueSubmit(self.queue, 1, ffi.new("WGPUCommandBuffer[1]", [cb]))
        lib.wgpuCommandBufferRelease(cb)
        lib.wgpuCommandEncoderRelease(enc)
        got = {}

        @ffi.callback("void(WGPUMapAsyncStatus, WGPUStringView, void*, void*)")
        def on_map(status, message, u1, u2):
            got.update(status=status, why=self.text(message))
        self.wait(lib.wgpuBufferMapAsync(self.read, F["WGPUMapMode_Read"], 0, self.words * 4, self.info("WGPUBufferMapCallbackInfo", on_map)))
        if got.get("status") != lib.WGPUMapAsyncStatus_Success:
            self.check()
            raise OSError("the card's picture could not be read back (%s)" % got.get("why"))
        mem = ffi.buffer(lib.wgpuBufferGetConstMappedRange(self.read, 0, self.words * 4), self.words * 4)
        out = np.frombuffer(mem, np.uint8, count=n).reshape(H, W, 3).copy()
        lib.wgpuBufferUnmap(self.read)
        self.check()
        return out


def _worker(jobs):
    """THE CARD'S THREAD: the WebGPU device is used on this thread alone; pictures are drawn here one at a time, the
    device made when it is first needed and destroyed on release() -- Direct3D gives back all it held when it is."""
    card = None
    while True:
        job, done = jobs.get()
        if job == "release":
            if card is not None:
                try:
                    card.release()
                except Exception:
                    pass
            card = None
            done["event"].set()
            continue
        try:
            if card is None:
                card = _Card()
            if job != "warm":
                px, flat, ss = job
                done["out"] = card.draw(px, flat, ss)
        except Exception as ex:
            _state["failed"] = "The graphics card could not draw pages (%s); the processor is drawing them instead." % (
                str(ex).splitlines()[0][:200] if str(ex) else type(ex).__name__)
            done["out"] = None
            try:
                if card is not None:
                    card.release()
            except Exception:
                pass
            card = None
        finally:
            done["event"].set()


def _ask(job, wait=True):
    with _start:
        if _state["thread"] is None:
            _state["jobs"] = queue.Queue()
            th = threading.Thread(target=_worker, args=(_state["jobs"],), name="page-gpu", daemon=True)
            _state["thread"] = th
            th.start()
    done = {"event": threading.Event(), "out": None}
    _state["jobs"].put((job, done))
    if wait:
        done["event"].wait()
    return done["out"]


def processor(on):
    """The job's lineup draws its pages on the processor (its "render" setting): until processor(False), no picture is
    drawn on the card (paint() says None, and render.c draws it), and nothing is made there."""
    _state["cpu"] = bool(on)


def paint(px, flat, ss=1):
    """A page's strokes (paint.Flat) drawn over px (RGB uint8, H x W x 3) on the card -> the new pixels, or None when the
    card is not drawing (the caller draws with render.c)."""
    if _state["off"] or _state["failed"] or _state["cpu"]:
        return None
    return _ask((px, flat, int(ss)))


def warm():
    """A job is starting: the card's context made now, alongside it, so its first picture does not wait for it."""
    if _state["off"] or _state["failed"] or _state["cpu"]:
        return
    _ask("warm", wait=False)


def release():
    """Let go of the card: the context destroyed, and everything it held on the card is the system's again (a job done,
    the daemon paused, a decompose finished). It is made again at the next picture."""
    if _state["thread"] is not None:
        _ask("release")
