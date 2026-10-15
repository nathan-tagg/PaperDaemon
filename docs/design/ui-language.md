# PaperDaemon interface language

PaperDaemon is the desktop half of a monochrome e-ink tablet. The tablet is where the work shows up; the desktop
app is where you connect things, check what happened and fix what didn't. The interface borrows the
tablet's materials, paper and ink, and behaves like a well-made instrument: dense, calm and exact.

Everything here is implemented in `mockups/paper.css`. Copy the tokens as they are when building the real UI.

## Principles

**Paper and ink, inverted.** A slate background, chalk text, hairline rules: the tablet's paper and ink,
turned dark. Structure comes from type and rules, not from boxes around everything.
*Why:* it is the tablet's own vocabulary. A screen that looks like the device feels like part of it, and
fewer containers means less noise between the user and the settings.

**Hierarchy from type, not color.** Size, weight and the serif/sans contrast carry the hierarchy. Color is
reserved for state.
*Why:* e-ink has no color to lean on, and a layout that reads in grayscale reads everywhere, including for
color-blind users.

**One mark.** A single accent, the red pencil, means "look here": an error, a failed test, an action that is
needed. It is never decoration, never a brand color and never a hover effect.
*Why:* an accent used everywhere stops meaning anything. An editor's red pencil only appears where something
is wrong.

**Say what happened, with numbers.** "Answered in 3 paragraphs, 21 s." "412 of 1,200 files." "Search failed:
SearXNG did not answer at 127.0.0.1:8888."
*Why:* specific text is how a tool earns trust. "Processing…" hides problems; a count shows progress and
exposes a stall.

**Dense and calm.** Settings rows at a 44 px pitch, no hero sections, no marketing, most screens fit a
1160 × 780 window without scrolling.
*Why:* this is a tool the user comes back to for a minute at a time. Density respects that minute.

**Show where things live.** Endpoints, ports, paths and launch scripts are shown in full, in monospace, and
can be copied.
*Why:* PaperDaemon runs on the user's own machine, often with local models. They need to see exactly what is
configured to fix it.

**Privacy is visible.** When a model slot or search provider sends pages off the computer, the screen that
configures it says so, in plain words, next to the setting.
*Why:* a privacy fact buried in a policy page is not a fact the user knows.

**It is a tool.** No pricing, credits, usage meters or upgrade prompts, anywhere.
*Why:* PaperDaemon uses AI; it does not sell it.

## Color

PaperDaemon is dark only. There is no light mode, and none is planned.

| Token | Value | Used for |
|---|---|---|
| `--paper` | `#1E2120` | window background |
| `--paper-sunk` | `#171918` | navigation rail, row hover, recessed panels |
| `--field` | `#262A28` | inputs, code, rendered pages, dialogs |
| `--ink` | `#E8E4DA` | text, primary buttons, "on" marks, section rules |
| `--ink-2` | `#BCB8AE` | secondary text, help text |
| `--ink-3` | `#94918A` | meta text: times, table headers, placeholders |
| `--rule` | `#343836` | hairline separators (decorative only) |
| `--edge` | `#737974` | the boundary of anything you can operate |
| `--mark` | `#E58A72` | the red pencil: errors, failures, needed actions |

The palette is inverted e-ink: chalk on slate, never neon and never pure black.

Measured contrast (WCAG 2): body ink on paper 12.8:1. The weakest text pair, `--ink-3` on `--field`, is
4.6:1. `--mark` is 5.0:1 or better on every background. `--edge` is 3.0:1 or better against every
background it sits on, as required for control boundaries. `--rule` is deliberately faint and is never
the only thing that shows a control's shape.

Rendered tablet pages are drawn chalk on slate, like the rest of the interface. Where true appearance
matters (Decompose and send, the benchmark), a page is shown as on the tablet: black on white, in the
pens' true colors.

## Type

Three faces from one family, Adobe's Source, all under the SIL Open Font License and bundled in
`fonts/`:

- **Source Serif 4** for page titles and section headings. It brings the book-and-paper voice of the
  tablet, and its optical sizes keep it crisp at 19 px and elegant at 36 px.
- **Source Sans 3** for everything you read and operate. It stays legible at 12–14 px, has true tabular
  figures, and is narrow enough for dense rows.
- **Source Code Pro** for endpoints, paths, tokens and launch scripts. It is drawn to sit beside Source
  Sans without a jump in size or color.

One family means matching proportions and a license that allows bundling the fonts in the app. It also avoids
the default font of every generated interface.

