# Spec Delta

## Purpose

Gives jobs facts from the web (search results, page text, pictures, dated facts and weather) through
providers the user chose, and nothing else.

## ADDED Requirements

### Requirement: A search provider of the user's choice
The search settings SHALL offer the search providers in one dropdown. Choosing SearXNG SHALL show one
text box for the address of a SearXNG instance the user runs; choosing a search API provider SHALL show
a field for its key. Jobs SHALL search only through the chosen provider. PaperDaemon SHALL NOT install,
start, stop or update SearXNG.

#### Scenario: A local SearXNG
- **WHEN** the user picks SearXNG, enters `http://127.0.0.1:8888`, and a page asks for today's top headline
- **THEN** the job searches through that SearXNG and answers from its results

#### Scenario: SearXNG is not running
- **WHEN** the user picks SearXNG and nothing answers at the address they entered
- **THEN** jobs report that SearXNG is not answering at that address, and PaperDaemon does not try to
  install or start it

#### Scenario: No provider
- **WHEN** no search provider is set and a page asks for today's weather in words
- **THEN** the model is offered no search tool, and the job says web search is not set up

### Requirement: Fetching pages and pictures
A job SHALL be able to fetch a web page's readable text or a web picture by its address, for use in
that job only.

#### Scenario: Summarize a link
- **WHEN** a page asks to summarize an article at a web address
- **THEN** the job fetches the article's text and writes the summary

### Requirement: Built-in sources are listed and can be turned off
Every web service PaperDaemon can call besides the search provider, such as an encyclopedia for facts about
a date or a weather service, SHALL be listed in the search settings with the host it calls, and SHALL be
possible to turn off. A source that is off SHALL never be called.

#### Scenario: Weather turned off
- **WHEN** the user turns the weather source off and a page asks for this week's calendar
- **THEN** the calendar is made without weather and no weather service is called

### Requirement: Nothing else leaves the machine
Jobs SHALL NOT contact any host other than the configured model endpoints, the chosen search provider,
the built-in sources left on, and the addresses a page or search result names for fetching.

#### Scenario: Auditing a job's traffic
- **WHEN** a job answers a question with a web search
- **THEN** its network calls go only to the text model's endpoint, the search provider and the pages it fetched
