# Web search for PaperDaemon: its own SearXNG, or something else?

Research note, 2026-09-26. The measurements were taken on a Windows 11 machine with
Python 3.12, in a throwaway folder, on a test port. An existing SearXNG instance on port 8888 was not
touched. The wider landscape (licenses, terms of service, every search API, with sources) is in
[web-search-sources.md](web-search-sources.md).

## Decision

PaperDaemon does not run SearXNG for anyone. SearXNG is one choice in the search provider dropdown, with a text box for the address of an
instance the user runs themselves. The managed options below (a native copy, or a Docker container
PaperDaemon controls) are not being built. A built-in choice that needs no setup (option B below) is a
stretch goal for later.

## The short answer

There is no longer a free, keyless, official web search API:

- Google's JSON API is closed to new customers, and existing ones are cut off on 2027-01-01.
- Bing's API was retired in August 2025.
- DuckDuckGo does not syndicate its results.
- Brave's free plan now needs a credit card.

So search that works out of the box means scraping search engines, whether SearXNG does it or
PaperDaemon does.

Given that, PaperDaemon can have search that works the moment it is installed, with no Docker and no key.
I got SearXNG itself running natively on Windows. But the better default is a search layer inside
PaperDaemon:

- official sources where they exist: the Wikipedia and Wikimedia APIs for facts, and Openverse and
  Wikimedia Commons for pictures that come with a license
- trafilatura for reading a page's text
- the MIT-licensed `ddgs` library as the fallback for open-web, news and image results

SearXNG stays available two ways:

- an address you point PaperDaemon at, which is what the pipeline does today
- an optional component PaperDaemon downloads and runs for you

The reasons are below; the choice is yours.

## What the host needs from search

Read from the pipeline's host, which is the behavior PaperDaemon v1 has to match:

1. **Web results.** Title and snippet for the top five (`t_web_search`). When a result is a Wikipedia
   article, the host also fetches the first eight sentences of its lead from the MediaWiki API. That
   was added after a snippet stopped one word short of the answer and the model filled the gap
   wrongly.
2. **Pictures.** An image search whose results carry direct image addresses (`_fetch_png`). The host
   downloads the first raster at least 256 px on its short side, skips SVG and GIF, and traces it
   into strokes.
3. **Page text,** for "summarize this link".
4. **Already direct, no SearXNG involved:** Reddit's feeds, the Open-Meteo forecast, Wikipedia's
   on-this-day facts.

So in the pipeline, SearXNG does exactly two jobs: web results and image results.

## What I measured

### SearXNG, run natively on Windows

The checkout was SearXNG's latest commit, 12f8b65 of 2026-09-25.

| Step | Result |
|---|---|
| Get the code | `git clone` fails on Windows: three deployment templates have a colon in their file names (`searxng.conf:socket`). A sparse checkout that skips `utils/templates/` works. (`pip install searxng` is a trap: it installs an unrelated package.) |
| Install | The requirements installed in 3 s from uv's cache, 63 MB. Every compiled dependency has a Windows wheel (`curl_cffi`, `lxml`, `msgspec`). |
| Start | Fails: `searx/valkeydb.py` imports `pwd`, a Unix-only module, at start-up, even with Valkey off. `pwd` is used only on an error path when a Valkey connection fails. A search of SearXNG's code for the usual Unix-only modules and calls found nothing else, though only the web, image and news paths were exercised. |
| Start, with a stand-in | A three-line `pwd` module on the path, with SearXNG's own files unmodified: up in about 2 s, about 80 MB of memory. |
| Web search | 1.3 to 1.6 s, 34 results, from Google's programmable search box and Brave. DuckDuckGo refused with a CAPTCHA. |
| Image search | 1.2 s, 342 results from six engines, Wikimedia Commons among them. |
| News | 0.8 s, 55 results from six engines. |

The "Google" results came from SearXNG's default Google source. Since July 2026 that source uses
Google's embeddable search box under another website's public search ID, with no key. PaperDaemon should
not ship that. SearXNG also sends its requests through `curl_cffi`, which mimics Chrome's network
fingerprint; that is its main defense against being blocked. Reports still show its default engines
blocked after about 70 searches from one address.

### ddgs, inside PaperDaemon's own process

ddgs is at version 9.16.0 (2026-08-26), MIT-licensed, and depends only on click, primp (a Rust HTTP
client that also mimics browsers) and lxml.

| Search | Result (each run includes starting a fresh Python) |
|---|---|
| Web | 1.6 to 3.5 s, 5 results. The Mount Elbert test put Wikipedia first, as SearXNG did. |
| Images | 0.65 s, direct image addresses. |
| News | 0.85 s. |

Its backends are Bing, Brave, DuckDuckGo, Google, Grokipedia, Mojeek, Startpage, Yandex, Yahoo and
Wikipedia, chosen automatically or by name. It also does videos and books.

### Reading a page

- `ddgs extract` returned the whole page, navigation included: 59 KB of markup-like text.
- trafilatura (2.2.0, Apache-2.0) returned the article itself, about 3 s with start-up. The sentence
  that answers "what county is Mount Elbert in" was in it. Published benchmarks also rank it first.

### Licensed pictures, no key

- **Openverse:** 240 Creative Commons results for "red fox" in 1.2 s, with the license on each result.
- **Wikimedia Commons:** the license and full-size originals (up to 6000 x 4000) in 0.5 s.

## The options

**A. PaperDaemon ships SearXNG and runs it for you (the idea).** PaperDaemon keeps a copy of SearXNG,
starts it on a local port as it does model servers, and asks it over HTTP.

- *For:* the broadest metasearch there is, a community that fixes broken engines quickly, and the
  same JSON that the pipeline's host already speaks. It works on Windows with one stand-in module.
