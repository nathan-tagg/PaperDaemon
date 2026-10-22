"""EACH LINEUP'S LoRA FOLDER: <data>/loras/<lineup>, made by PaperDaemon. The LoRA files put in it go with every
picture that lineup's image model makes, the way its image harness says to apply them (the harness's `loras`:
"request", sd-server's request list; "prompt", <lora:name:strength> tags in the prompt), at the harness's
strength. A harness that says nothing applies none of them, and the job's log says they were left out.

The image server loads them from this folder: its start script is told where it is (PAPERDAEMON_LORAS, beside
PAPERDAEMON_PORT), e.g. stable-diffusion.cpp's `--lora-model-dir "%PAPERDAEMON_LORAS%"`. Nothing is baked into
a model; the files are the user's, and a lineup deleted leaves its folder as it is.
"""
import os
import re

from . import paths

EXTS = (".safetensors", ".gguf", ".ckpt", ".pt")


def _safe(name):
    """A lineup's name as a folder name on Windows."""
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name or "")).strip().rstrip(". ")
    return n or "lineup"


def folder(lineup):
    """The lineup's LoRA folder, made when it is not there."""
    return paths.sub("loras", _safe(lineup))


def files(lineup):
    """The LoRA files in the lineup's folder (and folders inside it), as paths inside it with forward slashes."""
    root = folder(lineup)
    out = []
    for d, _subs, names in os.walk(root):
        for n in names:
            if n.lower().endswith(EXTS):
                out.append(os.path.relpath(os.path.join(d, n), root).replace("\\", "/"))
    return sorted(out, key=str.lower)


def rename(old, new):
    """A renamed lineup keeps its LoRAs: its folder takes the new name (when the new name has none yet)."""
    a = os.path.join(paths.data_dir(), "loras", _safe(old))
    b = os.path.join(paths.data_dir(), "loras", _safe(new))
    if a != b and os.path.isdir(a) and not os.path.exists(b):
        os.replace(a, b)


def open_folder(lineup):
    """The folder in the file manager. -> its path."""
    from . import folders
    p = folder(lineup)
    folders.open_folder(p)                             # in front, over PaperDaemon's window
    return p
