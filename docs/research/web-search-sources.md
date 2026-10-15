# Web search sources for PaperDaemon

Research note, checked 2026-09-26. Desk research only: web searches and fetched pages. Nothing was
installed or run, and no local service was contacted. Facts are as of 2026-09-26 unless a date is
given. Anything I could not confirm from a primary source is marked *(unverified)*. The companion
note [web-search.md](web-search.md) has hands-on measurements on Windows; this note is the wider
landscape, with sources.

The host's needs, as abbreviated in the tables: **W** web results (title, URL and snippet for the top
five), **I** image search that returns direct URLs of raster pictures, **P** a page's main text,
**F** Wikipedia leads for facts, **N** news.

## Recommendation

No free, keyless, official web search API remains in 2026: Google's JSON API is closed to new
customers, Bing's was retired in August 2025, DuckDuckGo does not syndicate its results, and Brave's
free plan became a monthly credit that needs a credit card. So the best out-of-the-box search is
built into PaperDaemon, with no Docker and no key: the MediaWiki APIs for Wikipedia leads, Wikimedia
Commons and Openverse for licensed raster pictures, trafilatura (Apache-2.0, run locally) for page
text, and the MIT-licensed `ddgs` library, in-process, as the fallback for open-web text and image
results. Pin `ddgs` to a short engine list the user can see and switch off (DuckDuckGo and Wikipedia
conflict least with published terms; Google, Microsoft and Mojeek forbid automated queries), throttle
and cache it, and describe it plainly as an unofficial scraper that will sometimes break. Anything
that needs setup is an opt-in upgrade: the user's own key for an official API (Tavily and Exa have
monthly free allowances without a card), the model provider's own search when the user runs Claude,
GPT or Gemini, a SearXNG address the user already runs, or an offline Kiwix Wikipedia. Bundling
SearXNG is the weakest default: AGPL (workable only as a separate process), no Windows support
upstream, no releases, and engines that go stale within weeks.

## Comparison table

| Option | Covers | Key or payment | License or terms that matter | Status on 2026-09-26 |
|---|---|---|---|---|
| **Self-hosted metasearch and engines** | | | | |
| SearXNG | W I N | None | AGPL-3.0-or-later; a separate process is an aggregate, imported code is a combined work | Rolling, no releases; Windows unsupported upstream; default engines often blocked from one IP |
| Whoogle | W (Google only) | None | MIT | Archived 2026-08-14: "no longer returns search results" |
| 4get | W I N | None | AGPL-3.0-only (PHP) | Active (commit 2026-09-22); Linux PHP stack only |
| LibreY | W I | None | AGPL-3.0 (PHP) | Last code changes in 2025; 2026 commits only edit the instance list |
| YaCy | W (own peer-to-peer index) | None | GPL-2.0-or-later (Java 17+) | Active; 1.942 (2026-08-15) has a Windows installer |
| Stract | W (own index) | None | AGPL-3.0 (Rust) | Repository archived 2026-04-02; stract.com still loads |
| Marginalia | W (own "small web" index) | Key: shared "public" test key, free non-commercial key by email, paid commercial | Code AGPL-3.0 with exceptions; non-commercial results CC BY-NC-SA 4.0 | Active; self-hosting needs a large server |
| **In-process library** | | | | |
| ddgs | W I N P | None | MIT; scrapes engines whose terms mostly forbid it; README says "for educational purposes only" | 9.16.0 (2026-08-26); Windows, macOS and Linux wheels |
| **Search APIs** | | | | |
| Brave Search API | W I N | Key and credit card; a monthly free credit (about 1,000 searches) | Transient storage only; "Powered by Brave" attribution; key not shareable | Free plan ended 2026-02-12 |
| Mojeek API | W | Key; paid only, limited free trial | May store results 1 hour on basic plans | Active |
| Tavily | W P | Key; 1,000 free credits a month, no card | Key may not be shared; no resale | Owned by Nebius since 2026-02 |
| Exa | W P | Key; a free credit, reset monthly | Terms not reviewed *(unverified)* | Active |
| Serper (Google results) | W I N | Key; 2,500 free queries once, no card | "Business-to-business service"; no consumer services | Active |
| SerpAPI | W I N | Key; 250 free searches a month | Legal shield only on paid plans | Active |
| Jina Search (s.jina.ai) | W | Key (free starter tokens) | No restrictions on output, except building a competing service | Part of Elastic since 2025-10 |
| Jina Reader (r.jina.ai) | P | None at 20 requests a minute; free key for 500 | Same terms; every URL read goes to Jina's servers | Active |
| Kagi Search API | W | Key; paid only | Terms not found *(unverified)* | Active |
| Perplexity Search API and Sonar | W (Sonar returns answers) | Key; paid only | Perplexity may keep and use search data *(unverified: snippet only)* | Active |
| Google Programmable Search JSON API | W I | Closed to new customers | n/a | Existing customers cut off 2027-01-01 |
| Bing Search APIs | none | Retired | n/a | Retired 2025-08-11 |
| **Provider-native tools** | | | | |
| Anthropic web search | W (URL, title, page age; content encrypted) | Claude API key; paid per search | Claude models only; citations must be shown | Current version `web_search_20260318` |
| Anthropic web fetch | P (full text returned) | Claude API key; tokens only | Claude models only; fetches only URLs already in the conversation | Not on Bedrock or Google Cloud |
| OpenAI web search | W (source URLs and citations) | OpenAI key; paid per call | OpenAI models only | Responses API tool |
| Gemini grounding with Google Search | W (citations) | Gemini key; free allowance, then paid | Gemini only; Search Suggestions must be shown; no caching | Current |
| **Official free sources** | | | | |
| MediaWiki APIs (Wikipedia) | F, and W for encyclopedic queries | None; a descriptive User-Agent | Content CC BY-SA; 10 requests a minute unidentified, 200 with a compliant User-Agent | Global limits new in 2026; api.wikimedia.org being phased out |
| Wikimedia Commons | I | None | License per file, in the metadata; standard thumbnail widths only | Stable |
| Openverse | I | None for light use; free registration for more | No scraping; attribute CC works | Stable |
| Google News RSS | N | None | Feed notice: personal, non-commercial feed-reader use only | Works (checked); undocumented |
| Bing News RSS | N | None | Same restriction in the feed | Works, few items (checked) |
| Open-Meteo | weather | None | Non-commercial use; CC BY 4.0 attribution; under 10,000 calls a day | Stable |
| **Local tools** | | | | |
| trafilatura | P | None (local) | Apache-2.0 | 2.2.0 (2026-07-31); best F1 in published benchmarks |
| readability-lxml | P | None (local) | Apache-2.0 | 0.9 (2026-08-27) |
| Kiwix ZIM files with libzim or kiwix-serve | F offline | None (13 to 119 GB download) | Content CC BY-SA; libzim and kiwix-tools GPL-3.0 | Rebuilt every few months |

