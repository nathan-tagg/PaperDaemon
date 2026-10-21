"""THE ENGINE'S RENDERER ON THE GRAPHICS CARD: the page editor's own shaders (ui/shaders.js), run here through
ANGLE (OpenGL ES 3 on Direct3D 11), for every picture of strokes the engine draws -- what the model is shown of a page, the
host's drafts and checks, the page pictures. paint.paint() comes here first and draws with render.c (the CPU renderer)
only when the card cannot be used.

Takes what render.c takes (paint.Flat: points and widths in the target's pixels, each stroke's kind and color, a
density per point) and draws by the same rules (render.c's note): a pen segment a capsule whose pixels are inked when
their CENTER is within r of it; a highlighter its rectangles and outer bevels, a per-channel MINIMUM; a shader's wash and
a grain stroke's pixels decided ONCE per stroke (the stencil holds which stroke last decided a pixel; a grain pixel left
uninked still claims its place, at alpha 0); in file order, runs of plain pens and of highlighters in one draw each, a
shader or grain stroke in a draw of its own.

THE FEEDING (_feed: each stroke's segments, radii, colors, densities, seeds and highlighter triangles) is written twice:
here, and in partOf() in ui/editor.html, which feeds the same shaders for the page editor. A change to one MUST be made
to the other.

ON ANGLE: OpenGL ES 3 on Direct3D 11 (libEGL.dll and libGLESv2.dll, our own build, tools/build_angle.py) -- the page
editor's own route to the card (WebView2 draws WebGL with ANGLE), so the shaders run as written and both sides draw
alike on every card; WARP, Windows' software Direct3D, when there is no card to use.

ONE THREAD owns the card's context: pictures are drawn there one at a time, so no more than one page's worth of the
card's memory is ever in use, and the context is destroyed at a job's end, the daemon paused, a decompose done
(release()) -- Direct3D gives back everything it held then (measured: to 0 MB). A job's start makes it (warm()), so its
first picture does not wait. A card that
cannot be used (no OpenGL 3.3, a context that
will not start, a shader the driver refuses, a page past its largest texture) is told once a session (failure()), and
render.c draws instead.
"""
import ctypes
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
    """The shaders, as ui/shaders.js has them (GLSL ES 3.00: ANGLE takes them as the page editor's WebGL2 does)."""
    text = open(_SHADERS, encoding="utf-8").read()
    return {m.group(1): m.group(2) for m in re.finditer(r"\b([A-Z_]+): `([^`]*)`", text)}


# ANGLE: libEGL.dll and libGLESv2.dll, built by tools/build_angle.py (pinned; Direct3D 11 only) into the angle folder
# beside this file, which the app carries as it carries the rest of the pipeline's files
ANGLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "angle")


