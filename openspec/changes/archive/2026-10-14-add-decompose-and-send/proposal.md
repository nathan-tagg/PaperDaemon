# Proposal

## Why

Not everything worth putting on the tablet starts as a request on a page. The pipeline has a drop
box: drop an image, see it as strokes, send it to the tablet as a new page of one inbox notebook.
PaperDaemon keeps it as it is: a drag box, then send to the tablet, with a destination inbox defined in
the app by the user.

## What Changes

- A drop box: drop an image or click to choose one, set its size on the page, and see the strokes it
  becomes and how many.
- Send appends a new page to the inbox notebook named in the settings (`tablet.inbox`): the strokes,
  under a small caption.
- The first send creates the inbox notebook, and any folder on its path. The daemon never answers the inbox,
  whatever it is tagged with.
- Sending is a cloud write like any other; nothing else changes. There is no undo (the maintainer's decision).
- The image and its preview are held in memory only. The pipeline saves every drop to disk; PaperDaemon does not.

## Capabilities

### New Capabilities
- `studio/decompose-and-send`: the drop box, its preview, sending to the inbox notebook, and what
  is kept.

### Modified Capabilities
None.

## Non-goals

- Making a picture from a prompt on this screen. The maintainer: "Just a drag box > send to tablet".
- Sending to any notebook other than the inbox, or onto part of an existing page.
- Decomposer options beyond the size. The decomposer ships frozen (drawing/decomposer).
- Editing strokes by hand.

## Impact

- A drop box in the UI and routes under `/api/v1/studio`.
- Uses the decomposer, the sync client and the tablet settings from earlier changes.
