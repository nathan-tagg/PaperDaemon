"""Every environment variable PaperDaemon reads, by kind. A setting is never one of them: settings live in
the settings file (and reach the host through its run file); a secret lives in the credential store.

tests/test_environment.py fails on a read of a name that is not listed here.
"""

# Set by the user or the system, read as they are.
SYSTEM = {
    "APPDATA": "the Windows per-user application data folder",
    "WINDIR": "the Windows folder (its fonts)",
    "LOCALAPPDATA": "the Windows per-user local folder (where a per-user reMarkable desktop app is installed)",
    "ProgramFiles": "the Windows programs folder (the reMarkable desktop app, whose typefaces are used)",
    "ProgramW6432": "the 64-bit programs folder, the same",
    "ProgramFiles(x86)": "the 32-bit programs folder, the same",
    "PAPERDAEMON_HOME": "another data folder (tests, a second install)",
    "PAPERDAEMON_CONTENT": "another content folder",
    "PAPERDAEMON_STOCKFISH": "a chess engine to use instead of the one found",
    "PAPERDAEMON_PAIRING_TOKEN": "the pairing token, for a headless engine started by a script",
    "PAPERDAEMON_CASES": "another folder of benchmark cases",
    "PAPERDAEMON_SERVICE": "another credential store service name (a test install)",
    "NUMBA_CACHE_DIR": "where the decomposer's reference caches its compiled code",
    "ZIG_GLOBAL_CACHE_DIR": "the C compiler's cache (building the decomposer)",
    "ZIG_LOCAL_CACHE_DIR": "the C compiler's cache (building the decomposer)",
}

# Wiring: what the engine tells the daemon and the host it starts (loop.environment).
WIRING = {
    "RM_STATE": "the state folder: ledger, queue, notepads, logs",
    "RM_MIRROR": "PaperDaemon's mirror of the library",
    "RM_CACHE": "the mirror, as the page readers know it",
    "RM_TRIGGERS": "every lineup's tags, a JSON list: the tags the daemon watches for",
    "RM_TRIGGER_LINEUPS": "each watched tag's lineup, a JSON object {tag: lineup}: a page tagged for two is skipped",
    "RM_TRIGGER": "one tag to watch for, when RM_TRIGGERS is not given (a pipeline run by hand)",
    "RM_INBOX": "the decompose inbox (Folder/Notebook), never worked whatever its tags",
    "RM_IGNORE_TAG": "the tag that keeps pages out (Settings)",
    "RM_SPROMPT_TAG": "the tag for a notebook's standing instructions (Settings)",
    "RM_LLM": "the engine's door to the text slot",
    "RM_RUN": "the host's run file: every lineup's harness values and resolved features, the settings it reads",
    "RM_INTERVAL": "the daemon's idle poll, in seconds",
    "RM_MAX_ATTEMPTS": "tries per page before the daemon gives up on it",
    "RM_PY": "the interpreter the children run under",
    "RM_STUDIO": "the engine's picture surface for the host",
    "RM_STUDIO_TOKEN": "the token for the engine's host surfaces",
    "RM_LOCAL_ONLY": "1 in a process working the false mirror: nothing is pulled from or pushed to the cloud",
    "PAPERDAEMON_PARENT": "the engine that started the false mirror's engine, which ends when it does",
    "RM_FACES": "tablet or own: the faces a process sets typed text and books in (the false mirror's, chosen by the engine)",
    "QT_QPA_PLATFORM": "offscreen, set by a book's layout child for Qt (remarkable/books.py)",
    "QT_QPA_FONTDIR": "the folder of faces a book's layout child gives Qt, so it sees no others",
}

# Developer switches: for measuring and debugging; nothing a user sets.
DEVELOPER = {
    "RM_DRY_RUN": "the daemon queues nothing",
    "RM_HOST_DRY_DOCS": "the host stages documents and never publishes them (the benchmark)",
    "RM_HOST_DRAW_LOOKS": "look-and-fix rounds for drawings",
    "RM_HOST_DRAW_ROUNDS": "the most look-and-fix rounds a drawing gets",
    "RM_DECIDE_TEMP": "the decision turn's temperature",
    "RM_CTX_RESTART": "the share of the context at which a job's conversation restarts",
    "RM_HISTORY_CAP": "how many page histories are kept",
    "RM_ERROR_BACKOFF": "how often a repeated scan error is reported",
    "RM_LOG_CAP": "the daemon log's size ceiling",
    "RM_SELF_WRITE": "seconds after a job in which a change is the job's own",
    "RM_CLAIM_TTL": "seconds after which a claim on a page is dead",
    "RM_NOTEBOOK_CAP": "the most jobs one notebook may start at once; past it, none start",
    "RM_FAST": "the decomposer's C stages on or off",
    "RM_FAST_STAGES": "which of the decomposer's C stages run",
    "RMFAST_LIB": "another build of the decomposer's C library",
    "RMB_VERIFY_CACHE": "the decomposer reference's cache check",
    "RM_UPSCALE": "the decomposer reference's upscaling",
    "RM_WHITE_FLOOR": "the decomposer reference's white floor",
    "RM_V69_FLOW": "a decomposer reference experiment",
    "RM_V69_FLOWFILL": "a decomposer reference experiment",
    "RM_V69_WP": "a decomposer reference experiment",
}

ALL = {**SYSTEM, **WIRING, **DEVELOPER}
