# How to create a new image harness

An image harness tells PaperDaemon how to get pictures out of one family of image models. PaperDaemon reads
every `.json` file in this folder, checks it, and lists every harness that passes in the Harness box of the
Image tab. A file that fails is listed with what is wrong with it.

PaperDaemon's own image harnesses are part of the app, not kept here: the built-in default, and
stable-diffusion.cpp - FLUX.2 Klein 9B and stable-diffusion.cpp - Z-Image Turbo. A harness here builds on one of
them (`extends`, or the built-in default when it names none) and changes only what it names.

## Name it for its server and model

A harness is made for one kind of server running one model, and its name says both: `stable-diffusion.cpp - FLUX.2 Klein 9B`. Every
file also says, for the people who read it:

| Field | What it is |
| --- | --- |
| `server` | Required. The server it is made for: `"stable-diffusion.cpp (sd-server)"`. |
| `models` | Required. The models it is made for: `["FLUX.2 Klein 9B"]`. |
| `notes` | What anyone choosing it should know: what it was tested with, what it does well, what to avoid. |

PaperDaemon shows these and never acts on them. A harness you build on another still says its own.

## The fields

| Field | What it is |
| --- | --- |
| `id` | Its name in the settings. Optional: the file name without `.json`. Must not be taken. |
| `name` | What the Harness box shows: the server, then the model. Optional: the `id`. |
| `extends` | The harness it builds on: one of PaperDaemon's, or another here. Optional: the built-in default. |
| `patterns` | Model names (regular expressions) that make this harness the automatic choice. |
| `refuse` | Model names that rule it out even when a pattern matches. |
| `abilities` | What it can do: `generate`, `edit_reference`, `img2img`, `inpaint`. |
| `steps` | Steps per picture (1 to 150). |
| `steps_range` | The lowest and highest steps worth using: `[4, 12]`. |
| `cfg` | Guidance scale. |
| `sampler`, `scheduler`, `shift` | The server's sampler and scheduler names, and the shift (or `null`). |
| `size` | Width and height of a picture, 64 to 4096: `[1024, 1024]`. |
| `workflows` | Named recipes the text model can ask for (below). |
| `features` | Things this model should not be asked to do: `{"off": [...]}`. |

## Workflows

A workflow has the same name on every image harness, and each harness carries it out its own way. A coloring
page is always `childrensColoringBook`; your harness decides the wording, the steps and any adapters. Your
workflows add to the ones of the harness you build on; one with the same name replaces it.

| Workflow field | What it is |
| --- | --- |
| `prompt` | The wording, with `{subject}` where the text model's description of the picture goes. |
| `about` | What it is for, told to the text model. |
| `steps` | Steps for this workflow only. |
| `loras` | LoRA adapters for this workflow only: `[{"file": "ink-wash.safetensors", "strength": 0.8}]`. The file must be in the folder your image server loads adapters from. |
| `reference` | `true` when it starts from a picture on the page. |

## An example

```json
{
  "id": "my-image-model",
  "name": "stable-diffusion.cpp - My image model",
  "server": "stable-diffusion.cpp (sd-server)",
  "models": ["My image model"],
  "notes": "Eight steps are enough; more change nothing.",
  "patterns": ["my-image-model"],
  "abilities": ["generate"],
  "steps": 8,
  "workflows": {
    "inkWash": {
      "about": "a soft ink wash painting",
      "prompt": "An ink wash painting of {subject}.",
      "loras": [{"file": "ink-wash.safetensors", "strength": 0.8}]
    }
  }
}
```

Save it here as `my-image-model.json`, then choose it in the Image tab's Harness box, or leave the box empty
and let the pattern pick it.
