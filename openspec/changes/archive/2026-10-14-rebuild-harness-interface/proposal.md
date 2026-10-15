# Proposal

## Why

The harnesses PaperDaemon has are JSON files: a model's capabilities, request fields and image workflows. The
September design said a text harness is a set of protocols (what the model is shown, what its reply means, who
does each task, what is refused), but the code never got there. Everything a model is told and every reply it
gives is written into the host, so a model that needs other tooling (another tool shape, another coordinate
format, a model that does the whole job itself) means editing the host.

The user's definition: "the harness needs to implement (Im using the coding definition of implement, like from
an INTERFACE) the intake procedure, the jobs that it can schedule, carried out by the host, which again calls
the harness or the model or otherwise, like just does the research, calls the chart, etc, sequentially, the
skill building, etc."

## What Changes

- **A text harness is an interface** the host calls: an intake protocol (what the model is shown and told), an
  output protocol (what its reply means: jobs, a finished page, another turn, a question back, or a skip),
  assist protocols (locate something on the page, read handwriting, describe a picture), `validate()`, a
  conflict protocol, skills (prompt files it owns) and `declare()` (its needs and the job kinds it supports).
- **The default is built in.** PaperDaemon's own harness is the app; nothing named "Default" sits in the
  harnesses folder. A harness in the folder is a Python file that overrides only what it changes, or a folder
  of skills only. Today's flow moves into the default with its prompts byte-identical.
- **One enumerated list of job kinds** (`JobKind`). The host holds each kind's protocol (what the model
  supplies, what the host does, whether results go back); a harness may override one, and usually does not.
- **The host never writes a prompt or reads a reply itself**: its narrow questions go through the assist
  protocols.
- **Every harness file declares** its server, its models and notes, and is named "server - model".
- **validate()** checks the safe zones and a page stroke limit (about 250,000); over the limit the host fixes
  it (a new page after this one for text, a lower region budget for a picture).
- **Conflicts become jobs.** When the tablet changed a page the job also changed, the tablet's copy wins, ours
  is set aside, and a CONFLICT job is queued behind the others: the harness sees both pages and the job that
  made ours, and its jobs run on the user's page.
- **The capacity engine** reads `declare()`: a kind the harness has no protocol for is off with the reason,
  and abilities a model provides itself (its own pictures or search) turn their kinds on.
- **Game pages** go through intake (a GAME_TURN job) instead of bypassing it.
- Supersedes facelift task 5.1's "no harness is code", and absorbs facelift groups 4 (the host as objects)
  and 6 (the structured decision) where they concern where the decision and the brief live.

## Capabilities

### New Capabilities
- `models/harness-interface`: the text harness's protocols, the built-in default, Python and skills-only
  harnesses, declared fields and naming, validate().
- `jobs/job-kinds`: the enumerated job kinds, their host-held protocols, and how the host works through them.
- `sync/conflicts`: conflicts between the tablet and a job, set aside and resolved as a job.

### Modified Capabilities
- `models/harnesses` (add-model-slots-and-harnesses): the base harness is the built-in default; task
  protocols are the host's; no shipped lineups; no upgrade from the old "profiles" names.

## Non-goals

- A strong-model harness or a small-model harness: the interface allows them; shipping them is later.
- MCP servers or clients.
- Changing what any job does: the job kinds are today's steps, listed.
- Any display of prices or usage.

## Impact

- New `paperdaemon/harnesses/text.py` (the interface and the built-in default), `paperdaemon/pipeline/host/jobs.py`
  (JobKind and the protocols); the brief, the decision tool and the grounding prompts move out of
  `pipeline/host/__init__.py`.
- The harness folder: `llm\` holds `.py` harnesses and skills folders, `image\` holds image harness JSON; each
  has its own guide.
- The daemon queues CONFLICT jobs; the sync keeps the set-aside copy for them.
- The build ships the full standard library so a user harness can import it.
