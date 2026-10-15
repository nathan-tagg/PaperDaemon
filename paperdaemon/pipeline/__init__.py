"""The pipeline: the daemon that watches the tablet (daemon), the host that answers a page (host), and what they
work with: pages (page), lettering and shapes (draw), charts (charts), games (games) and the decomposer
(decompose)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "rm-templates")
