# Proposal

## Why

Many requests on a page need facts the model does not have: today's news, a forecast, a price, what
people are saying about something. The pipeline answered them through a local SearXNG, fetched pages and
pictures, and drew social posts as cards, from Reddit's public feeds, Hacker News, Bluesky, Mastodon
and others. PaperDaemon needs the same, configured in the app instead of on one machine.

## What Changes

- Web search through a SearXNG address or a search API provider with a key, chosen in the settings.
- Fetching a web page's text, or a web picture, for a job.
- Built-in sources (encyclopedia facts for a date, weather for the user's location) listed in the
  settings with the host each one calls, each of which can be turned off.
- Social post cards: posts drawn as cards with author, text, votes and time, from sources that allow it,
  paced to each source's rate limits.

## Capabilities

### New Capabilities
- `search/web`: search providers, fetching pages and pictures, built-in sources, and what leaves the machine.
- `search/social-cards`: finding social posts and drawing them as cards.

### Modified Capabilities
None.

## Non-goals

- Logging in to any social network, or reading private feeds.
- Scraping sites that forbid it.
- Paid social APIs.

## Impact

- New package `paperdaemon/search/`, ported from the pipeline's search, fetch, history, weather and `rm_reddit`
  modules.
- Search settings gain provider choices and the built-in source switches; the search key stays in the
  credential store.
