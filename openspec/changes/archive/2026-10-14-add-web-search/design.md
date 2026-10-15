# Design

## Context

See proposal.md for why. The pipeline searches through a SearXNG container on the maintainer's machine, fetches
pages and pictures, pulls on-this-day facts from Wikipedia and forecasts for a built-in location, and
reads social posts (`rm_reddit` and friends). Reddit has no obtainable API key under its 2026 policy,
so the pipeline reads its public RSS feeds, including search feeds for posts and comments, and takes votes from
the public embed card; the feeds allow about one request a minute, signaled by `x-ratelimit` headers.

## Goals / Non-Goals

**Goals:**
- Every outbound host is either configured by the user or listed with a switch.
- One adapter per source, behind one interface.

**Non-Goals:**
- Running SearXNG for the user. The settings point at one the user runs, or at an API provider.
- A built-in search choice that needs no setup (the ddgs route in `docs/research/web-search.md`). It is a
  stretch goal for later.

## Decisions

**Providers behind one interface.** `search(query) -> [result(title, url, snippet)]` with a SearXNG
adapter and API adapters (for example Brave, Tavily or Serper). The key lives in the credential store.

**SearXNG is the user's to run.** SearXNG is one choice in the provider dropdown, with a text box for its address (shown as
`http://127.0.0.1:8888`). PaperDaemon never installs, starts, stops or updates it. Anyone who wants SearXNG
runs it themselves, usually in Docker, and enters the address.

Two managed alternatives were explored and rejected (details in `docs/research/web-search.md`):

- *A copy PaperDaemon keeps and runs natively on Windows.* SearXNG does not support Windows. It needs a
  file-name workaround and a stand-in for one Unix-only module, and every update would need testing, a
  second Python and a fallback.
- *A Docker container PaperDaemon manages.* It needs Docker Desktop, cannot end with PaperDaemon the way a job
  object does, and must not collide with other applications' containers.

**Built-in sources are named, with switches.** Encyclopedia facts for a date and weather for the user's
location are useful enough to ship on, but they are services the user did not type an address for, so
the settings list each one's host and a switch turns it off.

**Social sources are adapters with their own pacing.** Each adapter declares what it can read (posts,
comments, votes) and its rate-limit rule; a shared pacer waits as the source's headers ask. Waiting on
an external service is a sync matter, not a model limit, so a timer is appropriate here.

**Cards are a chart type.** Cards render through the chart tool as half-width cards in two columns, and
a posts chart can clip real posts, as in the pipeline.

## Risks / Trade-offs

- [Sources change or close their public feeds] → Each source is an adapter; a failing one is reported by
  name in the job, and the others still work.
- [A slow source holds a job for minutes] → The job's phase shows it is waiting on a rate limit.

## Open Questions

Can wait:
- Which search API providers to support first besides SearXNG.
- Whether fetched page text should be cached for the length of a notebook's conversation.
