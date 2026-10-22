# Design: add-lineup-loras

## D1. Where the files are, and who loads them

`<data>/loras/<lineup>`, made by PaperDaemon, named for the lineup (characters Windows refuses in a folder name
become `_`). A renamed lineup's folder is renamed with it; a deleted lineup's is left alone, since the files are the
user's. The image server loads them itself: its start script is given the folder in `PAPERDAEMON_LORAS`.

## D2. How they are applied

The image harness's `loras` field says how. `"request"`: in the request's `lora` list, by path inside the server's
folder, as stable-diffusion.cpp's server takes them (it ignores tags in a prompt); the server's own list is asked
for first, which also makes it look at the folder again, and a file it does not list is left out and reported.
`"prompt"`: `<lora:name:strength>` tags after the prompt, as the Stable Diffusion web UI takes them. A harness without
`loras` applies none, and reports them left out. A workflow's own LoRAs go with the lineup's.

## D3. Nothing baked

The weights never change: a file taken out of the folder is gone from the next picture.
