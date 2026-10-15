# Tasks

## 1. Search and fetch

- [x] 1.1 Write the provider interface with SearXNG and one API adapter; verify against recorded responses and that no search tool is offered without a provider Done: `paperdaemon/search.py` (a local search server or Brave, Tavily, Exa or Serper, one answer shape; `tests/test_search.py`, stubbed answers); a lineup without search is offered no search step or tool (`tests/test_host_lineups.py`).
- [ ] 1.2 Port page-text and picture fetching; verify with recorded pages Ported (the fetch step and web pictures); the recorded-page test is still to write.
- [x] 1.3 List built-in sources with their hosts and switches; verify a source that is off is never called (stubbed network) Done as the maintainer decided: one switch, Settings > Network access, off stops every direct call before it leaves (`paperdaemon/net.py`, `tests/test_network_setting.py`); the social sites are chosen in Settings.

## 2. Social cards

- [ ] 2.1 Port the Reddit feed adapter with rate-limit pacing and cross-post dedupe; verify with recorded feeds and headers Ported (`pipeline/charts/reddit.py`); the recorded-feed test is still to write.
- [ ] 2.2 Port the Hacker News, Bluesky, Mastodon, 4chan and single-post X adapters; verify with recorded responses Ported (`pipeline/charts/social.py`; X and Instagram/Facebook as the pipeline had them); the report card's social test calls each site (`benchmark/probes.py`); recorded-response tests are still to write.
- [ ] 2.3 Draw cards through the chart tool; verify by rendering a fixture card set Ported (the posts chart); a fixture card set is not yet in the chart baseline.

## 3. Real-run evidence

- [ ] 3.1 With the maintainer's go-ahead, run the maintainer's search, summary and social-card dogfood cases through PaperDaemon and record the outcomes and the hosts each job contacted
