"""python -m paperdaemon.pipeline.daemon: the daemon, as the engine starts it."""
from paperdaemon.pipeline.daemon import _shutdown, log, main, on_close

on_close(_shutdown)
try:
    main()
except KeyboardInterrupt:
    _shutdown()
except Exception:
    import traceback
    log("CRASHED: " + traceback.format_exc())
    _shutdown()
    raise