class _ES:
    """OpenGL ES 3 through ANGLE on Direct3D 11: a context of its own (an EGL display on the hardware's Direct3D 11, or
    on WARP, Windows' own software Direct3D, when there is no card to use), and the calls the renderer makes."""
    # the constants the renderer uses (GLES 3.0)
    ARRAY_BUFFER, STATIC_DRAW, DYNAMIC_DRAW = 0x8892, 0x88E4, 0x88E8
    FLOAT, UNSIGNED_BYTE, UNSIGNED_INT = 0x1406, 0x1401, 0x1405
    TEXTURE_2D, RGBA8, RGBA, TEXTURE0 = 0x0DE1, 0x8058, 0x1908, 0x84C0
    TEXTURE_MIN_FILTER, TEXTURE_MAG_FILTER, NEAREST = 0x2801, 0x2800, 0x2600
    FRAMEBUFFER, COLOR_ATTACHMENT0, STENCIL_ATTACHMENT, RENDERBUFFER, STENCIL_INDEX8 = 0x8D40, 0x8CE0, 0x8D20, 0x8D41, 0x8D48
    FRAMEBUFFER_COMPLETE = 0x8CD5
    BLEND, STENCIL_TEST, SCISSOR_TEST = 0x0BE2, 0x0B90, 0x0C11
    MIN, FUNC_ADD, SRC_ALPHA, ONE_MINUS_SRC_ALPHA = 0x8007, 0x8006, 0x0302, 0x0303
    NOTEQUAL, KEEP, REPLACE, STENCIL_BUFFER_BIT = 0x0205, 0x1E00, 0x1E01, 0x0400
    TRIANGLES, TRIANGLE_STRIP = 0x0004, 0x0005
    VERTEX_SHADER, FRAGMENT_SHADER, COMPILE_STATUS, LINK_STATUS, INFO_LOG_LENGTH = 0x8B31, 0x8B30, 0x8B81, 0x8B82, 0x8B84
    MAX_TEXTURE_SIZE, PACK_ALIGNMENT, UNPACK_ALIGNMENT, RENDERER = 0x0D33, 0x0D05, 0x0CF5, 0x1F01

    def __init__(self):
        if os.name != "nt":
            raise OSError("ANGLE's Direct3D 11 is Windows'")
        os.add_dll_directory(ANGLE_DIR)
        egl = ctypes.CDLL(os.path.join(ANGLE_DIR, "libEGL.dll"))
        gl = ctypes.CDLL(os.path.join(ANGLE_DIR, "libGLESv2.dll"))
        V, I, U = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint
        egl.eglGetProcAddress.restype, egl.eglGetProcAddress.argtypes = V, [ctypes.c_char_p]
        get_display = ctypes.CFUNCTYPE(V, U, V, ctypes.POINTER(I))(egl.eglGetProcAddress(b"eglGetPlatformDisplayEXT"))
        for f, r, a in (("eglInitialize", I, [V, ctypes.POINTER(I), ctypes.POINTER(I)]), ("eglTerminate", I, [V]),
                        ("eglChooseConfig", I, [V, ctypes.POINTER(I), ctypes.POINTER(V), I, ctypes.POINTER(I)]),
                        ("eglCreateContext", V, [V, V, V, ctypes.POINTER(I)]), ("eglDestroyContext", I, [V, V]),
                        ("eglCreatePbufferSurface", V, [V, V, ctypes.POINTER(I)]), ("eglDestroySurface", I, [V, V]),
                        ("eglMakeCurrent", I, [V, V, V, V]), ("eglBindAPI", I, [U]), ("eglGetError", I, [])):
            fn = getattr(egl, f); fn.restype, fn.argtypes = r, a
        self.egl = egl
        NONE, PLATFORM, TYPE, D3D11, DEVICE, WARP = 0x3038, 0x3202, 0x3203, 0x3208, 0x3209, 0x320B
        self.dpy = None
        for attrs in ((TYPE, D3D11, NONE), (TYPE, D3D11, DEVICE, WARP, NONE)):     # the card, else WARP
            dpy = get_display(PLATFORM, None, (I * len(attrs))(*attrs))
            if dpy and egl.eglInitialize(dpy, ctypes.byref(I()), ctypes.byref(I())):
                self.dpy = dpy
                break
        if not self.dpy:
            raise OSError("ANGLE could not open Direct3D 11 (EGL error 0x%x)" % egl.eglGetError())
        egl.eglBindAPI(0x30A0)                                                        # OpenGL ES
        cfg, n = V(), I()
        egl.eglChooseConfig(self.dpy, (I * 13)(0x3040, 0x0040, 0x3033, 0x0001, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8, NONE),
                            ctypes.byref(cfg), 1, ctypes.byref(n))
        self.ctx = egl.eglCreateContext(self.dpy, cfg, None, (I * 3)(0x3098, 3, NONE))              # ES 3
        self.surf = egl.eglCreatePbufferSurface(self.dpy, cfg, (I * 5)(0x3057, 1, 0x3056, 1, NONE))
        if not (n.value and self.ctx and self.surf and egl.eglMakeCurrent(self.dpy, self.surf, self.surf, self.ctx)):
            raise OSError("ANGLE could not make an OpenGL ES 3 context (EGL error 0x%x)" % egl.eglGetError())
        P, S, F = ctypes.POINTER, ctypes.c_ssize_t, ctypes.c_float
        sig = {
            "glCreateShader": (U, [U]), "glShaderSource": (None, [U, I, P(ctypes.c_char_p), P(I)]), "glCompileShader": (None, [U]),
            "glGetShaderiv": (None, [U, U, P(I)]), "glGetShaderInfoLog": (None, [U, I, P(I), ctypes.c_char_p]),
            "glCreateProgram": (U, []), "glAttachShader": (None, [U, U]), "glLinkProgram": (None, [U]),
            "glGetProgramiv": (None, [U, U, P(I)]), "glGetProgramInfoLog": (None, [U, I, P(I), ctypes.c_char_p]),
            "glUseProgram": (None, [U]), "glGetUniformLocation": (I, [U, ctypes.c_char_p]),
            "glUniform1i": (None, [I, I]), "glUniform1ui": (None, [I, U]), "glUniform1f": (None, [I, F]), "glUniform2f": (None, [I, F, F]),
            "glGenBuffers": (None, [I, P(U)]), "glDeleteBuffers": (None, [I, P(U)]), "glBindBuffer": (None, [U, U]),
            "glBufferData": (None, [U, S, V, U]), "glBufferSubData": (None, [U, S, S, V]),
            "glGenVertexArrays": (None, [I, P(U)]), "glDeleteVertexArrays": (None, [I, P(U)]), "glBindVertexArray": (None, [U]),
            "glEnableVertexAttribArray": (None, [U]), "glDisableVertexAttribArray": (None, [U]),
            "glVertexAttribPointer": (None, [U, I, U, ctypes.c_ubyte, I, V]), "glVertexAttribIPointer": (None, [U, I, U, I, V]),
            "glVertexAttribDivisor": (None, [U, U]), "glVertexAttrib2f": (None, [U, F, F]),
            "glGenTextures": (None, [I, P(U)]), "glDeleteTextures": (None, [I, P(U)]), "glBindTexture": (None, [U, U]),
            "glTexStorage2D": (None, [U, I, U, I, I]), "glTexSubImage2D": (None, [U, I, I, I, I, I, U, U, V]),
            "glTexParameteri": (None, [U, U, I]), "glActiveTexture": (None, [U]),
            "glGenFramebuffers": (None, [I, P(U)]), "glDeleteFramebuffers": (None, [I, P(U)]), "glBindFramebuffer": (None, [U, U]),
            "glFramebufferTexture2D": (None, [U, U, U, U, I]), "glCheckFramebufferStatus": (U, [U]),
            "glGenRenderbuffers": (None, [I, P(U)]), "glDeleteRenderbuffers": (None, [I, P(U)]), "glBindRenderbuffer": (None, [U, U]),
            "glRenderbufferStorage": (None, [U, U, I, I]), "glFramebufferRenderbuffer": (None, [U, U, U, U]),
            "glViewport": (None, [I, I, I, I]), "glEnable": (None, [U]), "glDisable": (None, [U]),
            "glBlendEquation": (None, [U]), "glBlendFunc": (None, [U, U]), "glStencilFunc": (None, [U, I, U]),
            "glStencilOp": (None, [U, U, U]), "glClearStencil": (None, [I]), "glClear": (None, [U]),
            "glDrawArrays": (None, [U, I, I]), "glDrawArraysInstanced": (None, [U, I, I, I]),
            "glReadPixels": (None, [I, I, I, I, U, U, V]), "glPixelStorei": (None, [U, I]), "glFinish": (None, []),
            "glGetIntegerv": (None, [U, P(I)]), "glGetString": (ctypes.c_char_p, [U]), "glGetError": (U, []),
        }
        for name, (r, a) in sig.items():
            fn = getattr(gl, name); fn.restype, fn.argtypes = r, a
            setattr(self, name[2].lower() + name[3:], fn)

    def gen(self, kind):
        n = ctypes.c_uint(0)
        getattr(self, "gen" + kind)(1, ctypes.byref(n))
        return n.value

    def delete(self, kind, n):
        if n:
            getattr(self, "delete" + kind)(1, ctypes.byref(ctypes.c_uint(n)))

    def program(self, vs, fs):
        p = self.createProgram()
        for kind, src in ((self.VERTEX_SHADER, vs), (self.FRAGMENT_SHADER, fs)):
            sh = self.createShader(kind)
            b = ctypes.c_char_p(src.encode())
            self.shaderSource(sh, 1, ctypes.byref(b), None)
            self.compileShader(sh)
            ok = ctypes.c_int(0); self.getShaderiv(sh, self.COMPILE_STATUS, ctypes.byref(ok))
            if not ok.value:
                log = ctypes.create_string_buffer(4096); self.getShaderInfoLog(sh, 4096, None, log)
                raise OSError("a shader did not compile: " + log.value.decode(errors="replace")[:300])
            self.attachShader(p, sh)
        self.linkProgram(p)
        ok = ctypes.c_int(0); self.getProgramiv(p, self.LINK_STATUS, ctypes.byref(ok))
        if not ok.value:
            log = ctypes.create_string_buffer(4096); self.getProgramInfoLog(p, 4096, None, log)
            raise OSError("the shaders did not link: " + log.value.decode(errors="replace")[:300])
        return p

    def release(self):
        e = self.egl
        e.eglMakeCurrent(self.dpy, None, None, None)
        e.eglDestroySurface(self.dpy, self.surf); e.eglDestroyContext(self.dpy, self.ctx); e.eglTerminate(self.dpy)


