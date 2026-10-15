# models/slots Specification

## Purpose
Lets the user point PaperDaemon at any model server or provider, one slot for text and reasoning and one
for pictures, and shows plainly what each slot can do and where it sends pages.

## Requirements

### Requirement: Two model slots
PaperDaemon SHALL have exactly two model slots, **text** (text and reasoning) and **image**. Each slot SHALL
hold: where the server runs (this computer or elsewhere), the API family, the endpoint address, an
optional key, the model name to request, the harness, capability overrides, and, for a slot on this
computer, an optional launch script.

#### Scenario: A local text model and a cloud image model
- **WHEN** the user sets the text slot to a server on this computer and the image slot to a cloud
  provider with a key
- **THEN** both settings are saved, the key is in the credential store, and each slot works on its own

### Requirement: Supported API families
The text slot SHALL speak the OpenAI-compatible Chat Completions API and the Anthropic Messages API.
The image slot SHALL speak the Stable Diffusion web UI API (`/sdapi/v1/txt2img`) and the OpenAI Images
API.

#### Scenario: A llama.cpp server
- **WHEN** the text slot is an OpenAI-compatible endpoint served by llama.cpp
- **THEN** PaperDaemon sends chat requests to it in that API's format

#### Scenario: An Anthropic model
- **WHEN** the text slot's API family is Anthropic and a key is saved
- **THEN** PaperDaemon sends Messages API requests with that key

### Requirement: Both slots may use one provider
The two slots SHALL be configured independently and MAY name the same endpoint, provider and key.

#### Scenario: One provider for both
- **WHEN** the user points both slots at the same provider with the same key
- **THEN** text requests and picture requests both go to that provider, each in its own API family

### Requirement: An empty image slot is allowed
PaperDaemon SHALL run with no image slot configured. Jobs then get no picture or coloring-page tools.

#### Scenario: Text only
- **WHEN** the image slot has no endpoint
- **THEN** PaperDaemon starts, answers pages in words and charts, and reports pictures as unavailable

### Requirement: A local slot's endpoint is on this computer
A slot set to run on this computer SHALL have an endpoint on a loopback address (`127.0.0.0/8`,
`localhost` or `::1`); saving any other address for it SHALL be refused.

#### Scenario: A local slot with a network address
- **WHEN** the user saves a local slot whose endpoint is `http://10.0.0.5:8080`
- **THEN** nothing is saved and the answer says a local slot's endpoint must be on this computer

### Requirement: Off-machine notice
Whenever a slot's endpoint is not a loopback address, the models screen SHALL say plainly that pages
the user tags are sent to that host.

#### Scenario: A cloud text model
- **WHEN** the text slot points at a provider's address
- **THEN** the models screen says that tagged pages are sent to that provider's host

### Requirement: Test this model
Each slot SHALL offer a test that reports, one line per check: whether the endpoint answers, the models
the server reports, and for text whether a forced tool call works and whether the model can see an
image, or for pictures a small render shown to the user. The test SHALL suggest capability overrides
where a check disagrees with the harness. A picture from the test SHALL be shown and not kept.

#### Scenario: A text model that cannot see
- **WHEN** the user tests a text slot whose harness says it has vision and the model fails the image check
- **THEN** the report shows the failed check and suggests turning vision off for this slot

#### Scenario: Testing the image slot
- **WHEN** the user tests the image slot
- **THEN** a small picture from the model is shown in the report, and it is not saved anywhere

### Requirement: No prices
The models screen and every part of PaperDaemon SHALL NOT show prices, costs, token spend or usage meters.

#### Scenario: A paid provider
- **WHEN** a slot points at a paid provider
- **THEN** nothing in PaperDaemon mentions what a request costs