## 1. SearXNG

### License, and what shipping it with PaperDaemon means

SearXNG is licensed AGPL-3.0-or-later (README, LICENSE file, and `license` in its `setup.py`). The
AGPL is the GPLv3 plus section 13, which reads in part: "if you modify the Program, your modified
version must prominently offer all users interacting with it remotely through a computer network (if
your version supports such interaction) an opportunity to receive the Corresponding Source of your
version by providing access to the Corresponding Source from a network server at no charge."

What that means for PaperDaemon (a reading of the license texts, not legal advice):

- **Section 13 adds duties only for a modified SearXNG.** Unmodified, it adds nothing. A patched
  copy (for example a Windows fix) must offer its source to the people who interact with it over a
  network; publishing the patch in PaperDaemon's public repository and linking it from the app covers
  that.
- **Putting SearXNG in PaperDaemon's installer is conveying it.** Section 0: "To 'convey' a work means
  any kind of propagation that enables other parties to make or receive copies. Mere interaction
  with a user through a computer network, with no transfer of a copy, is not conveying." Conveying
  brings the ordinary duties of sections 4 to 6: include the license, keep the notices, and provide
  the Corresponding Source. SearXNG is Python, so shipping its source tree covers most of that; if
  it were frozen into bytecode or an executable, the source would have to be offered alongside.
- **Mere aggregation.** Section 5: "A compilation of a covered work with other separate and
  independent works, which are not by their nature extensions of the covered work, and which are not
  combined with it such as to form a larger program, in or on a volume of a storage or distribution
  medium, is called an 'aggregate' ... Inclusion of a covered work in an aggregate does not cause
  this License to apply to the other parts of the aggregate."
- **Where the line falls.** The FSF's GPL FAQ (entry "MereAggregation") says the test is both the
  mechanism and the semantics of communication. Modules in the same executable are "definitely
  combined in one program"; modules linked in a shared address space almost surely are; "pipes,
  sockets and command-line arguments are communication mechanisms normally used between two separate
  programs," unless "the semantics of the communication are intimate enough, exchanging complex
  internal data structures." (gnu.org rate-limited every fetch. A search index confirmed the
  mechanism-and-semantics test and the last quoted sentence; the other phrases are quoted from the
  FAQ as previously published *(unverified today)*.)
- **So:** SearXNG running as its own process, asked through its public HTTP JSON API, is an
  aggregate, and PaperDaemon can carry any license. Importing `searx` modules into PaperDaemon's process, or
  freezing them into PaperDaemon's executable (a PyInstaller one-file build, say), makes one combined
  program, which must then be distributed under the AGPL-3.0. Section 13 also allows combining with
  GPLv3 code, so if PaperDaemon itself chose the AGPL-3.0 or GPL-3.0 the question largely goes away.

### Windows

- **Not supported natively.** In discussion #4029 (2024-11-22) a maintainer wrote that SearXNG does
  "not really support" Windows natively, its focus being Linux and Unix, and pointed Windows users to
  the Docker image.
- **A Windows-support pull request was declined.** PR #5067 (rename files with colons in their
  names, use winloop instead of uvloop, adapt multiprocessing) was closed unmerged on 2025-07-29. A
  maintainer: "MS-Windows is not in the scope of this project," citing the cost of porting the
  developer environment and quality assurance. The related discussion #4486 records CSS and template
  loading problems and fork-based multiprocessing as blockers.
- **Official install docs cover Linux only** (Ubuntu and Debian, Arch, Fedora and RHEL). macOS is not
  documented *(unverified whether it runs there from source)*.
- **Community workaround:** the `searxng-windows` project (MIT scripts) downloads upstream SearXNG,
  applies a Windows compatibility patch automatically, needs Python 3.11 or 3.12 x64, and disables
  DuckDuckGo in its template because shared traffic "frequently triggers CAPTCHA challenges."
- **Measured in the companion note** (commit 12f8b65 of 2026-09-25, not re-checked here): `git clone`
  fails on Windows because three templates have a colon in their file names, and start-up fails
  because `searx/valkeydb.py` imports the Unix-only `pwd` module even with Valkey off.

### Installation

- **Official methods:** the container image, an installation script, or step-by-step (Linux). The
  step-by-step path clones the git repository into a virtual environment and runs
  `pip install --use-pep517 --no-build-isolation -e .`.
- **No releases.** The GitHub releases page says "There aren't any releases here." The container
  image `searxng/searxng` (Docker Hub and GHCR) is tagged by date and commit (for example
  `2026.9.25-12f8b6515`) for amd64, arm64 and armv7.
- **Not on PyPI.** `setup.py` names the package `searxng` (Python 3.10 or later, entry point
  `searxng-run`), but the project does not publish it. The PyPI project called `searxng` is an
  unrelated third-party MCP server (0.1.2, 2026-09-09) that sends queries to a SearXNG instance, by
  default a public one. `pip install searxng` does not install SearXNG.

### Dependencies that need compiling

`requirements.txt` pins 17 packages: certifi, babel, flask-babel, flask, jinja2, lxml 6.1.3, pygments,
python-dateutil, pyyaml 6.0.3, curl_cffi 0.16.3, valkey 6.1.1, markdown-it-py, msgspec 0.21.1,
typer, isodate, whitenoise, typing-extensions. Four have compiled parts, and all four publish wheels
for Python 3.12 on Windows x64:

| Package | Windows | macOS | Linux |
|---|---|---|---|
| lxml 6.1.3 | cp312 win_amd64, win_arm64, win32 | universal2 and x86_64 | manylinux |
| curl_cffi 0.16.3 (bundles curl-impersonate) | abi3 win_amd64; no ARM64 wheel | x86_64 and arm64 | manylinux and musllinux |
| msgspec 0.21.1 | cp312 win_amd64 | x86_64 and arm64 | manylinux |
| PyYAML 6.0.3 | cp312 win_amd64 and win32; no ARM64 wheel | x86_64 and arm64 | manylinux and musllinux |

