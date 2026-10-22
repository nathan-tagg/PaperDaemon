# Proposal: inbox-tag-and-quick-sheets

## Why

Send to Tablet needed two settings, a notebook path for the Mirror and another for the False Mirror, and failed
until both were chosen. The maintainer asked for one tag instead, beside the other system tags: every notebook
carrying it is an inbox, and a library with none sends to its Quick sheets. The False Mirror also gets the
tablet's Quick sheets button and the tablet's options for a new notebook.

The game pages (messages, the adventure) covered the whole page with their picture, so typed text, which the tablet
puts below a picture, could not go in the box where the player answers. Typing is the stronger way to answer.

## What Changes

- New capability `tablet/inbox`: the inbox tag, Quick sheets as the fallback, inboxes never worked on, and the
  Send button's "Sent to all inboxes".
- The False Mirror's head button is a + with Quick sheets, New notebook, New folder and Import. New notebook asks
  for the cover setting and, with an account signed in, a template.
- The game pages' picture ends where the player's space begins; a turn reads typed text and handwriting there.
- A kept decomp sends again: a color with its own alpha was given a second one.

## Impact

- `paperdaemon/settings.py`, `paperdaemon/ledger.py`, `paperdaemon/loop.py`, `paperdaemon/studio.py`,
  `paperdaemon/server.py`, `paperdaemon/remarkable/local.py`, `paperdaemon/pipeline/draw/__init__.py`
- `paperdaemon/pipeline/games/inputarea.py`, `messages.py`, `adventure.py`
- `paperdaemon/ui/settings.js`, `decompose.js`, `tablet.js`, `app.css`, the strings in every language