class _Card:
    """The renderer on the card: the page editor's draws, call for call (ui/editor.html's GL), on ANGLE. What it makes on
    the card is KEPT from one picture to the next -- the point and grain buffers (grown when a page needs more), the
    canvas, its stencil and the small picture (made again only for another size) -- so pictures one after another make
    nothing new: the driver keeps what a process freed, and making and freeing them a picture at a time piled up."""

    def __init__(self):
        g = self.g = _ES()
        S = _sources()
        self.seg = g.program(S["VS_SEG"], S["FS_SEG"])
        self.tri = g.program(S["VS_HL"], S["FS_TRI"])
        self.down = g.program(S["VS_FULL"], S["FS_DOWN"])
        U = lambda p, n: g.getUniformLocation(p, n.encode())
        self.uSeg = {n: U(self.seg, n) for n in ("size", "k", "off", "grainOn", "alpha", "seed")}
        self.uTri = {n: U(self.tri, n) for n in ("size", "k", "off", "eps")}
        self.uDown = {n: U(self.down, n) for n in ("tex", "ss", "h")}
        most = ctypes.c_int(0); g.getIntegerv(g.MAX_TEXTURE_SIZE, ctypes.byref(most)); self.most = most.value
        self.renderer = (g.getString(g.RENDERER) or b"").decode(errors="replace")
        self.quad = g.gen("Buffers"); g.bindBuffer(g.ARRAY_BUFFER, self.quad)
        q = np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32)
        g.bufferData(g.ARRAY_BUFFER, q.nbytes, q.ctypes.data, g.STATIC_DRAW)
        self.segVao, self.hlVao, self.fullVao = g.gen("VertexArrays"), g.gen("VertexArrays"), g.gen("VertexArrays")
        g.bindVertexArray(self.segVao)
        g.bindBuffer(g.ARRAY_BUFFER, self.quad); g.enableVertexAttribArray(0); g.vertexAttribPointer(0, 2, g.FLOAT, 0, 0, None)
        for i in (1, 2, 3, 5, 6):
            g.enableVertexAttribArray(i); g.vertexAttribDivisor(i, 1)
        for i in (7, 8):
            g.vertexAttribDivisor(i, 1)
        g.bindVertexArray(self.hlVao)
        for i in (1, 2, 3, 5, 6, 9, 10):
            g.enableVertexAttribArray(i); g.vertexAttribDivisor(i, 1)
        g.bindVertexArray(0)
        self.pb = g.gen("Buffers"); self.gb = g.gen("Buffers"); self.pcap = self.gcap = 0
        self.tex = self.fb = self.stencil = self.small = self.sfb = 0
        self.size = self.small_size = None
        self.has_stencil = False

    def release(self):
        self.g.release()

    def _upload(self, buf, cap_name, data):
        g = self.g
        g.bindBuffer(g.ARRAY_BUFFER, buf)
        if data.nbytes > getattr(self, cap_name):                   # grown, with room for the next page to be a little larger
            cap = int(data.nbytes * 1.25) + 4096
            g.bufferData(g.ARRAY_BUFFER, cap, None, g.STATIC_DRAW)   # STATIC: ANGLE keeps a DYNAMIC buffer twice over
            setattr(self, cap_name, cap)
        g.bufferSubData(g.ARRAY_BUFFER, 0, data.nbytes, data.ctypes.data)

    def _canvas(self, W, H, stencil):
        g = self.g
        if self.size != (W, H):
            g.delete("Textures", self.tex); g.delete("Framebuffers", self.fb); g.delete("Renderbuffers", self.stencil)
            self.tex = g.gen("Textures"); g.bindTexture(g.TEXTURE_2D, self.tex)
            g.texStorage2D(g.TEXTURE_2D, 1, g.RGBA8, W, H)
            g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MIN_FILTER, g.NEAREST); g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MAG_FILTER, g.NEAREST)
            self.fb = g.gen("Framebuffers"); g.bindFramebuffer(g.FRAMEBUFFER, self.fb)
            g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, self.tex, 0)
            self.stencil, self.has_stencil, self.size = 0, False, (W, H)
        g.bindFramebuffer(g.FRAMEBUFFER, self.fb)
        if stencil and not self.has_stencil:                        # the stencil only for a page that needs one
            self.stencil = g.gen("Renderbuffers"); g.bindRenderbuffer(g.RENDERBUFFER, self.stencil)
            g.renderbufferStorage(g.RENDERBUFFER, g.STENCIL_INDEX8, W, H)
            g.framebufferRenderbuffer(g.FRAMEBUFFER, g.STENCIL_ATTACHMENT, g.RENDERBUFFER, self.stencil)
            self.has_stencil = True
        if g.checkFramebufferStatus(g.FRAMEBUFFER) != g.FRAMEBUFFER_COMPLETE:
            raise OSError("the card would not take the page's canvas")

    def draw(self, px, flat, ss):
        """px: the canvas, RGB uint8 (H, W, 3) -> the canvas with the strokes drawn, or None (too large)."""
        g = self.g
        H, W = px.shape[:2]
        WW, HH = W * ss, H * ss
        if WW > self.most or HH > self.most:
            return None
        pts, gr, plan = _feed(flat)
        own = any(p[0] == "own" for p in plan)
        self._canvas(WW, HH, own)
        under = px if ss == 1 else np.repeat(np.repeat(px, ss, 0), ss, 1)   # each pixel ss x ss, as render.c copies it
        rgba = np.empty(under.shape[:2] + (4,), np.uint8)
        rgba[..., :3] = under; rgba[..., 3] = 255
        g.bindTexture(g.TEXTURE_2D, self.tex); g.pixelStorei(g.UNPACK_ALIGNMENT, 1)
        g.texSubImage2D(g.TEXTURE_2D, 0, 0, 0, WW, HH, g.RGBA, g.UNSIGNED_BYTE, rgba.ctypes.data)
        g.viewport(0, 0, WW, HH)
        if self.has_stencil:
            g.clearStencil(0); g.clear(g.STENCIL_BUFFER_BIT)
        self._upload(self.pb, "pcap", pts)
        self._upload(self.gb, "gcap", gr)
        for prog, u in ((self.seg, self.uSeg), (self.tri, self.uTri)):
            g.useProgram(prog); g.uniform2f(u["size"], WW, HH); g.uniform1f(u["k"], ss); g.uniform2f(u["off"], 0.0, 0.0)
        g.useProgram(self.tri); g.uniform1f(self.uTri["eps"], WASH_EPS)
        S, Gs = PT.itemsize, GR.itemsize

        def points(o):                                    # this point (a) and the next (b), from the one buffer
            g.bindBuffer(g.ARRAY_BUFFER, self.pb)
            g.vertexAttribPointer(1, 2, g.FLOAT, 0, S, o); g.vertexAttribPointer(2, 1, g.FLOAT, 0, S, o + 8)
            g.vertexAttribIPointer(3, 4, g.UNSIGNED_BYTE, S, o + 12)                 # the flags and the color, one attribute
            g.vertexAttribPointer(5, 2, g.FLOAT, 0, S, o + S); g.vertexAttribPointer(6, 1, g.FLOAT, 0, S, o + S + 8)
        ref = 0
        for kind, first, count, grain, alpha, seed, gfirst in plan:
            o = first * S
            if kind == "hl":                              # a run of highlighters: nine vertices a point (VS_HL)
                g.useProgram(self.tri); g.bindVertexArray(self.hlVao); points(o)
                g.vertexAttribPointer(9, 2, g.FLOAT, 0, S, o - S); g.vertexAttribPointer(10, 1, g.FLOAT, 0, S, o - S + 8)
                g.disable(g.STENCIL_TEST); g.enable(g.BLEND); g.blendEquation(g.MIN)
                g.drawArraysInstanced(g.TRIANGLES, 0, 9, count)
                continue
            g.useProgram(self.seg); g.bindVertexArray(self.segVao); points(o)
            if grain:                                     # its densities and lengths along it
                g.bindBuffer(g.ARRAY_BUFFER, self.gb); g.enableVertexAttribArray(7); g.enableVertexAttribArray(8)
                g.vertexAttribPointer(7, 2, g.FLOAT, 0, Gs, gfirst * Gs); g.vertexAttribPointer(8, 2, g.FLOAT, 0, Gs, (gfirst + 1) * Gs)
            else:                                         # solid: density 1 everywhere
                g.disableVertexAttribArray(7); g.disableVertexAttribArray(8); g.vertexAttrib2f(7, 1.0, 0.0); g.vertexAttrib2f(8, 1.0, 0.0)
            if kind == "pen":
                g.disable(g.STENCIL_TEST); g.disable(g.BLEND)
                g.uniform1i(self.uSeg["grainOn"], 0); g.uniform1f(self.uSeg["alpha"], 1.0)
            else:
                ref = ref % 255 + 1
                if ref == 1:
                    g.clear(g.STENCIL_BUFFER_BIT)
                g.enable(g.STENCIL_TEST); g.stencilFunc(g.NOTEQUAL, ref, 0xFF); g.stencilOp(g.KEEP, g.KEEP, g.REPLACE)
                g.enable(g.BLEND); g.blendEquation(g.FUNC_ADD); g.blendFunc(g.SRC_ALPHA, g.ONE_MINUS_SRC_ALPHA)
                g.uniform1i(self.uSeg["grainOn"], 1 if grain else 0); g.uniform1f(self.uSeg["alpha"], float(alpha))
                g.uniform1ui(self.uSeg["seed"], int(seed))
            g.drawArraysInstanced(g.TRIANGLE_STRIP, 0, 4, count)
        g.bindVertexArray(0); g.disable(g.STENCIL_TEST); g.disable(g.BLEND)
        g.pixelStorei(g.PACK_ALIGNMENT, 1)
        if ss == 1:
            out = np.empty((HH, WW, 4), np.uint8)
            g.readPixels(0, 0, WW, HH, g.RGBA, g.UNSIGNED_BYTE, out.ctypes.data)
        else:                                             # each ss x ss block averaged down, as render.c rounds
            if self.small_size != (W, H):
                g.delete("Textures", self.small); g.delete("Framebuffers", self.sfb)
                self.small = g.gen("Textures"); g.bindTexture(g.TEXTURE_2D, self.small)
                g.texStorage2D(g.TEXTURE_2D, 1, g.RGBA8, W, H)
                self.sfb = g.gen("Framebuffers"); g.bindFramebuffer(g.FRAMEBUFFER, self.sfb)
                g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, self.small, 0)
                self.small_size = (W, H)
            g.bindFramebuffer(g.FRAMEBUFFER, self.sfb); g.viewport(0, 0, W, H)
            g.useProgram(self.down); g.activeTexture(g.TEXTURE0); g.bindTexture(g.TEXTURE_2D, self.tex)
            g.uniform1i(self.uDown["tex"], 0); g.uniform1i(self.uDown["ss"], ss); g.uniform1i(self.uDown["h"], H)
            g.bindVertexArray(self.fullVao); g.drawArrays(g.TRIANGLES, 0, 3); g.bindVertexArray(0)
            out = np.empty((H, W, 4), np.uint8)
            g.readPixels(0, 0, W, H, g.RGBA, g.UNSIGNED_BYTE, out.ctypes.data)
            out = out[::-1]
        err = g.getError()
        if err:
            raise OSError("the card reported GL error 0x%x" % err)
        return np.ascontiguousarray(out[..., :3])


def _worker(jobs):
    """THE CARD'S THREAD: the ANGLE context is current on this thread alone; pictures are drawn here one at a time, the
    context made when it is first needed and destroyed on release() -- Direct3D gives back all it held when it is."""
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