The rest are pure Python (`valkey` is only the client library). Nothing needs a compiler on Windows
x64; on Windows on ARM, curl_cffi and PyYAML would have to be built from source.

### A private single-user instance: Valkey and the limiter

- The default `settings.yml` has `server.limiter: false`, `server.public_instance: false`,
  `server.image_proxy: false` and `valkey.url: false`. The docs say "The limiter requires a Valkey
  database." A private instance bound to 127.0.0.1 therefore runs without Valkey or Redis and
  without the limiter.
- `server.secret_key` must be changed from the shipped `ultrasecretkey`; the server refuses to start
  with it *(unverified against current code; the error message is documented in the project's issue
  history)*.
- JSON output is off by default: `search.formats` is `[html]`, so `json` must be added.

### JSON API and image search

- `GET /search?q=...&format=json` (POST works too, as does `/`). Parameters: `q`, `categories`,
  `engines`, `language`, `pageno`, `time_range` (`day`, `month`, `year`), `safesearch` (0, 1, 2).
  "Format needs to be activated in search:"; asking for an unset format returns 403 Forbidden.
- Each result has `title`, `url`, `content` (the snippet) and the engines that returned it. Image
  results add `img_src` (full-size image), `thumbnail_src`, `resolution`, `img_format`, `source` and
  `filesize`.
- The Wikipedia engine defaults to `display_type: ["infobox"]`, so in JSON it arrives as an infobox,
  not in the results list.
