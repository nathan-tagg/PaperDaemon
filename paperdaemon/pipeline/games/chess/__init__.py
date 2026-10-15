r"""Chess on a tablet page -- the first game of the tabletop engine.

The design rules, and where each one lives here:

  1. A session has a random SEED, and the randomness is good. `Rng` is counter based: draw n is
     BLAKE2b(key=seed, message=n), so the state keeps two numbers (seed, draws), every draw can be
     reproduced, and a game resumes exactly where it stopped. (A noise map is the other kind of
     randomness -- smooth over space, for terrain and dungeon maps -- and belongs to the games that
     need a world, not to dice and shuffles.)
  2. The model never holds the game or picks an illegal move. games.chess.rules holds the rules, Stockfish
     proposes the moves, and a persona picks among them: `persona_pick` by traits, with no model, or
     a model through `llm_prompt` + `parse_llm_pick`, which accepts only a listed move.
  3. The game's state and its whole history live in the notebook's notepad as JSON, one entry per
     game, rewritten in place (`save_state` / `load_state`).
  4. An engine validates every move: `infer_move` and `apply_move`.
  5. The board is one picture, and every piece is a picture of its own, so a player moves a piece
     with the tablet's selection tool. Squares are drop zones read off the pictures' positions,
     with no model involved (`read_pictures`, `infer_move`). After every turn `tidy` snaps each piece
     to its square's exact box: a moved piece, a slightly-off piece, an illegal move put back on its
     origin square, and a captured piece set in the captured-pieces row.

The host's part (rm_host) is to notice that a page is a game page (`game_for_page`), call
`user_turn` and then `engine_turn`, letter the opponent's line in TALK area, and commit.

The pieces are drawn in games.chess.pieces and rendered at first use; so is the board of a game begun with
the older board layout (LEGACY_MARGIN).
"""
from paperdaemon import paths
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from paperdaemon.pipeline.games.chess import engine as _engine
from paperdaemon.pipeline.games.chess import pieces as _pieces
from paperdaemon.pipeline.games.chess import rules as chess

HERE = os.path.dirname(os.path.abspath(__file__))
from paperdaemon.notepad import folder as _notepads
NOTEPAD_DIR = _notepads()                                        # every notebook's notepad

# ------------------------------------------------------------------------------ the page
# A 1620 x 2160 notebook page: x runs -810..810 from its center, y 0..2160 from its top, and content
# keeps inside the page's safe area (rm_page.SAFE_AREA: the tablet's toolbar across the top, small
# margins at the sides and the foot).
# THE TOP OF A GAME PAGE IS THE OTHER SIDE'S, THE BOTTOM IS THE PLAYER'S, the board between: the
# opponent's talk strip and the pieces it has taken above the board, the pieces the player has taken
# below it.
# THE 64 SQUARES ARE CENTERED ON THE PAGE, green and near-white for the tablet's screen, and the file letters
# and rank numbers hang OUTSIDE them: the numbers to the left of the squares, the letters below, in the board's
# green, so a piece sits centered in its square with nothing to clear. Two older layouts stay readable, so a game
# keeps the board it was drawn with: labels inside the squares (its state has a "margin" of 0 and no "labels"),
# and a 48 px label margin round eight 168 px squares (LEGACY_MARGIN; its state has no "margin").
try:
    from paperdaemon.pipeline.page import SAFE_AREA as _SAFE
except Exception:                                     # without the rmscene stack: the same numbers
    _SAFE = (-800.0, 160.0, 800.0, 2150.0)
SQ = 168                                              # a square in the piece pictures' own pixels
LEGACY_MARGIN = 48
PAGE_W = 1620
TOP = float(_SAFE[1])                                 # below the tablet's toolbar
TALK_MIN = 300                                        # the least height the opponent's talk strip keeps
CAP = 72                                              # a captured piece's icon, and its row's height
CAP_GAP = 10
LIGHT, DARK = (240, 217, 181), (181, 136, 99)          # the squares of the two older layouts
# the board's colors on the tablet: one green that black pieces stand out on (3.6:1) and that text in it reads in
# on white (4.7:1), and near-white
GREEN, WHITE = (0x4F, 0x7F, 0x3A), (0xF4, 0xF4, 0xEC)
LABEL_W, LABEL_H = 46, 46                             # the margins the rank numbers and file letters hang in
OUTSIDE = -1                                          # margin_of() for a board with its labels outside
VALUE = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}


def board_box_for(safe=_SAFE):
    """A new game's 64 squares on the page: centered across it, as large as the safe area allows once the
    talk strip, the two captured rows and the label margins have their room (the numbers' margin on either
    side, so the squares stay centered), the lower captured row ending at the safe area's foot."""
    x0, y0, x1, y1 = (float(v) for v in safe)
    side = min(x1 - x0 - 2 * LABEL_W, y1 - y0 - TALK_MIN - 2 * (CAP + CAP_GAP) - LABEL_H)
    by1 = y1 - CAP_GAP - CAP - LABEL_H
    cx = (x0 + x1) / 2.0
    return (cx - side / 2.0, by1 - side, cx + side / 2.0, by1)


BOARD_BOX = board_box_for()                           # (-740, 542, 740, 2022) on a notebook page


def margin_of(state):
    """The label margin round the squares of this game's board picture, in the pictures' own pixels; OUTSIDE
    for a board whose box is its squares, with the labels hanging outside it."""
    b = state.get("board") or {}
    if b.get("labels") == "outside":
        return OUTSIDE
    return int(b.get("margin", LEGACY_MARGIN))


def talk_box(board_box=BOARD_BOX):
    """Where the opponent's talk strip goes: from the top of the safe area down to the pieces it has
    taken, starting at the board's left edge and no wider than the board."""
    return (float(board_box[0]), TOP, float(board_box[2]), float(board_box[1]) - 2 * CAP_GAP - CAP)


# ------------------------------------------------------------------------------ 1. randomness
def new_seed():
    """128 bits from the operating system's generator, as hex."""
    return secrets.token_hex(16)


class Rng(object):
    """A counter-based generator: draw n = BLAKE2b(key=seed, message=n). Two numbers are its whole
    state, so a game stored as JSON resumes with exactly the draws it would have made."""

    def __init__(self, seed, draws=0):
        self.seed = seed if isinstance(seed, str) else "%032x" % seed
        self.key = bytes.fromhex(self.seed)
        self.draws = int(draws)

    def next64(self):
        h = hashlib.blake2b(self.draws.to_bytes(8, "little"), key=self.key, digest_size=8).digest()
        self.draws += 1
        return int.from_bytes(h, "little")

    def random(self):
        """A float in [0, 1) with 53 random bits."""
        return (self.next64() >> 11) * (1.0 / (1 << 53))

    def randint(self, a, b):
        """An integer in [a, b], without modulo bias."""
        n = b - a + 1
        if n <= 0:
            raise ValueError("empty range")
        limit = (1 << 64) - ((1 << 64) % n)
        while True:
            v = self.next64()
            if v < limit:
                return a + v % n

    def choice(self, seq):
        return seq[self.randint(0, len(seq) - 1)]

    def shuffle(self, seq):
        """Fisher-Yates, in place."""
        for i in range(len(seq) - 1, 0, -1):
            j = self.randint(0, i)
            seq[i], seq[j] = seq[j], seq[i]
        return seq

    def state(self):
        return {"seed": self.seed, "draws": self.draws}


# ------------------------------------------------------------------------------ assets
def piece_png(color, kind):
    return _pieces.png_path(color, kind, SQ)


def board_png(flipped=False):
    """The board picture of a game begun before the labels moved inside the board (LEGACY_MARGIN), drawn
    the first time it is asked for."""
    from paperdaemon import paths
    out = os.path.join(paths.cache_dir("chess"), "legacy-board-%s.png" % ("black" if flipped else "white"))
    if not os.path.isfile(out):
        legacy_board_image(flipped).save(out)
    return out


LABEL_INK = {"on_light": (92, 62, 38), "on_dark": (246, 236, 214)}   # a label in its square's other tone


def board_image(flipped=False, px=1344):
    """The board as a picture `px` square: the 64 squares, green and near-white, edge to edge in a thin green
    frame. The labels are drawn outside it (layer_png)."""
    from PIL import Image, ImageDraw
    px = int(px)
    sq = px / 8.0
    im = Image.new("RGB", (px, px), WHITE)
    d = ImageDraw.Draw(im)
    for col in range(8):
        for row in range(8):
            f, r = _file_rank(col, row, flipped)
            x0, y0 = int(round(col * sq)), int(round(row * sq))
            x1, y1 = int(round((col + 1) * sq)) - 1, int(round((row + 1) * sq)) - 1
            d.rectangle((x0, y0, x1, y1), fill=GREEN if (f + r) % 2 == 0 else WHITE)
    d.rectangle((0, 0, px - 1, px - 1), outline=GREEN, width=max(2, int(round(sq * 0.02))))
    return im


