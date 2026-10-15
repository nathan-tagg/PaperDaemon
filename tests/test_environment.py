"""Every environment variable the code reads is listed, by kind, in paperdaemon/environment.py."""
import os
import re

from paperdaemon import environment

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READ = re.compile(r"""(?:environ(?:\.get)?[\[(]|getenv\(|environ\.setdefault\()\s*["']([A-Z_0-9]+)["']""")


def test_every_environment_read_is_classified():
    unlisted = {}
    for cur, dirs, files in os.walk(os.path.join(ROOT, "paperdaemon")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(cur, f)
                with open(path, encoding="utf-8") as fh:
                    for name in READ.findall(fh.read()):
                        if name not in environment.ALL:
                            unlisted.setdefault(name, os.path.relpath(path, ROOT))
    assert not unlisted, unlisted


def test_no_setting_and_no_key_is_an_environment_variable():
    assert "RM_MAP_KEY" not in environment.ALL and "RM_CHART_PATH" not in environment.ALL
    assert "RM_CALENDAR_MODE" not in environment.ALL and "RM_HOST_TURNS" not in environment.ALL