- Image engines on by default: Bing Images, DuckDuckGo Images, Brave Images, Google CSE Images and
  Wikimedia Commons. Off by default: Google Images, Qwant Images, Openverse, Flickr. Pexels and
  Unsplash moved to a separate "stock images" category (PR #6690 and #6703, merged 2026-09-20).

### How reliable the main engines are from one home IP in 2026

The default general engines are DuckDuckGo, Brave, Google CSE and Wikipedia (plus Wikidata and
utilities). Most public reports come from homelab instances that do not say whether the IP is
residential *(unverified which)*.

| Engine | Default | 2026 evidence |
|---|---|---|
| Google | `google` disabled; `google cse` on | Google has required JavaScript for search since January 2025. SearXNG's engine requests an XML layout with Nokia user agents, and broke again with CAPTCHAs in April 2026 (#5958, fixed). Since 2026-07-05 the default Google source is `google cse`, which calls Google's Custom Search Element without a key, using another website's (blackle.com's) public search-engine ID. A user calls its results "borderline unusable" (#6524, closed as not planned). |
| Bing | web disabled; images on | Long-running relevance complaints (#4964). A self-hosted instance on 2026-09-23 had Bing as its only working engine, with "mojeek 403, presearch 530, brave 429, duckduckgo and startpage CAPTCHA." |
| DuckDuckGo | on | CAPTCHA on every request in August (#6596), fixed on 2026-09-04 by browser impersonation; new CAPTCHA report with the default "all" language on 2026-09-24 (#6779, open). |
| Brave | on | "Too many requests" suspensions in several 2026 reports. Brave runs proof-of-work CAPTCHAs to make scraping expensive. |
| Startpage | `inactive` | Anubis proof-of-work challenge; "there is no way to get around this with any impersonate." Marked inactive 2026-09-10 (#6669, after #6520). |
| Mojeek | `inactive` | The settings comment: it "uses a Proof of Work CAPTCHA that requires much computer power to solve." A user reported Mojeek CAPTCHAs, then block pages, around June 2026. |
| Qwant | disabled | Access-denied and CAPTCHA reports (#6776). |
| Wikipedia | on | Official API; reliable. |

Volume matters. A single-IP test published 2026-07-22 (by a vendor of a competing paid API, so
discount accordingly) got results only from DuckDuckGo: "Google returned zero parseable results,
Brave and Startpage were suspended." A third-party project saw all three default web engines blocked
from one IP after about 70 searches (2026-09-25). A lab's notes (2026-05-07) found 20 to 40 queries
with 3-second gaps stable, and CAPTCHAs beyond that. The maintainers acknowledge "the ongoing
problems with the major web search providers" and are weighing real-browser solutions (discussion
#5651).

### Release cadence and how often engines break

- Rolling release: the version is the date plus a commit (the docs read `2026.9.25+12f8b6515`).
  Docker Hub shows three builds on 2026-09-25 and three on 2026-09-23.
- Engine-affecting changes in the last three months: Google CSE engine added (2026-07-05), new
  Google user agent (2026-08-22), the whole HTTP layer moved from httpx to curl_cffi to mimic
  Chrome's TLS fingerprint (2026-09-04), Startpage made inactive (2026-09-10), image defaults
  reshuffled (2026-09-20), a new DuckDuckGo CAPTCHA report (2026-09-24). A bundled snapshot would
  need updating every few weeks to keep its engines answering.

## 2. Libraries that do metasearch in-process

### ddgs (formerly duckduckgo_search)

- **Name and history.** `duckduckgo_search` stopped at 8.1.1 in July 2025; its PyPI page states that it
  "has been renamed to `ddgs`."
- **License and version.** MIT. 9.16.0, released 2026-08-26; Python 3.10 to 3.14; classified
  Production/Stable. Fourteen releases between 2026-03-11 and 2026-08-26; about 3,000 GitHub stars;
  published by a single author.
- **Dependencies.** click, primp and lxml; optional FastAPI and uvicorn for the API server, and
  `mcp` for the MCP server. primp is a Rust HTTP client that impersonates browsers (MIT, 2.0.1 on
  2026-09-13), with abi3 wheels for Windows x64, macOS (Intel and Apple silicon) and Linux (x86_64
  and aarch64), but none for Windows on ARM.
- **Backends.** Text: Bing, Brave, DuckDuckGo, Google, Grokipedia, Mojeek, Startpage, Yandex, Yahoo,
  Wikipedia. Images: Bing, DuckDuckGo. Videos: DuckDuckGo. News: Bing, DuckDuckGo, Yahoo. Books:
  Anna's Archive. `extract()` fetches a page as Markdown, plain text, rich text or raw HTML.
- **Results.** Text: `title`, `href`, `body`. Images: `title`, `image` (direct URL), `thumbnail`,
  `url` (the page), `height`, `width`, `source`.
- **`backend="auto"`.** Text search puts Wikipedia and Grokipedia first, then the other engines by
  priority with random tie-breaks; several run at once, and results are deduplicated and ranked.
  Default timeout 5 seconds; http, https and socks5 proxies, also through `DDGS_PROXY`.
- **CLI.** `ddgs` has search commands, `ddgs extract`, `ddgs api` (a local FastAPI server) and
  `ddgs mcp` (a stdio MCP server).
- **Rate limiting.** None built in. `RatelimitException` is defined but never raised, so rate limits
  arrive as a generic `DDGSException` (#478, open since 2026-07-04). DuckDuckGo news returning 403 is
  also open (#480, 2026-07-25).
- **For PaperDaemon.** Always pass `backend=` explicitly: "auto" contacts engines the user never chose
  (Grokipedia, Yandex and others). The README's disclaimer reads "This
  library is for educational purposes only."

### Others worth knowing

- **curl_cffi** (MIT) and **primp** (MIT): the browser-impersonating HTTP clients behind SearXNG and
  ddgs. Mimicking a browser's TLS fingerprint is why both still get answers.
- **open-webSearch** (Apache-2.0, TypeScript): a keyless multi-engine MCP server, CLI and daemon
  (Bing, DuckDuckGo, Brave, Startpage, Exa, Baidu and others), in plain HTTP or Playwright mode. It
  needs Node, so it cannot run inside PaperDaemon's Python process.
- **googlesearch-python** (MIT, 1.3.0 of 2025-01-21) and **icrawler** (MIT, 0.6.10 of 2025-02-11,
  image crawlers for Google, Bing, Baidu and Flickr): no release since Google began requiring
  JavaScript in January 2025. Whether they still work is *(unverified)*.

## 3. Other self-hostable engines

| Engine | License | Own index | Windows | Status and reliability |
|---|---|---|---|---|
| Whoogle | MIT | No; proxies Google | pip or Docker | Archived 2026-08-14. README: "Whoogle no longer returns search results, and that isn't something this project can fix," after Google blocked non-JavaScript queries. Final release v1.2.4, "End of an Era," in April (2026 by the release order; year inferred). |
| Stract | AGPL-3.0 | Yes, its own crawler and index | Rust; not documented | Repository archived 2026-04-02; stract.com still loaded on 2026-09-26. |
| 4get | AGPL-3.0-only | No; scrapes DuckDuckGo, Brave, Google, Yandex, Mojeek, Marginalia, Wiby, Startpage and more | No; the docs cover Debian with Apache or nginx, PHP 8, php-curl, APCu and Imagick | Active (commit 2026-09-22). Has an API. |
| LibreY | AGPL-3.0 | No; Google, DuckDuckGo, Brave, Ecosia, Yandex and Mojeek for text, Qwant for images | PHP or Docker | Low activity: last code changes in 2025, and the 2026 commits (latest 2026-06-10) only prune the instance list. Has an API. |
| YaCy | GPL-2.0-or-later | Yes, peer-to-peer, or local only | Java 17+; NSIS Windows installer | Active (commits 2026-09-23; 1.942 released 2026-08-15). HTTP JSON and XML APIs. Coverage depends on what peers have crawled, so general queries return sparse results *(unverified; my assessment, not measured)*. |
| Marginalia | AGPL-3.0 with exceptions, parts MIT | Yes, focused on the non-commercial "small web" | Java; not documented | Active. Self-hosting needs "a lot of RAM," enterprise SSDs and terabytes of disk (at least a 32 GB machine). Its API (`api2.marginalia-search.com`, key in an `API-Key` header) has a shared "public" key that "often hits a rate limit," free non-commercial keys by email with results under CC BY-NC-SA 4.0, and paid commercial keys. |

## 4. Search APIs

An API key belongs to one customer, and several of these terms forbid sharing it. A published app
cannot ship a key of its own; every API here means the user brings their own (kept in
the OS credential store).

- **Brave Search API.** Key, and a credit card even for the free credit ("an anti-fraud measure ...
  For free plans, the card is only used to confirm your identity and will not be charged"). Every
  plan includes a monthly free credit, about 1,000 searches, which Brave says requires
  attributing Brave on the project's site; the 2,000-query free plan ended on 2026-02-12. Endpoints:
  web, images, videos, news, suggest, spellcheck, LLM context and answers. Terms (effective
  2026-09-01): no storing or caching "other than transient storage required for operation of
  Customer Applications"; longer storage needs a plan with storage rights; the key may not be shared
  beyond affiliates, contractors and agents; "POWERED BY BRAVE" and the logo must be shown; the API
  may not be sublicensed.
- **Mojeek API.** Key; paid only (credit-based), with a "Free trial version, with limited queries."
  Web results only: URL, title and query-dependent snippets. Results may be stored for 1 hour on
  basic plans, longer on plans with storage rights; combining with other engines and use for AI are
  allowed.
- **Tavily.** Key; the free Researcher plan gives 1,000 credits a month with "No credit card
  required," pay-as-you-go beyond. Search, extract, research, crawl and map endpoints. Terms
  (2026-05-04): the key "may not be transferred, assigned, shared, or otherwise made available to any
  third party"; no resale or sublicensing; no explicit caching clause found. Nebius agreed to buy
  Tavily on 2026-02-10 and completed the purchase on 2026-02-19.
- **Exa.** Key; the free tier is a credit at sign-up that resets on the first of
  every month, with no payment method needed. Products:
  Search, Contents, Answer, Monitors, Agent and Deep Search. The terms are a PDF I could not read
  *(unverified)*.
- **Serper.** Key; 2,500 free queries once, no credit card. Google results for web, images, news,
  maps, places, videos, shopping, scholar and patents. Terms (2024-05-29): "Serper is a
  business-to-business service and does not provide end-user (consumer) services"; no mirroring
  "as-is with no-value-added"; one account per person.
- **SerpAPI.** Key; free plan of 250 searches a month, and cached searches are not counted. Terms
  (2026-08-27): search data is kept 31 days unless ZeroTrace mode is used; its "legal shield"
  (SerpApi assumes the scraping liability) covers paid recurring plans only.
- **Jina (part of Elastic since 2025-10-09).** `s.jina.ai` search needs a key (a free key allows 100
  requests a minute; each search costs a fixed token amount "starting from 10,000 tokens"); new keys
  come with free tokens, amount not stated. `r.jina.ai` reader works with no key at 20 requests a
  minute, 500 with a free key. Terms (2026-05-04): Jina "claims no rights to such Output and imposes
  no restrictions on the Customer regarding the use of the Output," except using it to build competing
  services; input and output are stored only as needed and not used for training. Every URL read
  through the reader goes to Jina's servers.
- **Kagi Search API.** Key from a Kagi account; paid only, per request (search and extract APIs
  listed). No free tier. I found no API-specific terms *(unverified)*.
- **Perplexity.** The Sonar models return answers with citations (an LLM with search); the Search API
  returns ranked results with title, URL, snippet and dates. Both need a key and are paid only; no
  free tier is documented. The Search addendum reportedly lets Perplexity retain and use search data
  *(unverified: the page returned 403; from a search-result snippet)*.
- **Google Programmable Search (Custom Search JSON API).** "The Custom Search JSON API is closed to
  new customers." Existing customers "have until January 1, 2027 to transition to an alternative
  solution." Google points to Vertex AI Search (up to 50 domains) or a sales contact for full web
  search.
- **Bing Search APIs.** Retired on 2025-08-11 and "decommissioned completely." Microsoft's replacement,
  Grounding with Bing Search, works only inside Azure AI Agents.

## 5. Terms of service on automated querying

- **DuckDuckGo.** The terms (dated "01-07-2025" on the page) never mention bots or scraping.
  Authorization requires following the terms and the Acceptable Use Policy, which forbids selling or
  reselling "any portion of the services" and unauthorized access. `robots.txt` disallows `/html` and
  `/lite`, the no-JavaScript pages scrapers use. There is no results API: the Instant Answer API
  excludes normal results. DuckDuckGo's partnerships page says "We simply don't have the rights to
  allow framing based on how we generate our search results"; its API page adds that it cannot fully
  syndicate results, free or paid, but that page is script-rendered and I saw the wording only in
  search snippets *(unverified)*. So automated querying is not expressly banned, but not authorized
  either, and DuckDuckGo blocks it with CAPTCHAs and 403s.
- **Google.** Terms effective 2026-07-30 forbid "using automated means to access content from any of
  our services in violation of the machine-readable instructions on our web pages (for example,
  robots.txt files that disallow crawling, training, or other activities)." `robots.txt` has
  `Disallow: /search`. Automated querying of Google Search breaks the terms.
- **Bing (Microsoft Services Agreement, effective 2025-09-30).** "Don't circumvent any restrictions on
  access to, usage, or availability of the Services (e.g., attempting to 'jailbreak' an AI system or
  impermissible scraping)." Bing and MSN material is "for your noncommercial, personal use only."
  `robots.txt` disallows `/search` and `/images/search`. With the API retired, there is no sanctioned
  programmatic route outside Azure.
- **Brave.** The general Terms of Use (last updated 2023-05-11) have no scraping clause, but forbid
  any action that imposes "an unreasonable or disproportionately large load" or interferes with the
  service. `search.brave.com/robots.txt` disallows `/search`, `/images`, `/news` and `/api`. Brave
  says its proof-of-work CAPTCHAs exist to make it "expensive for bots to scrape Brave Search." The
  paid API is the sanctioned route.
- **Mojeek.** Section 3.5 of its terms forbids using or accessing the services "by any automated
  means" unless you are an API customer, and states that "scraping the Services without Our prior
  consent is expressly prohibited" (crawling that follows `robots.txt` is allowed). `robots.txt`
  disallows `/search`.

For PaperDaemon: of `ddgs`'s text engines, only Wikipedia (an official API) is clean. DuckDuckGo is the
least-conflicting scraped engine, since its terms say nothing explicit. Google, Bing and Mojeek
forbid automated queries outright, and Brave works against them. Yandex, Yahoo and Startpage terms
were not reviewed *(unverified)*.

## 6. Official free sources that cover part of the need

### Wikipedia and the MediaWiki APIs

- **Leads.** Action API with TextExtracts:
  `https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&titles=...`.
  `exchars` takes 1 to 1,200; `exsentences` takes 1 to 10, but the extension's docs caution against
  it for edge cases (the pipeline's host uses `exsentences=8`); up to 20 extracts per request when `exintro`
  is set.
- **Search.** REST: `https://en.wikipedia.org/w/rest.php/v1/search/page?q=...&limit=5` returns `title`,
  `excerpt` (with the search terms marked), `description` and a `thumbnail`. The older
  `/api/rest_v1/page/summary/{title}` lives in RESTBase, which is being sunset endpoint by endpoint;
  I found no deprecation of `summary` itself *(unverified)*.
- **User-Agent policy** (moved to the Wikimedia Foundation governance wiki, edited 2026-03-27): the
  format is `<client name>/<version> (<contact information>) <library/framework name>/<version>`,
  where contact is a URL, an email address or a wiki user. Generic or missing agents "may be blocked
  without notice." Browser JavaScript uses the `Api-User-Agent` header instead. For a published app,
  the repository URL is a suitable contact, rather than a person's email.
- **Global rate limits, new in 2026** (announced in Tech News in March 2026; page edited
  2026-06-03): 10 requests a minute for unidentified clients, 200 for a compliant User-Agent, 2,000
  for established editors, across both the Action and REST APIs, "subject to experimentation and
  change." How requests from one install are counted (per IP, per agent) is not documented
  *(unverified)*.
- **Etiquette.** Requests in series, not in parallel; `Accept-Encoding: gzip`; cache what can be
  cached; `maxlag` for non-interactive work.
- **The API Portal is going away.** Its documentation wiki went read-only on 2026-06-15, and the
  `api.wikimedia.org` endpoints are being deprecated gradually from July 2026 to June 2027. The pipeline's
  on-this-day call uses `api.wikimedia.org/feed/v1/...`; the per-wiki Wikifeeds path
  `/api/rest_v1/feed/onthisday/{type}/{mm}/{dd}` serves the same feed.

### Wikimedia Commons

- Keyless, through the same Action API on `commons.wikimedia.org`: `generator=search` in the File
  namespace (6) with `prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=...`. SearXNG's
  Commons engine uses the same approach with a `filetype:` filter. `extmetadata` carries each file's
  license and author.
- **Standard thumbnail sizes only:** 20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920 and 3840 px.
  Hand-built thumbnail URLs at other widths are rejected (task T414805; non-browser clients were
  rate-limited first); the API rounds `iiurlwidth` up to the next standard size.
- For tracing: request a standard width such as 960 or 1280 and filter on `mime`; SVG files also get
  raster PNG thumbnails.

### Openverse

- CC-licensed and public-domain images, aggregated from many sites.
  `https://api.openverse.org/v1/images/?q=...` returns `url` (direct image), `thumbnail`, `license`,
  `license_version`, `creator`, `foreign_landing_url`, `filetype` and a ready-made `attribution`
  string.
- **Anonymous access is allowed:** "Anonymous requests should be sufficient for most users. Indeed,
  https://openverse.org itself operates using anonymous requests from the browser." Limits come back
  in response headers. Anonymous requests are also limited in page size (reportedly the default 20)
  and pagination depth (reportedly 240 results). The published source code's defaults for anonymous
  clients are 5 requests an hour burst and 100 a day sustained; production values are set by
  environment and not published *(unverified)*.
- **Free registration** (OAuth2 client credentials, after email verification) raises the code's
  defaults to 100 a minute and 10,000 a day.
- **Terms:** "You must not scrape the content in the Openverse catalog," no multiple machines to dodge
  limits, and give proper attribution to CC-licensed works.

### Google News and Bing News RSS

- **Google News:** `https://news.google.com/rss/search?q=...&hl=en-US&gl=US&ceid=US:en` worked on
  2026-09-26 (100 items; title, link, date, source). Links are `news.google.com` redirect URLs. The
  feed states: "This XML feed is made available solely for the purpose of rendering Google News
  results within a personal feed reader for personal, non-commercial use." Undocumented; no API
  status.
- **Bing News:** `https://www.bing.com/news/search?q=...&format=rss` worked on 2026-09-26 but returned
  one item for the test query; items carry a thumbnail and `bing.com/news/apiclick.aspx` redirect
  links. The feed states the results "may not be used, reproduced or transmitted in any manner or for
  any purpose other than rendering Bing results within an RSS aggregator for your personal,
  non-commercial use."
- PaperDaemon acting as a user's own reader arguably fits both notices; that is a gray area, not a grant.

### Open-Meteo

No key for non-commercial use: under 10,000 calls a day, 5,000 an hour, 600 a minute and 300,000 a
month. Non-commercial covers personal home automation, private and non-profit sites without ads or
subscriptions, public research and education. The data is CC BY 4.0, so attribution is required;
the server code is AGPLv3.
Commercial use needs a paid plan with its own key and endpoint.

## 7. Provider-native search tools

All three run on the provider's servers and work only with that provider's models. None helps a local
model.

### Anthropic: web search and web fetch

- **Web search.** Versions `web_search_20250305` (basic), `web_search_20260209` (adds dynamic
  filtering: Claude runs code to filter results before they enter the context) and
  `web_search_20260318` (adds `response_inclusion`). Options: `max_uses`, `allowed_domains` or
  `blocked_domains`, `user_location`. Paid per search on top of tokens; failed searches are not
  billed. Organization admins can turn it off in the Claude Console.
- **What comes back to the caller:** a `web_search_tool_result` with each result's `url`, `title`,
  `page_age` and `encrypted_content`, which must be passed back unchanged on later turns. The page
  content itself is encrypted, so the host gets URLs and titles but no readable snippets; the only
  plain text is in citations (`cited_text`, up to 150 characters). Citations are always on, and "When
  displaying API outputs directly to end users, citations must be included to the original source."
- **Web fetch.** Versions `web_fetch_20250910` (basic) up to `web_fetch_20260318`. No charge beyond
  tokens. The caller receives the full text (`web_fetch_result` holding a `document` with the text, or
  base64 for a PDF, and `retrieved_at`). It fetches only URLs already in the conversation (user
  messages, client tool results, earlier search or fetch results), not ones found only in the system
  prompt; it refuses private addresses and URLs blocked by `robots.txt`; it does not run JavaScript;
  it handles text, HTML and PDF; and results are cached (`use_cache: false` on newer versions).
- **Platforms:** web search on the Claude API, Claude Platform on AWS and Microsoft Foundry (basic
  version only when hosted on Azure) and Google Cloud (basic only); not Amazon Bedrock. Web fetch on
  the Claude API, Claude Platform on AWS and Foundry; not Bedrock or Google Cloud.

### OpenAI: web search

- The `web_search` tool in the Responses API; in Chat Completions, search-specific models.
- The caller gets a `web_search_call` item (the action and queries; the full source list with
  `include: ["web_search_call.action.sources"]`) and message annotations of type `url_citation` with
  URL and title. No snippets. Up to 100 `allowed_domains` in `filters`; `user_location`;
  `external_web_access: false` runs cache-only. The search context is limited to 128k tokens.
- Paid per tool call plus search content tokens. OpenAI models only.

### Google: Gemini grounding with Google Search

- Gemini models only. The current docs show the queries the model ran, a Search Suggestions HTML
  snippet, and `url_citation` annotations with URL, title and text span.
- Billing: Gemini 3 models are billed per search query the model runs, Gemini 2.5 per grounded
  prompt, each after a free allowance.
- Terms (2026-04-28): "You will only display the Grounded Results with the associated Search
  Suggestion(s) to the end user who submitted the prompt." No caching, framing, syndicating or
  training on grounded results, with narrow exceptions; no modifying them or interspersing other
  content. Google keeps prompts and output for 30 days to build grounded results. Showing Search
  Suggestions alongside text written onto an e-ink page would need its own UI.

## 8. Readable-text extraction

| Tool | License | Windows | Quality |
|---|---|---|---|
| trafilatura 2.2.0 (2026-07-31) | Apache-2.0 since 1.8.0 (GPLv3+ before) | Pure Python on lxml; classifiers list Windows, macOS, POSIX; Python 3.10+ | Best F1 (0.924) on its own 990-page benchmark run of 2026-08-04; best single tool by mean in an independent SIGIR 2023 comparison. Extracts metadata and dates; has its own `fetch_url`. |
| readability-lxml 0.9 (2026-08-27) | Apache-2.0 | Pure Python on lxml; Python 3.9 to 3.14 | F1 0.826 in trafilatura's benchmark (high precision, lower recall). Returns cleaned HTML. |
| Mozilla Readability (the Firefox reader view) | Apache-2.0 | JavaScript: Node or a browser only | Highest median and most predictable in the SIGIR 2023 comparison. |
| goose3 | Apache-2.0 | Python package *(Windows not checked)* | Highest precision (0.936) but recall 0.714 in trafilatura's benchmark. |
| newspaper4k 0.9.6 (2026-07-19) | MIT | Python package *(Windows not checked)* | News-oriented successor to newspaper3k. |
| ddgs `extract` | MIT | Yes | Converts the whole page; the companion note found navigation left in. |

A May 2026 benchmark (WCXB: 13 extractors, seven page types) found the top systems converge on news
articles (F1 0.93) but diverge on structured pages (F1 0.41 to 0.84), so expect gaps on product
pages, forums and documentation whichever tool is used. For PaperDaemon, trafilatura is the default;
readability-lxml is a reasonable fallback when trafilatura returns nothing.

## 9. Offline knowledge: Kiwix and ZIM

English Wikipedia ZIM files on download.kiwix.org, 2026-09-26:

| File | What it holds | Latest build | Size |
|---|---|---|---|
| `wikipedia_en_all_maxi` | Full articles with pictures | 2026-08 | 119 GB |
| `wikipedia_en_all_nopic` | Full articles, no pictures | 2026-06 | 49 GB |
| `wikipedia_en_all_mini` | Each article's introduction and infobox | 2026-09 | 13 GB |
| `wikipedia_en_top_maxi` / `_nopic` / `_mini` | Top articles only | 2026-09 | 6.5 GB / 2.6 GB / 283 MB |
| `wikipedia_en_100` | 100 articles | 2026-08 | 318 MB |

- The "mini" file is the one that matches need F: every English lead, offline, in 13 GB.
- **kiwix-serve** (in kiwix-tools, GPL-3.0-or-later): a Windows x86_64 zip exists at 3.8.1
  (2025-12-02), behind Linux and macOS at 3.8.2 (2026-03-02); the 32-bit Windows build stopped at
  3.7.0. Kiwix Desktop, the reader app, has Windows x64 builds.
- **python-libzim** (PyPI `libzim` 3.13.0, 2026-09-07, GPL-3.0-or-later) reads ZIM files in-process,
  full-text and title-suggestion search included, with cp312 win_amd64 wheels. Importing it makes
  the GPL apply to PaperDaemon when distributed; kiwix-serve as a separate process keeps it an aggregate.
- Freshness: files are rebuilt every few months (English maxi in 2026-02 and 2026-08), so offline
  facts are months old. Content is CC BY-SA.

## What I could not verify

- Exa's terms (a PDF the fetch tool could not read), Kagi's API terms (none found), and Perplexity's
  Search addendum (403; known only from a search snippet).
- DuckDuckGo's full syndication statement on its script-rendered API page (the partnerships page
  was read directly).
- Openverse's production limits for anonymous clients (only the code defaults are public).
- How Wikimedia counts rate limits for many installs of one app.
- Whether googlesearch-python and icrawler's Google crawler still work.
- The date of Mojeek's CAPTCHA (one user report), and whether 2026 SearXNG reports came from
  residential or datacenter IPs.
- YaCy's result quality (my assessment, not measured).
- SearXNG refusing to start with the default `secret_key` (from issue history, not current code),
  and whether it runs on macOS from source.
- Part of the GPL FAQ passage: gnu.org rate-limited every fetch, and a search index confirmed only
  the mechanism-and-semantics test and its last sentence.

## Sources

All accessed 2026-09-26.

**SearXNG**

- Repository and README: https://github.com/searxng/searxng
- License text (AGPL-3.0): https://raw.githubusercontent.com/searxng/searxng/master/LICENSE
- GNU AGPL-3.0: https://www.gnu.org/licenses/agpl-3.0.html
- GPL FAQ, mere aggregation: https://www.gnu.org/licenses/gpl-faq.html#MereAggregation
- `requirements.txt`: https://raw.githubusercontent.com/searxng/searxng/master/requirements.txt
- `setup.py`: https://raw.githubusercontent.com/searxng/searxng/master/setup.py
- Default `settings.yml`: https://github.com/searxng/searxng/blob/master/searx/settings.yml
- Installation methods: https://docs.searxng.org/admin/installation.html
- Step-by-step installation: https://docs.searxng.org/admin/installation-searxng.html
- Search API: https://docs.searxng.org/dev/search_api.html
- `server:` settings: https://docs.searxng.org/admin/settings/settings_server.html
- `search:` settings: https://docs.searxng.org/admin/settings/settings_search.html
- Limiter: https://docs.searxng.org/admin/searx.limiter.html
- Image result type: https://docs.searxng.org/dev/result_types/main/image.html
- Google engines: https://docs.searxng.org/dev/engines/online/google.html
- Google CSE engine source and history: https://github.com/searxng/searxng/blob/master/searx/engines/google_cse.py,
  https://github.com/searxng/searxng/commits/master/searx/engines/google_cse.py
- Windows discussion #4029: https://github.com/searxng/searxng/discussions/4029
- Windows discussion #4486: https://github.com/searxng/searxng/discussions/4486
- Windows PR #5067: https://github.com/searxng/searxng/pull/5067
- curl_cffi migration PR #6620: https://github.com/searxng/searxng/pull/6620
- Startpage PR #6669 and issue #6520: https://github.com/searxng/searxng/pull/6669,
  https://github.com/searxng/searxng/issues/6520
- DuckDuckGo issues #6596 and #6779: https://github.com/searxng/searxng/issues/6596,
  https://github.com/searxng/searxng/issues/6779
- Google issue #5958: https://github.com/searxng/searxng/issues/5958
- Google CSE issue #6524: https://github.com/searxng/searxng/issues/6524
- Qwant issue #6776: https://github.com/searxng/searxng/issues/6776
- Bing issue #4964: https://github.com/searxng/searxng/issues/4964
- Self-hosted instance with Bing as the only working engine: https://github.com/odysseus-dev/odysseus/issues/6392
- Discussion #5651, major engines: https://github.com/searxng/searxng/discussions/5651
- Image defaults PR #6690: https://github.com/searxng/searxng/pull/6690
- Releases page (none): https://github.com/searxng/searxng/releases
- Container tags: https://hub.docker.com/r/searxng/searxng/tags
- The unrelated PyPI `searxng` package: https://pypi.org/project/searxng/
- Community Windows scripts: https://github.com/Kerberos255/searxng-windows
- Wheels: https://pypi.org/project/curl-cffi/, https://pypi.org/project/lxml/6.1.3/,
  https://pypi.org/project/msgspec/0.21.1/, https://pypi.org/project/PyYAML/6.0.3/
- Single-IP test (vendor of a competing API): https://apiserpent.com/blog/searxng-self-hosted-serp-api-tested
- Third-party blocking report: https://github.com/khsarvar/sifthound/pull/14
- Engine selection notes: https://conselara.dev/notes/searxng-engine-selection/
- Google requires JavaScript (January 2025): https://www.searchenginejournal.com/confirmed-google-is-requiring-javascript-to-block-seo-tools/537705/

**Libraries**

- ddgs: https://pypi.org/project/ddgs/, https://github.com/deedy5/ddgs,
  https://github.com/deedy5/ddgs/issues/478, https://github.com/deedy5/ddgs/issues/480
- duckduckgo_search (renamed): https://pypi.org/project/duckduckgo-search/
- primp: https://pypi.org/project/primp/
- open-webSearch: https://github.com/Aas-ee/open-webSearch
- googlesearch-python: https://pypi.org/project/googlesearch-python/
- icrawler: https://pypi.org/project/icrawler/

**Self-hosted engines**

- Whoogle: https://github.com/benbusby/whoogle-search, https://github.com/benbusby/whoogle-search/releases
- Stract: https://github.com/StractOrg/stract, https://stract.com/
- 4get: https://git.lolcat.ca/lolcat/4get, https://git.lolcat.ca/lolcat/4get/src/branch/master/docs/apache2.md
- LibreY: https://github.com/Ahwxorg/LibreY, https://github.com/Ahwxorg/LibreY/commits/main
- YaCy: https://github.com/yacy/yacy_search_server, https://yacy.net/download_installation/
- Marginalia: https://github.com/MarginaliaSearch/MarginaliaSearch, https://about.marginalia-search.com/article/api/

**Search APIs**

- Brave: https://brave.com/search/api/, https://api-dashboard.search.brave.com/documentation/pricing,
  https://api-dashboard.search.brave.com/terms-of-service, https://x.com/brave/status/2023404757264867432,
  https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/
- Mojeek API: https://www.mojeek.com/services/search/web-search-api/
- Tavily: https://www.tavily.com/pricing, https://www.tavily.com/terms,
  https://nebius.com/newsroom/nebius-announces-agreement-to-acquire-tavily-to-add-agentic-search-to-its-ai-cloud-platform
- Exa: https://exa.ai/pricing
- Serper: https://serper.dev/, https://serper.dev/terms
- SerpAPI: https://serpapi.com/pricing, https://serpapi.com/legal
- Jina: https://jina.ai/reader/, https://jina.ai/api-dashboard/pricing/, https://jina.ai/legal/
- Elastic completes Jina AI acquisition: https://ir.elastic.co/News--Events/news/news-details/2025/Elastic-Completes-Acquisition-of-Jina-AI-a-Leader-in-Frontier-Models-for-Multimodal-and-Multilingual-Search/default.aspx
- Kagi: https://kagi.com/api/pricing, https://help.kagi.com/kagi/api/search.html
- Perplexity: https://docs.perplexity.ai/getting-started/pricing, https://docs.perplexity.ai/guides/search-quickstart,
  https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service-search (403 to my fetch)
- Google Custom Search JSON API: https://developers.google.com/custom-search/v1/overview
- Bing Search APIs retirement: https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement

**Terms of service**

- DuckDuckGo: https://duckduckgo.com/terms, https://duckduckgo.com/acceptable-use,
  https://duckduckgo.com/robots.txt, https://duckduckgo.com/duckduckgo-help-pages/company/partnerships
- Google: https://policies.google.com/terms, https://www.google.com/robots.txt
- Microsoft and Bing: https://www.microsoft.com/en-us/servicesagreement, https://www.bing.com/robots.txt
- Brave: https://brave.com/terms-of-use/, https://search.brave.com/robots.txt, https://search.brave.com/help/pow-captcha
- Mojeek: https://www.mojeek.com/about/terms.html, https://www.mojeek.com/robots.txt,
  user report of CAPTCHAs: https://lemmy.ml/post/49249286

**Official free sources**

- API etiquette: https://www.mediawiki.org/wiki/API:Etiquette
- User-Agent policy: https://foundation.wikimedia.org/wiki/Policy:User-Agent_policy
- Rate limits: https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits
- Tech News: https://www.mediawiki.org/wiki/Tech_news
- API Portal deprecation: https://wikitech.wikimedia.org/wiki/API_Portal/Deprecation
- TextExtracts: https://www.mediawiki.org/wiki/Extension:TextExtracts
- REST API reference: https://www.mediawiki.org/wiki/API:REST_API/Reference
- Wikifeeds: https://www.mediawiki.org/wiki/Wikifeeds
- Thumbnail sizes: https://www.mediawiki.org/wiki/Common_thumbnail_sizes, https://phabricator.wikimedia.org/T414805
- Openverse: https://api.openverse.org/v1/, https://docs.openverse.org/terms_of_service.html,
  https://github.com/WordPress/openverse/blob/main/api/conf/settings/rest_framework.py
- Google News RSS (fetched): https://news.google.com/rss/search?q=weather&hl=en-US&gl=US&ceid=US:en
- Bing News RSS (fetched): https://www.bing.com/news/search?q=weather&format=rss
- Open-Meteo: https://open-meteo.com/en/terms, https://open-meteo.com/en/pricing

**Provider-native tools**

- Anthropic web search: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
- Anthropic web fetch: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool
- OpenAI web search: https://developers.openai.com/api/docs/guides/tools-web-search,
  https://developers.openai.com/api/docs/pricing
- Gemini grounding: https://ai.google.dev/gemini-api/docs/google-search, https://ai.google.dev/gemini-api/docs/pricing,
  https://ai.google.dev/gemini-api/terms

**Extraction**

- trafilatura: https://pypi.org/project/trafilatura/, https://trafilatura.readthedocs.io/en/latest/evaluation.html
- readability-lxml: https://pypi.org/project/readability-lxml/
- newspaper4k: https://pypi.org/project/newspaper4k/
- SIGIR 2023, "An Empirical Comparison of Web Content Extraction Algorithms": https://dl.acm.org/doi/10.1145/3539618.3591920
- WCXB benchmark (May 2026): https://arxiv.org/abs/2605.21097

**Offline**

- Wikipedia ZIM listing: https://download.kiwix.org/zim/wikipedia/
- What mini, nopic and maxi mean: https://get.kiwix.org/en/faq-items/what-do-mini-nopic-and-maxi-mean-in-the-wikipedia-zim-files/
- kiwix-tools: https://github.com/kiwix/kiwix-tools, https://download.kiwix.org/release/kiwix-tools/
- Kiwix downloads: https://get.kiwix.org/en/solutions/applications/download-options/
- python-libzim: https://pypi.org/project/libzim/