def inside_board_image(flipped=False, px=1344):
    """The board as a picture `px` square, drawn here: the 64 squares edge to edge, a thin frame, and
    the coordinates INSIDE the board -- each rank number in its square of the left column, centered on
    the square's height in the strip pieces leave free at a square's left, and each file letter in its
    square of the bottom row, centered on the square's width in the strip they leave free at its foot.
    Bold and in the square's other tone, so they read on the tablet."""
    from PIL import Image, ImageDraw
    from paperdaemon import paths
    px = int(px)
    sq = px / 8.0
    im = Image.new("RGB", (px, px), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for col in range(8):
        for row in range(8):
            f, r = _file_rank(col, row, flipped)
            x0, y0 = int(round(col * sq)), int(round(row * sq))
            x1, y1 = int(round((col + 1) * sq)) - 1, int(round((row + 1) * sq)) - 1
            d.rectangle((x0, y0, x1, y1), fill=DARK if (f + r) % 2 == 0 else LIGHT)
    d.rectangle((0, 0, px - 1, px - 1), outline=(60, 60, 60), width=max(2, int(round(sq * 0.012))))
    # the free strips: a piece stands in its square at PIECE_SCALE (piece_box), which leaves a band clear at
    # the square's left for the number and one at its foot for the letter
    size = max(12, int(round(sq * 0.15)))
    font = paths.pil_font("reMarkableSans-Bold", size)

    def ink(col, row):
        f, r = _file_rank(col, row, flipped)
        return LABEL_INK["on_dark"] if (f + r) % 2 == 0 else LABEL_INK["on_light"]
    for i in range(8):
        _, r = _file_rank(0, i, flipped)                  # the left column: rank numbers
        t = str(r + 1)
        l, tp, rt, bt = d.textbbox((0, 0), t, font=font)
        cx, cy = sq * 0.10, (i + 0.5) * sq
        d.text((cx - (l + rt) / 2.0, cy - (tp + bt) / 2.0), t, font=font, fill=ink(0, i))
        f, _ = _file_rank(i, 7, flipped)                  # the bottom row: file letters
        t = "abcdefgh"[f]
        l, tp, rt, bt = d.textbbox((0, 0), t, font=font)
        cx, cy = (i + 0.5) * sq, 8 * sq - sq * 0.095
        d.text((cx - (l + rt) / 2.0, cy - (tp + bt) / 2.0), t, font=font, fill=ink(i, 7))
    return im


def legacy_board_image(flipped=False):
    """The board as games begun with the older layout have it: eight squares of SQ pixels inside a
    LEGACY_MARGIN band that holds the file letters and rank numbers."""
    from PIL import Image, ImageDraw, ImageFont
    margin, px = LEGACY_MARGIN, 8 * SQ + 2 * LEGACY_MARGIN
    try:
        font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "seguisb.ttf"), 28)
    except OSError:
        font = ImageFont.load_default(28)
    im = Image.new("RGB", (px, px), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for col in range(8):
        for row in range(8):
            f, r = _file_rank(col, row, flipped)
            x, y = margin + col * SQ, margin + row * SQ
            d.rectangle((x, y, x + SQ - 1, y + SQ - 1), fill=DARK if (f + r) % 2 == 0 else LIGHT)
    d.rectangle((margin - 2, margin - 2, margin + 8 * SQ + 1, margin + 8 * SQ + 1), outline=(60, 60, 60), width=2)
    ink = (70, 70, 70)
    for i in range(8):
        f, _ = _file_rank(i, 0, flipped)
        _, r = _file_rank(0, i, flipped)
        fl, rl = "abcdefgh"[f], str(r + 1)
        cx = margin + i * SQ + SQ / 2.0
        w = d.textlength(fl, font=font)
        d.text((cx - w / 2.0, margin + 8 * SQ + 6), fl, fill=ink, font=font)
        cy = margin + i * SQ + SQ / 2.0
        w = d.textlength(rl, font=font)
        d.text(((margin - w) / 2.0, cy - 17), rl, fill=ink, font=font)
    return im


# ------------------------------------------------------------------------------ layout
def _file_rank(col, row, flipped):
    """Board column and row (0 at the top left) -> (file 0..7, rank 0..7)."""
    return (7 - col, row) if flipped else (col, 7 - row)


def _col_row(square, flipped):
    f, r = "abcdefgh".index(square[0]), int(square[1]) - 1
    return (7 - f, r) if flipped else (f, 7 - r)


def _grid(board_box, margin=0):
    """Where the 64 squares are in a board picture's box -> (left, top, a square's width, its height).
    `margin` is the label margin round the squares in the picture's own pixels (LEGACY_MARGIN for a
    game begun with that layout; 0 or OUTSIDE when the box is the squares themselves)."""
    margin = max(0, margin)
    bx0, by0, bx1, by1 = (float(v) for v in board_box)
    total = 8 * SQ + 2 * margin
    sx, sy = (bx1 - bx0) / total, (by1 - by0) / total
    return bx0 + margin * sx, by0 + margin * sy, SQ * sx, SQ * sy


def square_box(square, board_box=BOARD_BOX, flipped=False, margin=0):
    """A square's box on the page, relative to where the board picture is NOW."""
    gx, gy, w, h = _grid(board_box, margin)
    col, row = _col_row(square, flipped)
    x0, y0 = gx + col * w, gy + row * h
    return (x0, y0, x0 + w, y0 + h)


PIECE_SCALE = 0.86              # a piece's picture in its square, on a board with the labels inside


def piece_box(square, board_box=BOARD_BOX, flipped=False, margin=0):
    """Where a piece's picture goes on its square: the whole square on a legacy board; on a board with
    its labels inside, PIECE_SCALE of it, a touch right of center and up from the foot, so the rank
    number at the square's left and the file letter at its foot stay clear of the piece."""
    b = square_box(square, board_box, flipped, margin)
    if margin == LEGACY_MARGIN:
        return b
    if margin == OUTSIDE:                       # nothing to clear: centered, with a little air round it
        w, h = b[2] - b[0], b[3] - b[1]
        return (b[0] + w * 0.04, b[1] + h * 0.04, b[2] - w * 0.04, b[3] - h * 0.04)
    w, h = b[2] - b[0], b[3] - b[1]
    pw, ph = w * PIECE_SCALE, h * PIECE_SCALE
    x0, y0 = b[0] + (w - pw) / 2.0 + w * 0.03, b[1] + h * 0.02
    return (x0, y0, x0 + pw, y0 + ph)


def square_at(x, y, board_box=BOARD_BOX, flipped=False, margin=0):
    """The square under a page point, or None off the board."""
    gx, gy, w, h = _grid(board_box, margin)
    fc, fr = (x - gx) / w, (y - gy) / h
    if not (0 <= fc < 8 and 0 <= fr < 8):
        return None
    f, r = _file_rank(int(fc), int(fr), flipped)
    return "abcdefgh"[f] + str(r + 1)


def captured_box(color, index, board_box=BOARD_BOX, user="w", margin=0):
    """The slot a captured piece of `color` sits in, on the side of whoever took it: the player's
    pieces the opponent took in a row above the board, the opponent's pieces the player took in a row
    below it."""
    gx, _gy, _w, _h = _grid(board_box, margin)
    by0, by1 = float(board_box[1]), float(board_box[3]) + (LABEL_H if margin == OUTSIDE else 0)
    x0 = gx + index * CAP
    y0 = by0 - CAP_GAP - CAP if color == user else by1 + CAP_GAP
    return (x0, y0, x0 + CAP, y0 + CAP)


# ------------------------------------------------------------------------------ 2. the engine
def strength(elo):
    """How hard it searches, how far below the best move it may play, and how often it blunders --
    Normally 400 to 3200; a character pack may extend the floor to 150. Stockfish's own UCI_Elo stops at
    1320, so below that the weakness is ours: a wider miss, more candidates to miss with, and outright
    blunders, a draw from the game's own randomness. UNMEASURED starting values; tune on real games."""
    elo = max(150, min(3200, int(elo)))
    tol = 350 - (elo - 600) * 0.12 if elo >= 600 else 350 + (600 - elo) * 1.5
    return {"elo": elo, "depth": max(4, 5 + (elo - 600) // 250),
            "multipv": 16 if elo < 1200 else (8 if elo < 1800 else 6),
            "tolerance": int(max(20, tol)),
            "blunder": round(max(0.0, (1300 - elo) / 3000.0), 3)}


HANDFUL = 5                                            # how many moves a model is shown to choose from


def pool(cands, params, rng):
    """The moves this player may play now -> (moves, "genius" | "blunder" | ""). Those within its
    tolerance of the best; on a genius draw, the best alone; on a blunder draw, anything the engine
    listed. The rates are the strength's and the character's (its `consistency`), whichever is more."""
    if not cands:
        return [], ""
    if params.get("genius") and rng.random() < params["genius"]:
        return cands[:1], "genius"
    if params.get("blunder") and rng.random() < params["blunder"]:
        return list(cands), "blunder"
    return [c for c in cands if c["loss"] <= params["tolerance"]] or cands[:1], ""


def handful(moves, rng, n=HANDFUL):
    """At most `n` of the pool for a model to pick from: the pool's best first, the rest drawn with
    the game's randomness -- so a weak player's handful holds the weak moves it might make."""
    if len(moves) <= n:
        return list(moves)
    rest = list(moves[1:])
    out = [moves[0]]
    while len(out) < n and rest:
        out.append(rest.pop(int(rng.random() * len(rest)) % len(rest)))
    return out


EngineNotInstalled = _engine.EngineNotInstalled


def engine_path():
    """The Stockfish executable to use, or None when there is none (games.chess.engine.path)."""
    return _engine.path()


class Engine(object):
    """Stockfish at a strength, started without a window. Use as a context manager."""

    def __init__(self, elo=1500, path=None):
        self.params = strength(elo)
        self.sf = _engine.Engine(path, options={"UCI_LimitStrength": True,
                                                "UCI_Elo": max(1320, min(3190, self.params["elo"]))})

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        self.sf.close()

    def candidates(self, fen, multipv=None, depth=None):
        """Stockfish's best moves here, each with what it does -> [dict], best first."""
        board = chess.Board(fen)
        n = multipv or self.params["multipv"]
        out, seen = [], set()
        for info in self.sf.analyze(fen, depth=depth or self.params["depth"], multipv=n):
            pv = info["pv"]
            if pv[0].uci() in seen:
                continue
            seen.add(pv[0].uci())
            reply = ""
            if len(pv) > 1:                         # the other side's best answer (what a kibitzer tells them)
                after = board.copy(stack=False)
                after.push(pv[0])
                reply = after.san(pv[1])
            out.append(dict(_features(board, pv[0]), cp=_engine.score(info), mate=info.get("mate"), reply=reply))
        if out:
            best = max(c["cp"] for c in out)
            for c in out:
                c["loss"] = best - c["cp"]
        return out


def _features(board, move):
    """What a move does, for a persona to weigh."""
    mover = board.turn
    piece = board.piece_at(move.from_square)
    victim = board.piece_at(move.to_square)
    cap = board.is_capture(move)
    cap_value = 1 if board.is_en_passant(move) else (VALUE[victim.symbol().upper()] if victim else 0)
    dr = chess.square_rank(move.to_square) - chess.square_rank(move.from_square)
    forward = dr if mover == chess.WHITE else -dr
    feats = {"uci": move.uci(), "san": board.san(move), "piece": piece.symbol().upper(),
             "capture": bool(cap), "captured_value": cap_value if cap else 0,
             "check": board.gives_check(move), "castling": board.is_castling(move),
             "promotion": bool(move.promotion), "forward": forward}
    board.push(move)
    try:
        ek = board.king(board.turn)
        zone = [s for s in chess.SQUARES if ek is not None and chess.square_distance(s, ek) == 1]
        feats["king_zone"] = sum(1 for s in zone if board.is_attacked_by(mover, s))
        to = move.to_square
        attacked = board.is_attacked_by(not mover, to)
        defended = board.is_attacked_by(mover, to)
        feats["hanging"] = bool(attacked and not defended and piece.piece_type != chess.KING)
        feats["defended"] = bool(defended)
    finally:
        board.pop()
    return feats


# ------------------------------------------------------------------------------ the persona
DEFAULT_TRAITS = {"aggression": 0.5, "caution": 0.5, "risk": 0.3}


def persona_pick(cands, traits, rng, elo=1500, limit=True):
    """The move this character plays among the engine's candidates, with no model. Every draw comes
    from `rng`, in candidate order, so a replay picks the same move. `limit=False` when the caller
    already chose the pool (see `pool`)."""
    tol = strength(elo)["tolerance"]
    pool = ([c for c in cands if c["loss"] <= tol] or cands[:1]) if limit else list(cands)
    t = dict(DEFAULT_TRAITS, **(traits or {}))
    a, cau, risk = float(t["aggression"]), float(t["caution"]), float(t["risk"])
    best, best_s = None, None
    for c in pool:
        if c.get("mate") is not None and c["mate"] > 0 and c["loss"] == 0:
            s = 1e9                                        # a forced mate is never passed over
        else:
            s = -(c["loss"] / 100.0) * (1.5 - risk)
            s += a * (0.6 * c["captured_value"] + (0.8 if c["check"] else 0.0)
                      + 0.25 * c["king_zone"] + (0.3 if c["forward"] > 0 else 0.0))
            s += cau * ((0.6 if c["castling"] else 0.0) + (0.4 if c["defended"] else 0.0)
                        - (0.8 if c["hanging"] else 0.0) + (0.3 if c["forward"] < 0 else 0.0))
        s += 0.05 * rng.random()                           # a seeded tie-break
        if best_s is None or s > best_s:
            best, best_s = c, s
    return best


def _flags(c):
    f = []
    if c.get("mate") is not None and c["mate"] > 0:
        f.append("mates in %d" % c["mate"])
    if c["capture"]:
        f.append("captures")
    if c["check"]:
        f.append("check")
    if c["castling"]:
        f.append("castles")
    if c["hanging"]:
        f.append("leaves the piece hanging")
    if c["loss"] >= 100:
        f.append("about %.1f pawns worse than the best" % (c["loss"] / 100.0))
    return f


# One vocabulary for the model parser and the portraits; new feelings must not silently disappear.
from paperdaemon.pipeline.games.faces import EMOTIONS


def situation(cands):
    """How the game stands for the side to move, in words, from the engine's best line -- the TRUTH a
    character's feelings answer to, whatever its face shows."""
    if not cands:
        return ""
    c = cands[0]
    if c.get("mate") is not None:
        return ("you can force mate in %d" % c["mate"]) if c["mate"] > 0 else ("you are getting mated in %d" % -c["mate"])
    cp = c["cp"]
    words = ("winning clearly" if cp >= 300 else "better" if cp >= 100 else "about level" if cp > -100
             else "worse" if cp > -300 else "losing badly")
    return "%s (%+.1f pawns)" % (words, cp / 100.0)


def facts(state):
    """The game's facts as the character's lines must respect them: who plays which side, who moved
    first, what move it is and what it answers. A model left to infer these told the player "I strike
    first" while replying to 1. e4 as Black."""
    board = chess.Board(state["fen"])
    you = "White" if state["colors"]["engine"] == "w" else "Black"
    them = "Black" if you == "White" else "White"
    first = "White" if chess.Board(state["start_fen"]).turn == chess.WHITE else "Black"
    last = state["history"][-1] if state["history"] else None
    to_move = "your turn" if ("w" if board.turn == chess.WHITE else "b") == state["colors"]["engine"] else "the player's turn"
    out = ["You play %s and the player plays %s. %s moved first, so %s made the first move of this game."
           % (you, them, first, "you" if first == you else "the player"),
           "It is move %d, %s%s." % (board.fullmove_number, to_move,
                                     ("; the player's last move was %s" % last["san"]) if last and last.get("by") == "user" else ""),
           "The moves so far: %s" % (movetext(state) or "none yet")]
    return out


def persona_text(state):
    """Who the opponent is, as the model is told: a roster character's profile from the cast tooling (RC.brief), read
    fresh each time -- the notepad keeps the character's id, never its profile -- else the game's own words for an
    opponent that is no roster character."""
    p = state["persona"]
    if p.get("character"):
        try:
            from paperdaemon.pipeline.games import characters as RC
            return RC.brief(p["character"], "chess", front=p.get("front"), shows=p.get("shows"))
        except Exception:
            pass
    return p.get("text") or p.get("profile") or "a steady club player"


def llm_prompt(state, cands, context="", stands="", plan=None, advise=False):
    """What a model is asked when it plays the character: pick one of these, what it truly feels, and
    -- only when the table says the character speaks this turn -- one line, marked true or not. The
    feeling is the character's own state; what the table sees of it is the host's to derive
    (rm_table). `plan` is rm_table.pre_turn's; `advise` lists the player's best answer to each move
    (a kibitzer tells them)."""
    p = state["persona"]
    lines = ["You are playing chess as this character: %s" % persona_text(state),
             "Traits, 0 to 1: aggression %.1f, caution %.1f, risk %.1f." % (
                 p["traits"]["aggression"], p["traits"]["caution"], p["traits"]["risk"])] + facts(state)
    if stands:
        lines.append("How the game truly stands for you right now: %s." % stands)
    speak = True if plan is None else plan["speak"]
    if plan:
        lines += plan["prompt_lines"]
    else:
        mood = p.get("mood") or {}
        if mood.get("feels"):
            lines.append("A moment ago you felt %s%s." % (mood["feels"], (" at %s" % mood["at"]) if mood.get("at") else ""))
    if context:
        lines.append(context)
    lines.append("Choose ONE of these moves, the one this character would play:")
    for i, c in enumerate(cands, 1):
        f = _flags(c)
        if advise and c.get("reply"):
            f = f + ["then the player's best answer is %s" % c["reply"]]
        lines.append("%d. %s%s" % (i, c["san"], ("  (%s)" % ", ".join(f)) if f else ""))
    lines += ["Answer with the move exactly as listed on the first line.",
              "Then a line FEEL: what the character truly feels now -- one of %s -- then how strongly, 1 to "
              "10, and at whom if anyone (\"at the player\"). Feel honestly; you need not SHOW it." % ", ".join(EMOTIONS)]
    if plan:
        lines.append("Then FACE: one fitting signature ID from the private menu above, or none. Not a tell.")
    if speak:
        lines += ["Then a line SAY: one short thing the character says out loud, in their own voice (it may "
                  "bluff or hide the feeling). What it says about the game must be true to the facts above and to "
                  "the move you chose, unless the character is lying on purpose. Saying the move you played, in the "
                  "character's own way (\"Knight to f6.\"), is welcome: the strip has no other line that says it.",
                  "Then a line TRUTH: true, lie or bluff -- whether what the character said was true. Nobody at "
                  "the table sees this line."]
        if advise:
            lines.append("This character cannot help telling the player their best move: work the player's best "
                         "answer to your chosen move into what you say.")
    else:
        lines.append("No SAY line this turn: the character says nothing.")
    return "\n".join(lines)


def parse_truth(text):
    """The TRUTH line -> "true", "lie", "bluff" or ""."""
    m = re.search(r"(?im)^\s*TRUTH:\s*(true|lie|bluff)", str(text or ""))
    return m.group(1).lower() if m else ""


def situations_before(state, cid, cands):
    """What the game reports for the opponent before it moves (rm_table.SITUATIONS): how it stands,
    whether the player's last move swung the game or took a piece, whether it is in danger."""
    board = chess.Board(state["fen"])
    t = state.setdefault("table", {})
    out = set()
    if len([h for h in state["history"] if h.get("by") == "engine"]) == 0:
        out.add("start")
    c = cands[0] if cands else None
    if c:
        cp = 100000 if (c.get("mate") or 0) > 0 else -100000 if (c.get("mate") or 0) < 0 else c["cp"]
        out.add("winning" if cp >= 150 else "losing" if cp <= -150 else "close" if abs(cp) < 50 else "even")
        prev = (t.get("eval") or {}).get(cid)
        if prev is not None and abs(cp) < 90000 and abs(prev) < 90000:
            if cp - prev >= 150:
                out |= {"their_blunder", "turning"}
            elif cp - prev <= -150:
                out.add("slipping")
    lost = len(state["captured"][state["colors"]["engine"]])
    if lost > (t.get("lost") or {}).get(cid, 0):
        out.add("hit")
    if board.is_check():
        out.add("danger")
    out.discard("even")
    return out


def situations_after(state, cid, chosen, change, blundered):
    """What the game reports once the opponent has moved: a capture, an attack, a blunder, the end."""
    t = state.setdefault("table", {})
    out = set()
    if change.get("captured"):
        out.add("scored")
    if chosen.get("check") or (chosen.get("king_zone") or 0) >= 2:
        out.add("attacking")
    if blundered:
        out.add("blundered")
    if state["status"] != "playing":
        won = (state["result"] == "1-0") == (state["colors"]["engine"] == "w") and state["result"] != "1/2-1/2"
        out.add("won" if won else "lost" if state["result"] != "1/2-1/2" else "close")
    t.setdefault("eval", {})[cid] = chosen.get("cp") if chosen.get("mate") is None else (100000 if chosen["mate"] > 0 else -100000)
    t.setdefault("lost", {})[cid] = len(state["captured"][state["colors"]["engine"]])
    return out


def parse_feel(text):
    """The FEEL (or older MOOD) line -> (emotion, intensity 0..1, at) or ("", 0.6, "")."""
    m = re.search(r"(?im)^\s*(?:FEEL|MOOD):\s*([A-Za-z]+)[,\s]*(\d{1,2})?(?:[^\n]*?\bat\s+([^\n.;]+))?", str(text or ""))
    if not m or m.group(1).lower() not in EMOTIONS:
        return "", 0.6, ""
    n = int(m.group(2)) if m.group(2) else 6
    return m.group(1).lower(), max(0.1, min(1.0, n / 10.0)), (m.group(3) or "").strip()[:40]



def felt_by_rule(cands, blundered=False):
    """A feeling from the position alone, for a turn with no model."""
    if blundered:
        return "confused", 0.6
    if not cands:
        return "thinking", 0.4
    c = cands[0]
    if c.get("mate") is not None:
        return ("smug", 0.9) if c["mate"] > 0 else ("worried", 0.9)
    cp = c["cp"]
    return (("smug", .8) if cp >= 300 else ("happy", .5) if cp >= 100 else ("thinking", .4) if cp > -100
            else ("worried", .6) if cp > -300 else ("worried", .9))


def _norm_san(s):
    return re.sub(r"[+#!?\s]", "", str(s or ""))


def parse_llm_pick(text, cands):
    """The listed move a model named -> (candidate, what it says) or (None, said). Only a listed move
    counts: a move off the list is refused, whatever it is."""
    text = str(text or "")
    said = ""
    m = re.search(r"(?im)^\s*SAY:\s*(.+)$", text)
    if m:
        said = m.group(1).strip().strip('"')
    first = text.strip().splitlines()[0] if text.strip() else ""
    by_san = {_norm_san(c["san"]): c for c in cands}
    by_uci = {c["uci"]: c for c in cands}
    for tok in re.findall(r"[A-Za-z0-9=+#\-]+", first):
        t = _norm_san(tok)
        if t in by_san:
            return by_san[t], said
        if t.lower() in by_uci:
            return by_uci[t.lower()], said
    m = re.match(r"\s*(\d+)\s*[.)]?\s*$", first)
    if m and 1 <= int(m.group(1)) <= len(cands):
        return cands[int(m.group(1)) - 1], said
    return None, said


# ------------------------------------------------------------------------------ 3. the state
def new_game(doc, page_id, user_color="w", persona="", traits=None, elo=1500, seed=None, fen=None,
             game_id=None):
    """A fresh game's state: pieces from the position, nothing placed on a page yet."""
    board = chess.Board(fen) if fen else chess.Board()
    seed = seed or new_seed()
    now = int(time.time())
    st = {"game": "chess", "version": 1, "id": game_id or "chess-" + seed[:8],
          "doc": doc, "page_id": page_id,
          "start_fen": board.fen(), "fen": board.fen(), "history": [],
          "rng": {"seed": seed, "draws": 0},
          "persona": {"text": persona, "traits": dict(DEFAULT_TRAITS, **(traits or {}))},
          "strength": {"elo": int(elo)},
          "colors": {"user": user_color, "engine": "b" if user_color == "w" else "w"},
          "flipped": user_color == "b",
          "board": {"hash": None, "name": None, "box": list(BOARD_BOX), "margin": 0, "labels": "outside"},
          "pieces": {}, "captured": {"w": [], "b": []},
          "status": "playing", "result": None, "created": now, "updated": now}
    for sq, pc in sorted(board.piece_map().items()):
        c = "w" if pc.color == chess.WHITE else "b"
        name = chess.square_name(sq)
        st["pieces"]["%s%s-%s" % (c, pc.symbol().upper(), name)] = {
            "color": c, "kind": pc.symbol().upper(), "square": name, "captured": False,
            "hash": None, "name": None}
    return st


def pid_at(state, square):
    for pid, p in state["pieces"].items():
        if not p["captured"] and p["square"] == square:
            return pid
    return None


def apply_move(state, uci):
    """Play a legal move on the state -> what changed: {san, moved: [(pid, from, to)], captured,
    promoted}. Raises ValueError on an illegal one."""
    board = chess.Board(state["fen"])
    move = chess.Move.from_uci(uci)
    if move not in board.legal_moves:
        raise ValueError("illegal move %s" % uci)
    san = board.san(move)
    frm, to = chess.square_name(move.from_square), chess.square_name(move.to_square)
    mover = pid_at(state, frm)
    out = {"san": san, "uci": uci, "moved": [], "captured": None, "promoted": None}
    victim_sq = to
    if board.is_en_passant(move):
        victim_sq = chess.square_name(move.to_square + (-8 if board.turn == chess.WHITE else 8))
    victim = pid_at(state, victim_sq) if board.is_capture(move) else None
    if victim:
        v = state["pieces"][victim]
        v["captured"] = True
        v["square"] = None
        state["captured"][v["color"]].append(victim)
        out["captured"] = victim
    if board.is_castling(move):
        rank = to[1]
        rf, rt = ("h", "f") if to[0] == "g" else ("a", "d")
        rook = pid_at(state, rf + rank)
        state["pieces"][rook]["square"] = rt + rank
        out["moved"].append((rook, rf + rank, rt + rank))
    state["pieces"][mover]["square"] = to
    out["moved"].insert(0, (mover, frm, to))
    if move.promotion:
        state["pieces"][mover]["kind"] = chess.piece_symbol(move.promotion).upper()
        out["promoted"] = mover
    by = "user" if (board.turn == chess.WHITE) == (state["colors"]["user"] == "w") else "engine"
    board.push(move)
    state["fen"] = board.fen()
    state["history"].append({"ply": len(state["history"]) + 1, "uci": uci, "san": san, "by": by})
    oc = board.outcome(claim_draw=True)
    if oc is not None:
        state["status"] = oc.termination.name.lower()
        state["result"] = oc.result()
    state["updated"] = int(time.time())
    return out


def play_opening(state, moves):
    """THE MOVES THE REQUEST ALREADY PLAYED ("Let's play chess. I'm white. e4"), applied to a new game in
    order from its start, each read as SAN or squares and checked by the rules here -- the model only
    passes them on, it never holds the position. Stops at the first move that cannot be read or is not
    legal. -> (the moves played, in SAN; the one that was not, or None)."""
    played = []
    for raw in list(moves or [])[:40]:
        text = re.sub(r"^\s*\d+\s*\.+\s*", "", str(raw or "")).strip()       # "1. e4", "1... e5"
        if not text:
            continue
        uci = parse_text_move(state, text)
        if uci is None:
            return played, str(raw).strip()
        played.append(apply_move(state, uci)["san"])
        if state["status"] != "playing":
            break
    return played, None


def movetext(state, last=None):
    """'1. e4 e5 2. Nf3' -- the whole game, or its last `last` plies."""
    board = chess.Board(state["start_fen"])
    parts = []
    hist = state["history"]
    start = 0 if last is None else max(0, len(hist) - last)
    for i, h in enumerate(hist):
        if i >= start:
            if board.turn == chess.WHITE:
                parts.append("%d. %s" % (board.fullmove_number, h["san"]))
            else:
                parts.append(("%d... %s" % (board.fullmove_number, h["san"])) if i == start else h["san"])
        board.push(chess.Move.from_uci(h["uci"]))
    return " ".join(parts)


def pgn(state):
    """The game as PGN, from its starting position."""
    board = chess.Board(state["start_fen"])
    for h in state["history"]:
        board.push(chess.Move.from_uci(h["uci"]))
    who = (state["persona"].get("name") or state["persona"].get("text") or "PaperDaemon")[:60]
    return chess.pgn(board, {"Event": "PaperDaemon chess %s" % state["id"],
                             "White": "You" if state["colors"]["user"] == "w" else who,
                             "Black": who if state["colors"]["user"] == "w" else "You",
                             "Result": state["result"] or "*"})


def summary_lines(state):
    """What the notepad says about the game in words (the JSON follows it)."""
    board = chess.Board(state["fen"])
    who = state["persona"].get("name") or state["persona"].get("text") or "a steady club player"
    you = "White" if state["colors"]["user"] == "w" else "Black"
    head = "chess game %s: you play %s against %s, at about %d" % (state["id"], you, who, state["strength"]["elo"])
    if state["status"] == "playing":
        tail = "%s to move" % ("White" if board.turn == chess.WHITE else "Black")
    else:
        tail = "game over: %s, %s" % (state["status"].replace("_", " "), state["result"])
    return [head, "%d moves so far; %s" % (len(state["history"]), tail),
            "moves: %s" % (movetext(state, last=16) or "none yet")]


# ------------------------------------------------------------------------------ notepad storage
# One entry per game in rm-notepad/<doc>.md, in the notepad's own entry format (a "## <time>, page id
# <id>" header and "- " lines), with the state as JSON in an HTML comment after the words. The
# entry is rewritten in place on every save, so the file holds one current state per game.
_BLOCK = re.compile(r"<!-- game-state (\w+) (\S+)\n(.*?)\n-->", re.S)


def notepad_file(doc):
    return os.path.join(NOTEPAD_DIR, "%s.md" % doc)


def _entries(text):
    return [e for e in re.split(r"(?m)^(?=## )", text) if e.strip()]


SUMMARIES = {}          # game kind -> its summary_lines, for the games that are not chess (rm_adventure)


def _stored(state):
    """The state as the notepad keeps it: a roster character by its id alone. Its profile comes from the cast
    tooling when a prompt needs it (persona_text); only its memories live in the notebook."""
    per = state.get("persona")
    if not (isinstance(per, dict) and per.get("character")):
        return state
    return dict(state, persona=dict((k, v) for k, v in per.items() if k not in ("profile", "text")))


def _entry(state):
    body = json.dumps(_stored(state), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    body = body.replace("-->", "--\\u003e")               # the comment must not end inside the JSON
    lines = ["## %s, page id %s" % (time.strftime("%Y-%m-%d %H:%M"), state["page_id"])]
    lines += ["- %s" % " ".join(str(l).split())[:400] for l in SUMMARIES.get(state["game"], summary_lines)(state)]
    lines += ["<!-- game-state %s %s" % (state["game"], state["id"]), body, "-->", ""]
    return "\n".join(lines) + "\n"


def save_state(state):
    """Write the game's entry: in place if it is there, at the end if it is new."""
    state["updated"] = int(time.time())
    path = notepad_file(state["doc"])
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        text = ""
    mark = "<!-- game-state %s %s\n" % (state["game"], state["id"])
    ents = _entries(text)
    new = _entry(state)
    for i, e in enumerate(ents):
        if mark in e:
            ents[i] = new
            break
    else:
        ents.append(new)
    out = "".join(e if e.endswith("\n\n") else e.rstrip("\n") + "\n\n" for e in ents)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    os.replace(tmp, path)
    return path


def games(doc):
    """Every game state in the notebook's notepad."""
    try:
        text = open(notepad_file(doc), encoding="utf-8").read()
    except OSError:
        return []
    out = []
    for m in _BLOCK.finditer(text):
        try:
            out.append(json.loads(m.group(3)))
        except ValueError:
            continue
    return out


def load_state(doc, game_id=None, page_id=None):
    """A game by its id, or the newest game on a page."""
    gs = games(doc)
    if game_id:
        gs = [g for g in gs if g.get("id") == game_id]
    if page_id:
        # a game may own several pages (an adventure: its sheet and every turn); page_id is where it
        # is played now
        gs = [g for g in gs if g.get("page_id") == page_id or page_id in (g.get("pages") or [])]
    return max(gs, key=lambda g: g.get("updated", 0)) if gs else None


def game_for_page(doc, page_id):
    """The game that lives on this page, if the page is a game page."""
    return load_state(doc, page_id=page_id)


# ------------------------------------------------------------------------------ 5. the pictures
# ONLY WHAT THE PLAYER MAY MOVE IS ITS OWN PICTURE (rule 5; otherwise the opponent's pieces and the
# captured pieces could be dragged on the tablet). The board, the opponent's pieces and every captured
# piece are ONE picture, the LAYER, drawn again whenever any of them changes; each of the player's
# pieces on the board is its own picture on top of it. A new layer lies over everything (the tablet
# stacks by id), so after one the player's pieces are brought to the front (rm_images.to_front).
def layer_box(board_box, margin=0):
    """The layer's box on the page: the board with a captured row above and below it, and on a board with its
    labels outside, the label margins to its left and below it."""
    bx0, by0, bx1, by1 = (float(v) for v in board_box)
    if margin == OUTSIDE:
        return (bx0 - LABEL_W, by0 - CAP_GAP - CAP, bx1, by1 + LABEL_H + CAP_GAP + CAP)
    return (bx0, by0 - CAP_GAP - CAP, bx1, by1 + CAP_GAP + CAP)


def _static(state):
    """What the layer shows, as a signature: the opponent's pieces, every captured piece, the side."""
    opp = state["colors"]["engine"]
    on = sorted([p["square"], p["color"], p["kind"]] for p in state["pieces"].values()
                if not p["captured"] and p["color"] == opp)
    caps = [[c, [state["pieces"][pid]["kind"] for pid in state["captured"][c]]] for c in "wb"]
    return json.dumps([on, caps, bool(state["flipped"]), [round(float(v), 1) for v in state["board"]["box"]]])


def layer_png(state, out):
    """Draw the layer: the board, the opponent's pieces on their squares, the captured rows."""
    from PIL import Image
    bb = tuple(float(v) for v in state["board"]["box"])
    m = margin_of(state)
    L = layer_box(bb, m)
    im = Image.new("RGBA", (int(round(L[2] - L[0])), int(round(L[3] - L[1]))), (255, 255, 255, 0))

    def paste(png, box):
        w, h = int(round(box[2] - box[0])), int(round(box[3] - box[1]))
        with (Image.open(png) if isinstance(png, str) else png.copy()) as src:
            pic = src.convert("RGBA")
            if pic.size != (w, h):
                pic = pic.resize((w, h), Image.LANCZOS)
        im.alpha_composite(pic, (int(round(box[0] - L[0])), int(round(box[1] - L[1]))))
    if m == LEGACY_MARGIN:
        paste(board_png(state["flipped"]), bb)
    elif m == OUTSIDE:
        paste(board_image(state["flipped"], int(round(bb[2] - bb[0]))), bb)
        _labels(im, bb, L, state["flipped"])
    else:
        paste(inside_board_image(state["flipped"], int(round(bb[2] - bb[0]))), bb)
    for pid, p in sorted(state["pieces"].items()):
        if p["captured"]:
            paste(piece_png(p["color"], p["kind"]),
                  captured_box(p["color"], state["captured"][p["color"]].index(pid), bb, state["colors"]["user"], m))
        elif p["color"] == state["colors"]["engine"]:
            paste(piece_png(p["color"], p["kind"]), piece_box(p["square"], bb, state["flipped"], m))
    im.save(out)
    return out


def _labels(im, bb, L, flipped):
    """The rank numbers to the left of the squares and the file letters below them, bold, in the board's
    green, each centered on its rank or file."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    sq = (bb[2] - bb[0]) / 8.0
    font = paths.pil_font("reMarkableSans-Bold", int(round(LABEL_H * 0.62)))
    for i in range(8):
        _, r = _file_rank(0, i, flipped)
        f, _ = _file_rank(i, 7, flipped)
        for t, cx, cy in ((str(r + 1), bb[0] - LABEL_W / 2.0, bb[1] + (i + 0.5) * sq),
                          ("abcdefgh"[f], bb[0] + (i + 0.5) * sq, bb[3] + LABEL_H / 2.0)):
            l, tp, rt, bt = d.textbbox((0, 0), t, font=font)
            d.text((cx - L[0] - (l + rt) / 2.0, cy - L[1] - (tp + bt) / 2.0), t, font=font, fill=GREEN + (255,))


def _put_layer(doc, page_no, state, page_id=None):
    from paperdaemon.pipeline.page import images as IM
    queue = os.path.join(paths.state_dir(), "rm-queue")
    os.makedirs(queue, exist_ok=True)
    png = layer_png(state, os.path.join(queue, "_chess_layer_%d.png" % int(time.time() * 1000)))
    box = layer_box(state["board"]["box"], margin_of(state))
    try:
        r = IM.insert(doc, page_no, png, box, page_id=page_id)
    finally:
        os.remove(png)
    state["board"].update(hash=r["hash"], name=r["name"], layer=True, drawn=_static(state))
    IM.record_placement(r["doc"], page_no, r["name"], box, hash=r["hash"], kind="chess-board", game=state["id"])
    return r


def _mine(state):
    """The player's pieces still on the board: the only pieces with pictures."""
    u = state["colors"]["user"]
    return [pid for pid, p in sorted(state["pieces"].items()) if p["color"] == u and not p["captured"]]


def _put_piece(doc, page_no, state, pid, box, page_id=None):
    from paperdaemon.pipeline.page import images as IM
    p = state["pieces"][pid]
    r = IM.insert(doc, page_no, piece_png(p["color"], p["kind"]), box, page_id=page_id)
    p.update(hash=r["hash"], name=r["name"])
    IM.record_placement(r["doc"], page_no, r["name"], box, hash=r["hash"], kind="chess-piece",
                        game=state["id"], piece=pid, square=p["square"])


def setup_page(doc, page_no, state, page_id=None):
    """The layer, then each of the player's pieces on top of it, each its own picture."""
    bb = tuple(state["board"]["box"])
    for p in state["pieces"].values():
        p.update(hash=None, name=None)
    _put_layer(doc, page_no, state, page_id)
    for pid in _mine(state):
        _put_piece(doc, page_no, state, pid, piece_box(state["pieces"][pid]["square"], bb, state["flipped"],
                                                      margin_of(state)), page_id)
    return state


def _pictures(doc, page_no, state, page_id=None):
    """{hash: [live pictures with it]} -- more than one when a picture was copied on the tablet."""
    from paperdaemon.pipeline.page import images as IM
    out = {}
    for im in IM.items(doc, page_no, page_id=page_id):
        out.setdefault(im["hash"], []).append(im)
    return out


def _board_now(state, by_hash):
    """Where the board sits NOW, read off its picture (the player may have dragged or stretched it)."""
    bb = tuple(float(v) for v in state["board"]["box"])
    ims = by_hash.get(state["board"]["hash"]) or []
    if not ims:
        return bb
    if not state["board"].get("layer"):                # a game from before the layer: the picture is the board
        return tuple(ims[0]["box"])
    L = layer_box(bb, margin_of(state))
    x0, y0, x1, y1 = ims[0]["box"]
    sx, sy = (x1 - x0) / (L[2] - L[0]), (y1 - y0) / (L[3] - L[1])
    return (x0 + (bb[0] - L[0]) * sx, y0 + (bb[1] - L[1]) * sy, x0 + (bb[2] - L[0]) * sx, y0 + (bb[3] - L[1]) * sy)


def read_pictures(doc, page_no, state, page_id=None):
    """Where the board and each of the player's pieces are now -> (board box, {pid: {box, center,
    square} or None when its picture is gone}). Squares are read against the board as it sits NOW,
    since that is what the player moved the piece on. A piece copied on the tablet is the picture
    nearest where the state has it: a copy never makes a move (tidy takes it away)."""
    by_hash = _pictures(doc, page_no, state, page_id)
    board_box = _board_now(state, by_hash)
    want = targets(state, board_box)
    seen = {}
    for pid in want:
        p = state["pieces"][pid]
        ims = by_hash.get(p.get("hash"))
        if not ims:
            seen[pid] = None
            continue
        if len(ims) > 1:
            t = want[pid]
            ims = sorted(ims, key=lambda im: abs(im["box"][0] - t[0]) + abs(im["box"][1] - t[1]))
        x0, y0, x1, y1 = ims[0]["box"]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        seen[pid] = {"box": tuple(ims[0]["box"]), "center": (cx, cy),
                     "square": square_at(cx, cy, board_box, state["flipped"], margin_of(state))}
    return board_box, seen


def _why_illegal(board, move, piece_name):
    frm, to = chess.square_name(move.from_square), chess.square_name(move.to_square)
    if board.is_pseudo_legal(move):
        return "that move would leave your king in check"
    if board.is_check():
        return "your king is in check, and %s from %s to %s does not get it out" % (piece_name, frm, to)
    return "a %s cannot move from %s to %s" % (piece_name, frm, to)


_NAMES = {"P": "pawn", "N": "knight", "B": "bishop", "R": "rook", "Q": "queen", "K": "king"}


def infer_move(state, seen, promote="q"):
    """The move the pictures show -> {"ok": True, "uci": ... or None} or {"ok": False, "reason"}.

    Squares are drop zones: a piece counts as moved when its picture's center sits on another square
    than the state says. What can happen: one of your pieces moved (a capture when it lands on an
    opponent's piece, castling when the king moves two files, en passant, promotion to a queen unless
    told otherwise); castling with the king AND the rook moved; a capture where you also pulled the
    captured piece aside. Anything else is refused with a reason, and `tidy` then puts every piece
    back where the state has it."""
    if state["status"] != "playing":
        return {"ok": False, "reason": "the game is over (%s)" % state["result"]}
    board = chess.Board(state["fen"])
    user = state["colors"]["user"]
    moved = []
    for pid, p in state["pieces"].items():
        s = seen.get(pid)
        if p["captured"] or s is None:
            continue                       # an erased picture is no move: tidy draws it again
        if s["square"] != p["square"]:
            moved.append((pid, p["square"], s["square"]))
    if not moved:
        return {"ok": True, "uci": None}
    turn = "w" if board.turn == chess.WHITE else "b"
    if turn != user:
        return {"ok": False, "reason": "it is your opponent's turn; wait for its move"}
    mine = [m for m in moved if state["pieces"][m[0]]["color"] == user]
    theirs = [m for m in moved if state["pieces"][m[0]]["color"] != user]
    if not mine:
        return {"ok": False, "reason": "that is your opponent's piece"}
    if len(mine) == 2:
        k = [m for m in mine if state["pieces"][m[0]]["kind"] == "K"]
        r = [m for m in mine if state["pieces"][m[0]]["kind"] == "R"]
        if k and r and k[0][2] and r[0][2] and abs("abcdefgh".index(k[0][2][0]) - "abcdefgh".index(k[0][1][0])) == 2:
            rf, rt = ("h", "f") if k[0][2][0] == "g" else ("a", "d")
            if r[0][1] == rf + k[0][1][1] and r[0][2] == rt + k[0][1][1]:
                mine = k                                  # castling, both pieces moved: the king says it
    if len(mine) != 1:
        return {"ok": False, "reason": "several pieces moved at once (%s); move one piece a turn"
                % ", ".join("%s from %s" % (_NAMES[state["pieces"][m[0]]["kind"]], m[1]) for m in mine)}
    pid, frm, to = mine[0]
    kind = state["pieces"][pid]["kind"]
    if to is None:
        return {"ok": False, "reason": "the %s was set down off the board" % _NAMES[kind]}
    for opid, ofrom, _oto in theirs:
        if ofrom != to:
            return {"ok": False, "reason": "your opponent's %s on %s was moved too"
                    % (_NAMES[state["pieces"][opid]["kind"]], ofrom)}
    move = chess.Move(chess.parse_square(frm), chess.parse_square(to))
    if kind == "P" and to[1] in "18":
        move = chess.Move(move.from_square, move.to_square, promotion=chess.Piece.from_symbol(promote.upper()).piece_type)
    if move not in board.legal_moves:
        return {"ok": False, "reason": _why_illegal(board, move, _NAMES[kind])}
    return {"ok": True, "uci": move.uci(), "san": board.san(move)}


def targets(state, board_box):
    """Where each of the player's piece pictures belongs: its square."""
    return {pid: piece_box(state["pieces"][pid]["square"], board_box, state["flipped"], margin_of(state))
            for pid in _mine(state)}


def redraw(doc, page_no, state, page_id=None):
    """Every picture of this game off the page, then the layer and the player's pieces put back from
    the state -- for a layer that is gone (one put back afterwards would lie over the pieces), and
    for a game drawn before the layer existed (every piece its own picture)."""
    from paperdaemon.pipeline.page import images as IM
    mine = set([state["board"].get("hash")] + [p.get("hash") for p in state["pieces"].values()]) - {None}
    items = [im["item"] for ims in _pictures(doc, page_no, state, page_id).values() for im in ims
             if im["hash"] in mine and im.get("item")]
    if items:
        IM.remove_items(doc, page_no, items, page_id=page_id)
    state["board"]["box"] = list(BOARD_BOX)
    state["board"].update(margin=0, labels="outside")  # drawn again from scratch: today's board
    setup_page(doc, page_no, state, page_id)


def tidy(doc, page_no, state, page_id=None, tol=0.5):
    """PUT THE PAGE BACK TO THE STATE: the layer where it belongs and showing the position (drawn
    again when the opponent's pieces or the captured rows changed), each of the player's pieces
    exactly on its square and on top, copies gone, a piece whose picture was erased drawn again, a
    piece that was taken gone into the layer. So a move made, refused or half-made always ends with
    the page showing the last legal position at the player's turn. -> what was done."""
    from paperdaemon.pipeline.page import images as IM
    by_hash = _pictures(doc, page_no, state, page_id)
    layers = by_hash.get(state["board"]["hash"]) or []
    if not layers or not state["board"].get("layer"):
        redraw(doc, page_no, state, page_id)
        return ["redrawn"]
    board_box = tuple(float(v) for v in state["board"]["box"])
    want = targets(state, board_box)
    todo, extra, missing = [], [], []
    extra += [im["item"] for im in layers[1:]]
    for pid, p in state["pieces"].items():             # taken, or the opponent's: in the layer now
        if pid not in want and p.get("hash"):
            extra += [im["item"] for im in by_hash.get(p["hash"]) or []]
            p.update(hash=None, name=None)
    for pid, box in want.items():
        ims = sorted(by_hash.get(state["pieces"][pid].get("hash")) or [],
                     key=lambda im: abs(im["box"][0] - box[0]) + abs(im["box"][1] - box[1]))
        if not ims:
            missing.append(pid)
            continue
        extra += [im["item"] for im in ims[1:]]
        if any(abs(a - b) > tol for a, b in zip(ims[0]["box"], box)):
            todo.append((state["pieces"][pid]["hash"], box))
    stale = state["board"].get("drawn") != _static(state)
    if stale:
        extra.append(layers[0]["item"])
    elif any(abs(a - b) > tol for a, b in zip(layers[0]["box"], layer_box(board_box, margin_of(state)))):
        todo.append((state["board"]["hash"], layer_box(board_box, margin_of(state))))
    if extra:
        IM.remove_items(doc, page_no, extra, page_id=page_id)
    done = IM.move(doc, page_no, todo, page_id=page_id) if todo else []
    if stale:
        _put_layer(doc, page_no, state, page_id)
        done.append({"key": "layer", "redrawn": True})
    for pid in missing:
        _put_piece(doc, page_no, state, pid, want[pid], page_id)
        done.append({"key": pid, "restored": True})
    if stale:
        front = [state["pieces"][pid]["hash"] for pid in want if pid not in missing and state["pieces"][pid].get("hash")]
        if front:
            IM.to_front(doc, page_no, front, page_id=page_id)
    return done


def _swap_kind(doc, page_no, state, pid, page_id=None):
    """The player's promoted pawn: its picture becomes its new piece's, on its square, on top."""
    from paperdaemon.pipeline.page import images as IM
    p = state["pieces"][pid]
    if pid not in _mine(state):
        return                                          # the opponent's promotion is the layer's
    ims = _pictures(doc, page_no, state, page_id).get(p.get("hash")) or []
    if ims:
        IM.remove_items(doc, page_no, [im["item"] for im in ims], page_id=page_id)
    _put_piece(doc, page_no, state, pid, piece_box(p["square"], tuple(state["board"]["box"]), state["flipped"],
                                                  margin_of(state)), page_id)


def _finish(doc, page_no, state, change, page_id=None):
    tidy(doc, page_no, state, page_id)                 # the layer drawn again, the player's pieces on top
    if change.get("promoted"):
        _swap_kind(doc, page_no, state, change["promoted"], page_id)


def user_turn(doc, page_no, state, page_id=None, promote="q"):
    """Read the player's move off the pictures, check it, play it, and tidy the page. An illegal
    move is refused and every piece goes back. -> {ok, san | reason}"""
    _bb, seen = read_pictures(doc, page_no, state, page_id)
    res = infer_move(state, seen, promote=promote)
    if not res["ok"] or not res.get("uci"):
        tidy(doc, page_no, state, page_id)
        return res
    change = apply_move(state, res["uci"])
    _finish(doc, page_no, state, change, page_id)
    return dict(res, change=change)


def recall_block(state, about=""):
    """What the opponent remembers of the player in this notebook (rm_residents), for the model's
    prompt: their own memories, cross-referenced with what is being said -- for one with alters, only
    what whoever is out can reach. The game on this page is on the board already, so it is left out.
    -> text, or "" when there is nothing."""
    cid = state["persona"].get("character")
    if not cid:
        return ""
    try:
        from paperdaemon.pipeline.games import table as RS
        from paperdaemon.pipeline.games import table as TB
        fr = TB.front(state, cid)
        aid = fr["id"] if fr else None
        lines = [l for l in RS.recall(state["doc"], cid, about, k=8, alter=aid)
                 if not l.startswith("We are playing chess")]
        if not lines:
            return ""
        return ("\n%s\nWhat you remember from this notebook (only what you truly remember):\n%s"
                % (RS.about_player(state["doc"], cid, aid), "\n".join("- " + l for l in lines)))
    except Exception:
        return ""


def sync_front(state, rng=None, situations=None):
    """For a character with alters (rm_characters): who is out this turn (rm_table.front_turn, from what
    happened lately when `situations` is None), and the persona that comes with them -- their brief,
    traits and consistency, and their own chess strength unless the request named one. -> the front
    record, or None (no alters)."""
    cid = state["persona"].get("character")
    if not cid:
        return None
    from paperdaemon.pipeline.games import characters as RC
    from paperdaemon.pipeline.games import table as TB
    if not RC.alters(cid):
        return None
    fr = TB.front(state, cid)
    if rng is not None:
        fr = TB.front_turn(state, cid, rng, TB.recent(state, cid) if situations is None else situations, "chess")
    if not fr:
        return None
    p = RC.profile(cid, fr["id"])
    tr = p["personality"]["traits"]
    state["persona"].update(front=fr["id"], shows=fr["shows"],
                            traits={k: float(tr.get(k, d)) for k, d in DEFAULT_TRAITS.items()},
                            consistency=dict(p.get("consistency") or {}))
    if state["strength"].get("by_front"):
        state["strength"]["elo"] = RC.chess_elo(p)
    return fr


def engine_turn(doc, page_no, state, page_id=None, pick=None, engine=None, context=""):
    """The opponent's move. Stockfish lists its candidates; the player's strength decides which of
    them it may play (`pool`: within its tolerance, or anything on a blunder draw); a model playing the
    character picks one of a handful of those through `pick(prompt) -> text`, or the persona picks by
    its traits. Played and set on the page. -> {san, said, mood, how, candidates, blundered}

    A character with alters settles who is out BEFORE the search, since the search is theirs: their
    strength, their consistency, their traits (sync_front)."""
    if state["status"] != "playing":
        return {"ok": False, "reason": "the game is over (%s)" % state["result"]}
    rng = Rng(**state["rng"])
    current=re.search(r'The player just said to you: "(.*)"',context)
    state['cast_input']=current.group(1) if current else ''
    cid = state["persona"].get("character")
    if cid:
        from paperdaemon.pipeline.games import table as TB
        TB.seat(state, [cid])
        TB.next_turn(state)
        sync_front(state, rng)
        from paperdaemon.pipeline.games import cast as rm_cast
        rm_cast.interact(state,state['cast_input'],pick)
        if rm_cast.hook("effective_profile") and not state['strength'].get('named'):
            # a pack can change a character's profile as the game goes on: play this turn at the
            # strength and consistency of the profile as it stands now
            from paperdaemon.pipeline.games import characters as RC
            effective=TB.now(state,cid)
            state['strength']['elo']=RC.chess_elo(effective)
            state['persona']['consistency']=dict(effective['consistency'])
        if state['cast_input']:
            active=rm_cast.prepare(state,cid,rng,())
            rm_cast.challenge_input(state,[active],state['cast_input'],pick)
    own = engine is None
    eng = engine or Engine(state["strength"]["elo"])
    try:
        cands = eng.candidates(state["fen"])
    finally:
        if own:
            eng.close()
    params = strength(state["strength"]["elo"])
    con = state["persona"].get("consistency") or {}
    params["blunder"] = max(params["blunder"], float(con.get("blunder") or 0))
    params["genius"] = float(con.get("genius") or 0)
    moves, drew = pool(cands, params, rng)
    blundered = drew == "blunder"
    stands = situation(cands)
    plan, advise = None, False
    if cid:
        # THE TABLE (rm_table): what this turn does to the character's feelings, whether they speak at
        # all (often not), and which of their tells are rolled to show
        from paperdaemon.pipeline.games import table as TB
        plan = TB.pre_turn(state, cid, situations_before(state, cid, cands), rng, addressed="said to you" in context, interaction='conversation' if state['cast_input'] else 'gameplay')
        advise = plan["speak"] and rng.random() < float(TB.now(state, cid)["voice"].get("advice", 0))
    chosen, said, feel, strong, at, how, truth = None, "", "", 0.6, "", "persona", ""
    presentation = None
    if pick is not None:
        few = handful(moves, rng)
        try:
            reply = pick(llm_prompt(state, few, context + recall_block(state, context), stands, plan=plan, advise=advise))
            chosen, said = parse_llm_pick(reply, few)
            feel, strong, at = parse_feel(reply)
            truth = parse_truth(reply)
            from paperdaemon.pipeline.games import cast as rm_cast
            presentation = rm_cast.parse_face(reply)
            rm_cast.suspicion_from_reply(state,plan,reply)
            how = "model" if chosen else "persona (the model named no listed move)"
        except Exception as ex:
            how = "persona (the model failed: %s)" % type(ex).__name__
    if chosen is None:
        chosen = persona_pick(moves, state["persona"]["traits"], rng, state["strength"]["elo"], limit=False)
    if not feel:
        feel, strong = felt_by_rule(cands, blundered)
    if plan is not None and not plan["speak"]:
        said = ""                                       # the table said silent: a line anyway is dropped
    state["rng"] = rng.state()
    change = apply_move(state, chosen["uci"])
    _finish(doc, page_no, state, change, page_id)
    seen = None
    if plan is not None:
        from paperdaemon.pipeline.games import table as TB
        seen = TB.post_turn(state, cid, plan, feel, strong, at, truth,
                            situations_after(state, cid, chosen, change, blundered), speech=said,presentation=presentation)
        said=seen.get('speech', said)
    return {"ok": True, "san": change["san"], "uci": chosen["uci"], "said": said, "mood": feel,
            "feel": feel, "intensity": strong, "at": at, "stands": stands, "truth": truth, "table": seen,
            "how": how, "change": change, "candidates": [c["san"] for c in cands], "blundered": blundered,
            "advised": advise}


# ------------------------------------------------------------------------------ written moves
def legal_sans(state):
    """Every legal move in the position, in SAN."""
    board = chess.Board(state["fen"])
    return [board.san(m) for m in board.legal_moves]


def parse_text_move(state, text, promote="q"):
    """A move written as SAN or as squares ("Nxc2", "e4", "O-O", "e7e8q") -> uci, or None. Anything
    in words ("knight takes c2") is the model's to translate first -- into one of `legal_sans`."""
    board = chess.Board(state["fen"])
    t = re.sub(r"[!?+#\s]", "", str(text or "")).replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    if not t:
        return None
    for cand in (t, t[:1].upper() + t[1:] if t[:1] in "nbrqk" else t):
        try:
            return board.parse_san(cand).uci()
        except ValueError:
            pass
    try:
        m = chess.Move.from_uci(t.lower())
        if m.promotion is None and board.piece_at(m.from_square) and \
                board.piece_at(m.from_square).piece_type == chess.PAWN and chess.square_rank(m.to_square) in (0, 7):
            m = chess.Move(m.from_square, m.to_square, promotion=chess.Piece.from_symbol(promote.upper()).piece_type)
        return m.uci() if m in board.legal_moves else None
    except ValueError:
        return None


def play_user_uci(doc, page_no, state, uci, page_id=None):
    """A move the player WROTE rather than dragged: played, and its piece set on its square by the
    host (with any capture moved to the captured row). -> {ok, san, change} or {ok: False, reason}"""
    board = chess.Board(state["fen"])
    turn = "w" if board.turn == chess.WHITE else "b"
    if turn != state["colors"]["user"]:
        return {"ok": False, "reason": "it is your opponent's turn; wait for its move"}
    try:
        change = apply_move(state, uci)
    except ValueError:
        return {"ok": False, "reason": "that move is not legal here"}
    _finish(doc, page_no, state, change, page_id)
    return {"ok": True, "uci": uci, "san": change["san"], "change": change}
