r"""Reuse of pure results inside one model run.

The model (rm_model.run) quantizes the same picture three times: the painter's first run, then the region budget's
two calls to rm_regions.engine_grid (the count, and the budgeted merge). Each is the same function of the same
inputs, so each is computed once and handed out as fresh copies after that:

  * quantize: rm_paint.quantize keyed by the picture's bytes, every argument, the painter's per-picture globals it
    reads (_SKIN_HUE_OFFSET, _DARK_FIELD, _WHITE_FLOOR, _UP; a call with _FLOW set is never reused) and the values of
    every tuned constant in rmb_params;
  * engine_grid: rm_regions.engine_grid keyed by (source path, w, h) and the same constants, restoring the painter
    globals exactly as engine_grid leaves them.

Every hit returns new mask images built from copies of the stored arrays, so no caller can change what another
caller sees. The cache lives for one run: `install` returns the function that removes it.
"""
import numpy as np


def _constants(K):
    return tuple((k, repr(v)) for k, v in sorted(vars(K).items()) if k.isupper() and not callable(v))


def _copy_masks(N, masks):
    return {k: N.img(np.array(N.view(m), np.uint8)) for k, m in masks.items()}


def install(P, RG, N, K):
    """Wrap rm_paint.quantize and rm_regions.engine_grid with the per-run cache. -> a function that restores them."""
    q_orig, g_orig = P.quantize, RG.engine_grid
    q_cache, g_cache = {}, {}

    def quantize(small, *args, **kw):
        if P._FLOW is not None:
            return q_orig(small, *args, **kw)
        data = small.tobytes()
        key = (small.mode, small.size, repr(args), repr(sorted(kw.items())), repr(P._SKIN_HUE_OFFSET), repr(P._DARK_FIELD),
               repr(P._WHITE_FLOOR), repr(P._UP), _constants(K))
        hit = q_cache.get(key)
        if hit is not None and hit[0] == data:
            masks, cover = hit[1], hit[2]
            return _copy_masks(N, masks), dict(cover)
        masks, cover = q_orig(small, *args, **kw)
        q_cache[key] = (data, _copy_masks(N, masks), dict(cover))
        return masks, cover

    def engine_grid(src, w, h):
        if not isinstance(src, str):
            return g_orig(src, w, h)
        key = (src, int(w), int(h), _constants(K))
        hit = g_cache.get(key)
        if hit is None:
            small, masks, ppg, grid = g_orig(src, w, h)
            g_cache[key] = (small.copy(), _copy_masks(N, masks), ppg, tuple(grid))
            return small, masks, ppg, grid
        small, masks, ppg, grid = hit
        # engine_grid leaves the painter's per-picture globals reset; so does a reuse
        P._SKIN_HUE_OFFSET, P._DARK_FIELD, P._FLOW, P._WHITE_FLOOR, P._UP = 0.0, False, None, None, 1.0
        return small.copy(), _copy_masks(N, masks), ppg, grid

    P.quantize, RG.engine_grid = quantize, engine_grid

    def remove():
        P.quantize, RG.engine_grid = q_orig, g_orig
        q_cache.clear()
        g_cache.clear()
    return remove


def install_rgb_view(P, Image):
    """The painter reads its grid picture back as a numpy array many times -- `np.asarray(small.convert("RGB"))`, once
    per dark mass among them -- and each read is a full copy of the picture plus a full byte encode. For the run,
    `small.convert("RGB")` (default arguments) on the picture the painter is working on returns one shared, frozen copy
    whose array interface is computed once: the same bytes, the same shape and type, so every array read from it is
    the array the copy would give. The picture is recognized by identity: the object handed to
    rm_paint.skin_cast_offset, which decompose (and rm_regions.engine_grid) call on it first thing.
    The frozen copy refuses writes (PIL's _ensure_mutable raises), and when the run ends both the picture and the
    frozen copy are read back and compared with the bytes taken at the start: a write by any other path fails the run
    instead of changing its output. -> a function that removes the hook (and runs that check)."""
    orig_convert, orig_skin = Image.Image.convert, P.skin_cast_offset
    frozen = {}

    class FrozenRGB(Image.Image):
        @property
        def __array_interface__(self):
            return self._rm_interface

        def _ensure_mutable(self):
            raise RuntimeError("the painter's shared RGB view cannot be written to")

    def skin_cast_offset(small):
        if getattr(small, "mode", None) == "RGB" and id(small) not in frozen:
            f = small.copy()
            data = small.tobytes()
            interface = Image.Image.__array_interface__.fget(f)
            f.__class__ = FrozenRGB
            f._rm_interface = interface
            frozen[id(small)] = (small, f, data)
        return orig_skin(small)

    def convert(self, mode=None, matrix=None, dither=None, palette=Image.Palette.WEB, colors=256):
        if mode == "RGB" and matrix is None and dither is None and palette == Image.Palette.WEB and colors == 256:
            hit = frozen.get(id(self))
            if hit is not None and hit[0] is self:
                return hit[1]
        return orig_convert(self, mode, matrix, dither, palette, colors)

    P.skin_cast_offset, Image.Image.convert = skin_cast_offset, convert

    def remove():
        P.skin_cast_offset, Image.Image.convert = orig_skin, orig_convert
        bad = [k for k, (small, f, data) in frozen.items()
               if small.tobytes() != data or Image.Image.tobytes(f) != data]
        frozen.clear()
        if bad:
            raise RuntimeError("the painter's grid picture changed during the run: the shared RGB view is not valid")
    return remove
