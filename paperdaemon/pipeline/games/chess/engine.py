"""Stockfish over UCI: find the engine, start it without a window, ask it for its best moves.

Where the engine is looked for is paths.stockfish: PAPERDAEMON_STOCKFISH, the content folder, the copy the
app ships beside itself, then the executable search path.

A search is bounded by depth or nodes, the engine's own limits. Reading its reply ends when it answers
or when its process exits, never on a timer.
"""
import subprocess

from . import rules


class EngineNotInstalled(RuntimeError):
    """No Stockfish executable could be found."""


class EngineTerminated(RuntimeError):
    """The engine's process ended while PaperDaemon was waiting for it."""


def path():
    """The Stockfish executable to run, or None (paths.stockfish says where it is looked for)."""
    from paperdaemon import paths
    return paths.stockfish()


class Engine(object):
    """One Stockfish process. Use as a context manager."""

    def __init__(self, exe=None, options=None):
        exe = exe or path()
        if not exe:
            raise EngineNotInstalled("the chess engine (Stockfish) is not installed: PaperDaemon looks for it "
                                     "in its content folder under engines/stockfish, beside the app, on the "
                                     "executable search path, or at PAPERDAEMON_STOCKFISH")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
                                     creationflags=flags)
        self.options = {}
        self._send("uci")
        for line in self._until("uciok"):
            parts = line.split()
            if parts[:2] == ["option", "name"] and "type" in parts:
                self.options[" ".join(parts[2:parts.index("type")])] = line
        if options:
            self.configure(options)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _send(self, line):
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            raise EngineTerminated("the chess engine has stopped") from None

    def _until(self, word):
        """The engine's lines up to and including the first one that starts with `word`."""
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise EngineTerminated("the chess engine stopped while PaperDaemon waited for %r" % word)
            line = line.strip()
            yield line
            if line.split(" ", 1)[0] == word:
                return

    def configure(self, options):
        for name, value in options.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            self._send("setoption name %s value %s" % (name, value))
        self._send("isready")
        for _ in self._until("readyok"):
            pass

    def analyze(self, fen, depth=None, nodes=None, multipv=1):
        """The engine's best lines from a position -> [{"multipv", "depth", "cp", "mate", "pv": [Move]}],
        best first. `cp` is in centipawns and `mate` in moves, from the side to move's point of view."""
        if multipv != getattr(self, "_multipv", 1):
            self.configure({"MultiPV": multipv})
            self._multipv = multipv
        self._send("position fen " + fen)
        go = "go" + (" depth %d" % depth if depth else "") + (" nodes %d" % nodes if nodes else "")
        self._send(go if go != "go" else "go depth 12")
        lines = {}
        for line in self._until("bestmove"):
            info = _parse_info(line)
            if info and info.get("pv"):
                lines[info["multipv"]] = info
        board = rules.Board(fen)
        out = []
        for k in sorted(lines):
            info = lines[k]
            pv, b = [], board.copy(stack=False)
            for uci in info["pv"]:
                try:
                    move = rules.Move.from_uci(uci)
                except ValueError:
                    break
                if move not in b.legal_moves:
                    break
                pv.append(move)
                b.push(move)
            if pv:
                out.append(dict(info, pv=pv))
        return out

    def close(self):
        if self.proc.poll() is not None:
            return
        try:
            self._send("quit")
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def _parse_info(line):
    parts = line.split()
    if not parts or parts[0] != "info" or "pv" not in parts or "score" not in parts:
        return None
    out = {"multipv": 1, "depth": 0, "cp": None, "mate": None}
    for key in ("multipv", "depth"):
        if key in parts:
            out[key] = int(parts[parts.index(key) + 1])
    i = parts.index("score")
    kind, value = parts[i + 1], int(parts[i + 2])
    out["cp" if kind == "cp" else "mate"] = value
    out["pv"] = parts[parts.index("pv") + 1:]
    return out


def score(info, mate_score=100000):
    """One number for a line, mates beyond any material: mate in n is mate_score - n, being mated in n is
    -mate_score + n."""
    if info.get("mate") is not None:
        n = info["mate"]
        return mate_score - n if n > 0 else -mate_score - n
    return info.get("cp") or 0