| Role | Face | Size / line height | Weight | Color |
|---|---|---|---|---|
| First-run title | Serif | 36 / 42 | 600 | ink |
| Page title | Serif | 28 / 34 | 600 | ink |
| Section heading | Serif | 19 / 26 | 600 | ink |
| Body and controls | Sans | 14 / 20 | 400 | ink |
| Row label | Sans | 14 / 20 | 600 | ink |
| Help text | Sans | 13 / 18 | 400 | ink-2 |
| Meta, table headers | Sans | 12 / 16 | 600 | ink-3 |
| Code, paths, endpoints | Mono | 13 / 20 | 400 | ink |

Rules:

- Sentence case everywhere: titles, headings, buttons, menu items.
- Numbers that line up (tables, times, durations, counts) use tabular lining figures.
- Running text stops at 66 characters a line.
- No letter-spaced uppercase labels. A heading is a heading.

## Space and layout

- Base unit 4 px. Steps: 4, 8, 12, 16, 24, 32, 48, 64.
- Window: 1160 × 780 by default, 900 × 620 at least.
- Navigation rail: 216 px on `--paper-sunk`, hairline on its right edge. The item for the current screen is
  ink, semibold, on `--paper`, with a 2 px ink rule on its left like a bookmark ribbon. An item may carry a
  short state on its right ("Connected", "18/20").
- Content: 32 px top, 48 px sides, at most 800 px wide.
- Sections: a serif heading over a full-width 1 px ink rule, then rows.
- Settings rows: a two-column grid, label column 220 px (label, help text below it), control column the
  rest. Rows are divided by hairlines, 12 px above and below.
- A notebook page is 3:4 (1620 × 2160, or 1404 × 1872 in older notebooks). A PDF page is its PDF page, at
  its own proportion. Every page shown in the interface keeps its page's proportion.

## Components

**Button.** 1 px `--edge` border, 2 px radius, 14 px medium text. Four kinds:

- Primary: ink fill, paper text. One per view at most.
- Secondary: outline.
- Quiet: underlined text, no border, for low-stakes actions inside rows.
- Danger: red pencil text and outline, filled red pencil on hover. Danger buttons open a confirm dialog;
  they never act on the first click.

The label is a verb naming the result: "Test connection", "Roll back", "Send to tablet".

**Field.** `--field` background, 1 px `--edge` border, 2 px radius, 30 px tall. Endpoints, paths and names use
the mono face. An invalid field gets a red pencil border and a line of help text in red pencil saying what
is wrong and what would be right.

**Secret field.** A stored secret is never displayed, not even in part. The field shows where the secret is
kept and when it was added ("Saved in the Windows credential store · added Sep 22"), with Replace and Remove.
Replace swaps in a password input. The pairing token is the one exception: it can be shown and copied,
because it has to be typed on a phone.

**Segmented control.** For two to four exclusive choices that change what else is on screen ("On this
computer / Remote service"). Outline group; the chosen segment is ink with paper text.

**Toggle.** A square-cornered switch: a hairline track with a small square knob that fills with ink when
on. Always paired with a label that names the thing, not the state ("Hot swapping", not "Enabled").

**Select.** Native select, restyled to match the field, with a drawn chevron. Keeps the platform's keyboard
behavior.

**Status mark.** Shape first, color second, always followed by a word:

| Mark | Shape | Means |
|---|---|---|
| on | filled ink circle | connected, loaded, passed, ready |
| off | hollow circle | off, idle, not set up |
| busy | half-filled circle | working, loading, swapping |
| fail | red pencil cross | failed, needs attention |
| skip | short dash | skipped on purpose, not a failure |

**List row and table.** Headers in 12 px semibold `--ink-3` over a 1 px ink rule; rows divided by hairlines.
No zebra stripes, no cell borders. Hover lifts the row to `--paper-sunk`. Numbers right-aligned in tabular
figures.

**Margin mark.** A row that failed or needs attention gets a 2 px red pencil stroke in the page margin to
its left, the way an editor marks a manuscript. The row itself stays on paper. No pink backgrounds, no
colored rows.

**Activity row.** Clock time, the page ("Garden plans › p. 3") with how it was asked below it, what
PaperDaemon did in words, the job's steps as five short segments (noticed by the daemon; read, decided, drew and
synced by the host), and how long it took. A failed step is a red pencil segment, and the reason is written in the row.

**Code and script editor.** Mono 13/20 on `--field`, a line-number gutter on `--paper-sunk`, hairline border.
It is plain text, never syntax-colored in several hues. A caption above says when the script runs.

