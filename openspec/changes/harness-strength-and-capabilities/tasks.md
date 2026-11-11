# Tasks

## 1. The engine

- [x] 1.1 The `web_search` and `image_generation` capabilities (harness fields, rules, overrides)
- [x] 1.2 Weak (`weak-text`); Medium and Strong renamed; descriptions
- [x] 1.3 Whether the model searches the web itself (`slots.searches_itself`), told to the host and to each call
- [x] 1.4 The brief's facts line by where search comes from; the `claude` program's own search by its data; the
      Anthropic API's own search tool
- [x] 1.5 Tests: `tests/test_harness_bases.py`

## 2. The window

- [x] 2.1 The slider, the base's description, Your harness, the Capabilities boxes, the summary line and warning
- [x] 2.2 Help modal; "?" on both labels; notes on the Image and Network tabs; 19 languages

## 3. The maintainer's revision (11-11)

- [x] 3.0 Harness a dropdown; Capabilities a type-ahead with pills; no Your harness, no Add Harness; the summary and
      warning lines moved into the help modal's warning card; the tested models on every base
- [x] 3.0a Pictures made by the text model's server when the Image tab is empty (tested against a stand-in server in
      the documented reply shapes; his Google key's free tier has no image-model quota)
- [x] 3.0b Tool-call markup read as calls on the command line (Sonnet 5.5 answered that way and was asked twice more)
- [x] 3.0c A lineup saved or deleted reaches the running loop (0.2.56)
- [x] 3.0d Weak turns off mark-ups and checkboxes made of the user's own lines (Qwen3-VL 8B ruled a whole typed list erased and copied a sentence back instead of underlining it); checkboxes are a feature of their own

## 4. Proof

- [ ] 4.1 The maintainer's app after the update: each lineup's Text tab, and a real job on Weak with a small model
