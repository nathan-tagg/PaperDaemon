"""python -m paperdaemon.pipeline.host: the host's job loop, as the engine starts it."""
import sys

from paperdaemon.pipeline.host import log, main

try:
    sys.exit(main())
except KeyboardInterrupt:
    log("stopped")
