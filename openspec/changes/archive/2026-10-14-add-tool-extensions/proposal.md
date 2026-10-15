# Proposal

## Why

The maintainer wants PaperDaemon open to abilities nobody has written yet: "terminal stuff, or open my garage
door stuff, or literally whatever". If each new ability means editing the host, the host becomes a
fork per ability. Every tool the host offers, built-in or added, should plug in the same way.

## What Changes

- One tool interface: a tool declares its name, what the model is told about it, its input, what it
  needs (an image slot, vision, the network) and the code the host runs.
- Every built-in tool (words, charts, pictures, coloring pages, mark-ups, search, social cards, tags)
  is written against that interface.
- A capabilities screen lists every tool with what it needs and a switch; a tool that is off is never
  offered to the model.
- Tools that act outside the tablet, such as running a command or switching a device at home, are off
  by default and run only when the user named that action.

## Capabilities

### New Capabilities
- `extensions/tools`: the tool interface, the switches, what a tool may need, and the rule for tools
  that act outside the tablet.

### Modified Capabilities
None.

## Non-goals

- A marketplace or download of third-party tools.
- Any specific outside-world tool (terminal, home automation) in this change.

## Impact

- New package `paperdaemon/tools/` with the interface and the registry; the drawing and search tools move
  behind it.
- A capabilities screen and routes under `/api/v1/tools`.
