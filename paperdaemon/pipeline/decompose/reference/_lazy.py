"""The heavy libraries the reference runs on (OpenCV, SciPy, numba), loaded when the reference first USES them.

The app decomposes through the C library and reads only the reference's constants and defaults, so importing
the reference must not load these; the reference itself, run for an identity check, loads each the moment it
first needs it and behaves exactly as with the imports at the top of its modules.
"""
import importlib
import importlib.util


def available(name):
    """True when the library is installed (found without importing it)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


class Module:
    """A module imported on first attribute access; `then(module)` runs once, right after the import."""

    def __init__(self, name, then=None):
        self._name, self._then, self._mod = name, then, None

    def _load(self):
        if self._mod is None:
            mod = importlib.import_module(self._name)
            if self._then:
                self._then(mod)
            self._mod = mod
        return self._mod

    def __getattr__(self, attr):
        return getattr(self._load(), attr)


def _ipp_off(cv2):
    # DETERMINISM: OpenCV's IPP paths are not run-to-run deterministic (the precise distance transform moved
    # strokes by ~1e-6 between identical runs); off, every decomposition is bit-identical, which the C port
    # requires. Set the moment OpenCV loads, before any of the reference's calls into it.
    if hasattr(cv2, "ipp"):
        cv2.ipp.setUseIPP(False)


CV2 = Module("cv2", then=_ipp_off)


def function(module, name):
    """A function of a module, imported on its first call."""
    holder = {}

    def call(*a, **k):
        if "f" not in holder:
            holder["f"] = getattr(importlib.import_module(module), name)
        return holder["f"](*a, **k)
    call.__name__ = name
    return call


def njit(**options):
    """numba.njit(**options), compiled on the function's first call (and the plain function without numba)."""
    def deco(f):
        holder = {}

        def call(*a, **k):
            if "f" not in holder:
                if available("numba"):
                    import numba
                    holder["f"] = numba.njit(**options)(f)
                else:
                    holder["f"] = f
            return holder["f"](*a, **k)
        call.__name__ = f.__name__
        call.py_func = f
        return call
    return deco
