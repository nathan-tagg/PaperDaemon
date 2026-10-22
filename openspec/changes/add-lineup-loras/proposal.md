# Proposal: add-lineup-loras

## Why

LoRAs could be applied only inside a harness workflow, so using one meant writing a harness for it. The maintainer
asked for a LoRA folder per lineup instead, with the image harness saying how to apply whatever is in it.

## What Changes

- New capability `models/lineup-loras`: each lineup's LoRA folder, the harness's `loras` field (how they are
  applied: the server's request list, or prompt tags; and their strength), the start script's
  `%PAPERDAEMON_LORAS%`, and the link to the folder under the image model's start script.
- PaperDaemon's stable-diffusion.cpp harnesses (FLUX.2 Klein 9B, Z-Image Turbo) apply them in the request's list.

## Impact

- `paperdaemon/loras.py` (new), `paperdaemon/card.py`, `paperdaemon/harnesses/`, `paperdaemon/models/hotswap.py`,
  `paperdaemon/scripts.py`, `paperdaemon/server.py`
- `paperdaemon/ui/slots.js`, `models.js`, `app.css`, the strings in every language
