# Design

## The lineup of a job

The daemon watches every lineup's tags (`RM_TRIGGERS`, a JSON list); the ledger resolves the most specific tag
per page as before, matching the longest watched tag so "qwen fast" is not read as "qwen". The host's run file
holds every lineup's harness values and features plus a tag-to-lineup map, so a job on another lineup changes
nothing the halves were started with. At the start of each job the host calls `use_lineup(name)`: it swaps its
own values (capabilities, model, context, brief) and posts `/host/lineup`, after which the engine's
`settings.active()` is that lineup until the next job names another. A benchmark run forces its lineup as before.

## Start scripts by need

`scripts.identity(slot)` is the script file's path or a hash of its inline text, with the location. The server
record keeps the identity it was started for; `card` treats a running server as ready only when its identity
is the one the lineup in use needs, and `hotswap.start` ends a different one before running the needed script.

## Memories

`memories.json` in the data folder, `{lineup: [{id, text, saved}]}`. The model's decision tools (plan, answer,
ask, skip) take an optional `remember` list declaring only `text` (the server's grammar keeps declared key
order); `replaces` is free. The host applies it at the end of the job through `/host/memories` and adds what
was done to the job's note. The system message is the brief, then the memories, then the tag prompts, then the
notebook's own instructions, so the cached prefix holds.
