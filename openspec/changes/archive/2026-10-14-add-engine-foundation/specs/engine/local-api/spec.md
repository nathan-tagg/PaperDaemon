# Spec Delta

## Purpose

The one surface every PaperDaemon client uses (the desktop window today, a phone over WireGuard later),
guarded by a pairing token against everyone else on the machine or the network.

## ADDED Requirements

### Requirement: Every API request needs the pairing token
The local API SHALL refuse any request under `/api/` that does not carry
`Authorization: Bearer <pairing token>`, from any address including localhost, answering 401 with
`{"error": "not paired"}` and doing nothing else.

#### Scenario: No token
- **WHEN** a request to `/api/v1/status` arrives without an Authorization header
- **THEN** the answer is 401 `{"error": "not paired"}`

#### Scenario: Right token from the desktop window
- **WHEN** the desktop window calls `/api/v1/status` with the pairing token
- **THEN** the answer is 200 with the engine's status

### Requirement: The API is versioned
Every API route SHALL live under `/api/v1/`. A change that would break a v1 route SHALL add a new
version instead of changing v1.

#### Scenario: A route without a version
- **WHEN** a paired client calls `/api/settings`
- **THEN** the answer is 404, and `/api/v1/settings` answers with the settings

### Requirement: The pairing token is made once and can be rotated
PaperDaemon SHALL create a random pairing token with at least 256 bits of entropy on first start, keep it
in the credential store, and replace it when the user rotates it. After a rotation the old token
SHALL be refused.

#### Scenario: Rotation
- **WHEN** the user rotates the pairing token
- **THEN** requests carrying the old token get 401, and the desktop window keeps working with the new one

### Requirement: The API listens where the user says
The API SHALL listen on 127.0.0.1 always, and on each further address in the listen setting, on the
configured port.

#### Scenario: A WireGuard address is added
- **WHEN** the user adds their WireGuard interface address and restarts PaperDaemon
- **THEN** a paired device on the tunnel reaches the API at that address and port

### Requirement: The pairing token never travels in a request URL
The engine SHALL NOT receive the pairing token in any request URL, and SHALL NOT write it to any log.
The desktop window SHALL receive it in the page address fragment, which is never sent to the server.

#### Scenario: The desktop window starts
- **WHEN** the desktop window opens the UI
- **THEN** no request the engine receives carries the pairing token in its path or query

### Requirement: No API documentation is served at run time
The API SHALL NOT serve interactive documentation or a machine-readable schema.

#### Scenario: Looking for docs
- **WHEN** a client requests `/docs` or `/openapi.json`
- **THEN** the answer is 404