**Rendered page.** A 3:4 frame on `--field` with an `--edge` hairline. Strokes are drawn in the current ink.

**Empty state.** A small outline of a blank page, one sentence on why it is empty and one on what to do.
("No jobs yet. Tag a page with PaperDaemon on your tablet; it shows up here within a few seconds.")

**Error state.** A margin mark, a sentence saying what failed and why, and the one action most likely to
fix it. The error sits where the problem is, not in a toast that disappears.

**Notice.** A 2 px ink rule on the left of a short paragraph, for facts the user must know before acting.
The off-machine notice for model slots and search providers is one. A notice turns red pencil only when
action is required.

**Confirm dialog.** A sheet of `--field` with an `--edge` hairline and the interface's only shadow, over a
dimmed window. The title is the question ("Roll back Reading log to 09:13?"). The body gives the consequences in plain
numbers. Buttons sit bottom right: Cancel, then the action, named with the same verb as the title.

**Progress.** A count in words ("Pulling 112 of 412 documents") over a 1 px rule that fills with a 2 px ink
line. No percentages without the counts, no spinners when a count is knowable.

## Icons

Words first. An icon appears only where a word will not fit or would repeat down a list: copy, show,
open folder, external link, drag handle. Drawn on a 16 px grid with a 1.5 px stroke, square caps and
mitered joins, in `currentColor`, never filled, never two-tone. Never used: sparkles, magic wands, robots,
brains, lightning bolts, chat bubbles standing for "AI".

## Motion

- 120 ms ease-out for hover, press and toggle; 160 ms for a dialog (fade plus at most a 4 px rise).
- No springs, bounces, shimmer or skeleton screens.
- Progress is shown by counts, not by animation.
- With `prefers-reduced-motion`, state changes happen instantly.

## Voice

- Plain, short, specific. Say what happened and give the numbers.
- The two moving parts have two names. The **daemon** notices tagged pages; the **host** carries out a
  job. Use exactly these words in labels, headings and copy, never "watcher", "agent" or "bot".
- Buttons are verbs. Titles and headings are sentence case.
- Errors say what failed, why if known, and what to do next: "SearXNG did not answer at 127.0.0.1:8888. Is
  it running?"
- Privacy in plain words: "This slot sends your pages to api.example.com. They leave this computer each time
  a page is answered."
- Clock times use the system's format; durations read "21 s", "1 min 44 s".
- American spelling. No exclamation marks, no emoji.
- Never: "magic", "supercharge", "seamless", "effortless", "smart", "unlock", "AI-powered", "Welcome back",
  "Oops", "Something went wrong".

| Instead of | Write |
|---|---|
| Oops! Something went wrong. | Sync failed: the cloud answered 401. Paste a new device token. |
| Processing your request… | Drawing a bar chart, step 4 of 5 |
| Your AI assistant is ready! | Connected. PaperDaemon answers pages tagged PaperDaemon. |
| Are you sure? | Roll back Reading log to 09:13? Your edits since then go back too. |
| Enabled | Hot swapping |

## Never

The tells that make an interface look generated. None of these appear in PaperDaemon:

- Purple, indigo or blue-violet gradients; gradient text; gradient buttons.
- Glassmorphism, blurred panels, glow, neon.
- A grid of rounded cards with drop shadows as the default container; KPI-tile dashboards.
- Pill badges on everything; a colored chip for every status.
- Sparkle, wand, robot and brain icons; emoji.
- Centered hero sections, oversized welcome headlines, "Welcome back!".
- Tiny uppercase eyebrow labels over headings.
- Lorem ipsum, stock illustrations, 3D blobs.
- Skeleton shimmer, bouncing loaders.
- One default sans at one weight doing every job.
- Pricing, credits, usage meters, upgrade prompts.

## Accessibility

- Focus is a 2 px ink outline, offset 2 px, on everything focusable. Never removed.
- Marks never carry meaning alone; the word beside them does.
- Every control is reachable and operable from the keyboard. Dialogs trap focus and close on Escape.
- Text contrast is at least 4.5:1 and control boundaries at least 3:1.

## Files

- `mockups/index.html`: the contents page; open it in a browser.
- `mockups/paper.css`: tokens and components.
- `mockups/mockup.js`: behavior for the mockups only (segmented controls, switches, menus, dialogs). The
  real app replaces it.
- `fonts/`: the three typefaces and their licenses.
- `mockups/book.js`, `mockups/book.css`: the tablet book. `uv run python tools/mockup_book.py` turns every
  screen, in each state its controls reach, into one PDF in `build/mockup/` in which every control is a
  link to the page showing what it does.
