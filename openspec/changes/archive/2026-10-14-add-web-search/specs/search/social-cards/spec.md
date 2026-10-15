# Spec Delta

## Purpose

Shows what people are posting about something as cards on the page, from social sources that can be
read without an account, within each source's limits.

## ADDED Requirements

### Requirement: Posts become cards
A job SHALL be able to find posts about a topic and draw each as a card showing the author, the post's
text, its votes or likes where the source gives them, and when it was posted.

#### Scenario: What is Reddit saying
- **WHEN** a page asks what Reddit is saying about a new game
- **THEN** the job draws cards for matching posts, each with author, text, votes and age

### Requirement: Sources that work without an account
Social cards SHALL use only sources readable without the user's account: Reddit's public feeds and
public vote counts, Hacker News, Bluesky, Mastodon and 4chan, and single public posts from X. A request
for a source PaperDaemon cannot read, such as Instagram or Facebook, SHALL be answered by saying so.

#### Scenario: An unsupported source
- **WHEN** a page asks for the latest Instagram posts from an account
- **THEN** the job says Instagram cannot be read without an account and draws no cards

### Requirement: Rate limits are respected
Social requests SHALL follow each source's published or signaled rate limits, waiting between requests
as the source asks, and SHALL say on the page when a card set was cut short by a limit.

#### Scenario: Reddit's one request a minute
- **WHEN** a job needs four Reddit feeds
- **THEN** it spaces the requests as Reddit's rate-limit headers ask and draws the cards when they arrive

### Requirement: No duplicates
The same post, including a cross-post of it, SHALL appear once in a card set.

#### Scenario: A cross-posted story
- **WHEN** one story was posted to three subreddits
- **THEN** it appears as one card

### Requirement: No private feeds
PaperDaemon SHALL NOT ask for, store or use a private feed address or account token for a social source.

#### Scenario: A pasted private feed link
- **WHEN** a page holds a private feed address
- **THEN** PaperDaemon does not store it or fetch it