- *Against:*
  - **Windows is out of scope upstream.** The maintainers closed a Windows-support pull request in
    July 2025 ("MS-Windows is not in the scope of this project") and point Windows users to Docker.
    PaperDaemon would have to carry the Windows fix itself and re-test every update.
  - **No releases.** There is no package to depend on, so PaperDaemon would bundle a snapshot. That adds
    about 70 MB to an install whose engine is about 130 MB.
  - **A snapshot goes stale in weeks,** and keeping it current means an updater, which would have to be
    opt-in.
  - **Its default Google source borrows another site's search ID.** It would have to be switched off,
    leaving Brave and DuckDuckGo, and DuckDuckGo refused on the first try.
  - **AGPL.**
    - A separate, unmodified program on disk, asked over HTTP, is fine, provided PaperDaemon ships
      SearXNG's source.
    - Importing its code, or freezing it into PaperDaemon's own executable (as a one-file build would),
      makes one combined program under the AGPL.
    - A patched copy must offer its patch.
  - **Another process** on its own port, to start, watch and stop.

**B. Search inside PaperDaemon.** Official sources first: the MediaWiki API for Wikipedia facts and
leads, Openverse and Wikimedia Commons for licensed pictures, Open-Meteo for weather. trafilatura
reads pages. ddgs is the fallback for open-web, news and image results.

- *For:*
  - Ordinary versioned packages: updating is a dependency bump.
  - Windows-native, no port, no process.
  - Permissive licenses (MIT, Apache-2.0).
  - Covers every search the pipeline's host makes.
  - The official sources don't break the way scrapers do.
- *Against:*
  - **ddgs is a scraper too,** and says so: its README calls it "for educational purposes only". It
    breaks and gets refused like SearXNG does.
  - **Its "auto" mode also queries Grokipedia and Yandex,** so PaperDaemon would name its engines.
  - **It never raises its rate-limit error** (a known issue), so PaperDaemon has to pace and cache on its
    own.
  - **Google, Microsoft and Mojeek forbid automated queries in their terms,** and Brave fights them
    with proof-of-work CAPTCHAs. DuckDuckGo's terms say nothing. DuckDuckGo plus Wikipedia is the
    least conflicting default.
  - **Google News and Bing News feeds restrict themselves** to personal feed readers, so news should
    come through ddgs rather than those feeds.

**C. Bring your own.** The address of a SearXNG you already run, or a key for a
search API. Tavily and Exa have monthly free allowances without a card; Brave now needs one. Most
reliable, but it needs setup, so it cannot be the default for a published app.

**D. The model provider's own search.** Anthropic, OpenAI and Google offer web search for their own
models only; nothing like it works with a local model.

- Anthropic's search gives the host titles and addresses but not readable snippets, since the
  content comes back encrypted for the model. Its web fetch does return a page's text.
- Gemini's grounding must be shown with Google's search suggestions.

At most an extra for cloud text slots.

**E. Offline.** Wikipedia from Kiwix answers facts with no network at all, but nothing current: 13 GB
for article introductions, 49 GB without pictures, 119 GB with them. Kiwix's library is GPL-3.0, so
it too would run as a separate program. A niche extra.

## Recommendation

1. **Default: B, built in.** Search works on first start with no setup.
   - Official sources first: Wikipedia leads and facts from the MediaWiki API, with a descriptive
     User-Agent that names the project and its repository, since unidentified clients now get 10
     requests a minute.
   - ddgs for the open web, pinned to DuckDuckGo and Wikipedia by default. Every other engine is
     listed with a note on its terms, and each can be switched on or off.
   - Searches paced and cached, and trafilatura for page text.
2. **Keep SearXNG as a first-class choice** for people who want its breadth.
   - First, an address, which is what you run today.
   - Second, an optional "run SearXNG for me" component that downloads a pinned, tested snapshot and
     runs it as its own process, with PaperDaemon carrying the Windows fix and the AGPL kept at the
     process boundary. That component is your idea, offered where its costs are opted into.
3. **Keys for search APIs** as a reliability upgrade.
4. **Pictures:** try Openverse and Wikimedia Commons before general image search, so a picture PaperDaemon
   draws on your page comes with a known license, and the job records where it came from. This
   changes the pipeline's behavior slightly, so it is a setting, off by default for parity.
5. **Declared hosts:** the search settings list every engine and host PaperDaemon can contact, each with a
   switch, and say plainly that a search sends words from your page to those hosts.

## A heads-up about the pipeline (nothing was changed)

The pipeline's on-this-day facts (`rm_history.py`) call `api.wikimedia.org/feed/v1/...`. Wikimedia is
retiring those endpoints gradually from July 2026 to June 2027, so the call will stop working at some
point. The same feed is served at `https://en.wikipedia.org/api/rest_v1/feed/onthisday/{type}/{mm}/{dd}`.
Wikimedia also now limits unidentified clients to 10 requests a minute, and wants a User-Agent with
contact details. That is plenty for one person's jobs.

## If you agree: what changes in the specs

The add-web-search change would gain:

- A requirement that search works with no setup, through the built-in provider, whose engines are
  listed and switchable.
- The provider list: built in (default), a SearXNG address, a managed SearXNG (optional download),
  and API providers.
- Official-source rules: a descriptive User-Agent, pacing and caching.
- Page text through trafilatura, and an optional licensed-pictures-first setting.

Nothing is changed until you choose.

## Open questions

- Built-in library or managed SearXNG as the default. The one choice that matters here.
- Whether the built-in engine list starts with only DuckDuckGo and Wikipedia (least conflict with
  published terms), or also switches on engines whose terms forbid automated queries.
- Licensed pictures first: a setting, or the default.
