# Proposal: add-model-call-retries

## Why

A model reached over the network can be too busy to answer. Gemini 3.8 Flash answered HTTP 503 ("This model is
currently experiencing high demand") on four jobs between 11-06 and 11-16, and each job was skipped within seconds after
one try. The maintainer (11-16): a retry setting for "any model that isn't local", "like how long it should wait for a
response and how many times it should retry".

## What Changes

- A model reached with an API key (a text or image slot whose model isn't on this computer) has two settings: Wait for a
  reply (seconds one call waits; blank: as long as it takes) and Retries (how many more times a busy or silent server
  is asked; 3 unless set).
- A busy answer (429, 502, 503, 504, 529) or no reply is asked again after a pause: what the server asked for
  (Retry-After), else 5, 10, 20, 40, then 60 seconds. Any other answer is the answer.
- Models on this computer and command-line programs are not changed: a local server's busy answer means it is loading,
  and a command line retries on its own (running it again could repeat what it did on the computer).

## Impact

- `paperdaemon/models/adapters.py` (Adapter.call, paced), `paperdaemon/settings.py` (the two slot values),
  `paperdaemon/ui/slots.js` and the strings in 19 languages, `tests/test_model_retries.py`.
- The rule that a model call has no clock gains its one exception, the user's own Wait for a reply.
