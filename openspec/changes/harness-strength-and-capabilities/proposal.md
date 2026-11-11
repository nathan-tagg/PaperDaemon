# Proposal: harness-strength-and-capabilities

## Why

The maintainer's design (11-11): the harness a text model runs on is set by how strong the model is, and what the
model can do on its own is a set of checkboxes on top of it. "Under Harness its just a model strength selector
(Strong, medium, weak) and then its a series of capability checkboxes", "the harness base gives the high level of how
jobs are handled, intake, output, jobs etc, and then the capacities add onto the harness base". A lineup always has
an image slot and a search slot; when one is empty, the text model's capabilities say whether the model does that job
itself or the job is not offered. "Strong would be the claude models, medium would be the 27b class of models and
gemini 3.8 flash, weak would be weaker ones than that."

## What Changes

- Three shipped text harnesses are the bases: Weak (`weak-text`, new), Medium (`default-text`), Strong
  (`lean-default`). Weak is Medium with short answers, a lower output limit, and sketches, social posts, pictures
  from the web and the long games turned off.
- Two text capabilities, each yes or no: `web_search` and `image_generation`. Defaults: no to both on Weak and Medium;
  Strong searches the web, and makes no images.
- A lineup with no search of its own and a text model that can search: the model is told to look facts up with its own
  search, and PaperDaemon turns that search on where it knows how (the `claude` program, by its data's `web_search`;
  the Anthropic API's own search tool). With neither, the model is told facts cannot be looked up.
- Image generation by the text model: with the Image tab empty and the capability added, a picture step goes to the
  text model's own server (a chat completion asking for an image) and the picture is taken from the reply. It is for
  servers that make images themselves and need no separate image model.
- The Text / Reasoning tab (the maintainer's revision, 11-11: "the harness strength slider is ugly move it to a drop
  down", "Perhaps the capacities area should be a typeahead with pills underneath instead", "The Your Harness should
  not be there anymore", "THERE SHOULDN'T BE AN ADD HARNESS BUTTON ANYMORE", the capability lines "belong in the help
  modal, in a warning card at the bottom"): a Harness dropdown (Weak / Medium / Strong) with the base's description
  and the models it was tested with; Capabilities a type-ahead box with a pill under it for each capability (Enter adds,
  the list narrows as pills are added, hovering a pill explains it, x removes it); a "?" and Help on both labels; the
  help modal ends in a warning card. No "Your harness", no "+ Add Harness" on either tab. The Image and Network tabs say
  that what they set is used instead of the text model's own.

## Impact

- Affected specs: models/harnesses
- Code: `paperdaemon/harnesses/` (fields, rules, shipped files, guide), `paperdaemon/models/slots.py`, `cli.py`,
  `adapters.py`, `lineup.py`, `paperdaemon/loop.py`, `paperdaemon/server.py`, `paperdaemon/pipeline/host/__init__.py`,
  `decision.py`, `paperdaemon/ui/slots.js`, `scripthelp.js`, `models.js`, `setup.js`, `app.css`, the strings in 19
  languages
- Tests: `tests/test_harness_bases.py`
