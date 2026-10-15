"""The rules of chess: the board, FEN, legal moves (castling, en passant, promotion, check), SAN, the end of
a game (mate, stalemate, the fifty- and seventy-five-move rules, threefold and fivefold repetition,
insufficient material) and PGN.

Squares are numbered a1 = 0, b1 = 1, ... h8 = 63. White is True and Black is False. A move is
(from square, to square, promotion piece type or None); castling is the king's two-square move.
"""
import enum
from typing import NamedTuple, Optional

WHITE, BLACK = True, False
COLORS = (WHITE, BLACK)
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = range(1, 7)
PIECE_TYPES = (PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING)
PIECE_SYMBOLS = (None, "p", "n", "b", "r", "q", "k")
FILE_NAMES = "abcdefgh"
RANK_NAMES = "12345678"
SQUARES = range(64)
SQUARE_NAMES = tuple(f + r for r in RANK_NAMES for f in FILE_NAMES)
STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
STARTING_BOARD_FEN = STARTING_FEN.split()[0]
A1, H1, A8, H8 = 0, 7, 56, 63
_CORNERS = (A1, H1, A8, H8)


def square(file_index, rank_index):
    return rank_index * 8 + file_index


def square_file(sq):
    return sq & 7


def square_rank(sq):
    return sq >> 3


def square_name(sq):
    return SQUARE_NAMES[sq]


def parse_square(name):
    """'e4' -> 28. Raises ValueError for anything else."""
    try:
        return SQUARE_NAMES.index(name)
    except ValueError:
        raise ValueError("not a square: %r" % (name,)) from None


def square_distance(a, b):
    """The number of king steps from a to b."""
    return max(abs(square_file(a) - square_file(b)), abs(square_rank(a) - square_rank(b)))


def piece_symbol(piece_type):
    return PIECE_SYMBOLS[piece_type]


class Piece(NamedTuple):
    piece_type: int
    color: bool

    def symbol(self):
        """'P' for a white pawn, 'n' for a black knight."""
        s = PIECE_SYMBOLS[self.piece_type]
        return s.upper() if self.color else s

    @classmethod
    def from_symbol(cls, symbol):
        return _PIECES[(PIECE_SYMBOLS.index(symbol.lower()), symbol.isupper())]

    def __str__(self):
        return self.symbol()


_PIECES = {(t, c): Piece(t, c) for t in PIECE_TYPES for c in COLORS}


class Move(NamedTuple):
    from_square: int
    to_square: int
    promotion: Optional[int] = None

    def uci(self):
        return SQUARE_NAMES[self.from_square] + SQUARE_NAMES[self.to_square] + \
            (PIECE_SYMBOLS[self.promotion] if self.promotion else "")

    @classmethod
    def from_uci(cls, text):
        """'e2e4', 'e7e8q' -> a Move. Raises ValueError for anything else."""
        if len(text) not in (4, 5):
            raise ValueError("not a move in UCI notation: %r" % (text,))
        promotion = None
        if len(text) == 5:
            if text[4] not in "nbrqk":
                raise ValueError("not a move in UCI notation: %r" % (text,))
            promotion = PIECE_SYMBOLS.index(text[4])
        frm, to = parse_square(text[:2]), parse_square(text[2:4])
        if frm == to:
            raise ValueError("not a move in UCI notation: %r" % (text,))
        return cls(frm, to, promotion)

    def __str__(self):
        return self.uci()


class Termination(enum.Enum):
    CHECKMATE = 1
    STALEMATE = 2
    INSUFFICIENT_MATERIAL = 3
    SEVENTYFIVE_MOVES = 4
    FIVEFOLD_REPETITION = 5
    FIFTY_MOVES = 6
    THREEFOLD_REPETITION = 7


class Outcome(NamedTuple):
    termination: Termination
    winner: Optional[bool]

    def result(self):
        return "1/2-1/2" if self.winner is None else ("1-0" if self.winner else "0-1")


# ---------------------------------------------------------------- geometry, computed once

def _walk(sq, df, dr):
    out, f, r = [], square_file(sq) + df, square_rank(sq) + dr
    while 0 <= f < 8 and 0 <= r < 8:
        out.append(square(f, r))
        f, r = f + df, r + dr
    return tuple(out)


_ROOK_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_BISHOP_DIRS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
# RAYS[sq] = eight rays; the first four are a rook's, the last four a bishop's
RAYS = tuple(tuple(_walk(sq, df, dr) for df, dr in _ROOK_DIRS + _BISHOP_DIRS) for sq in SQUARES)


def _steps(sq, deltas):
    f, r = square_file(sq), square_rank(sq)
    return tuple(square(f + df, r + dr) for df, dr in deltas if 0 <= f + df < 8 and 0 <= r + dr < 8)


KNIGHT_TO = tuple(_steps(sq, ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)))
                  for sq in SQUARES)
KING_TO = tuple(_steps(sq, ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)))
                for sq in SQUARES)
# PAWN_ATTACKS[color][sq]: the squares a pawn of that color standing on sq attacks
PAWN_ATTACKS = {WHITE: tuple(_steps(sq, ((-1, 1), (1, 1))) for sq in SQUARES),
                BLACK: tuple(_steps(sq, ((-1, -1), (1, -1))) for sq in SQUARES)}
_BETWEEN = {}
for _a in SQUARES:
    for _ray in RAYS[_a]:
        for _i, _b in enumerate(_ray):
            _BETWEEN[(_a, _b)] = frozenset(_ray[:_i])
_LIGHT = frozenset(sq for sq in SQUARES if (square_file(sq) + square_rank(sq)) % 2 == 1)


def _slides(piece_type, ray_index):
    """Whether a piece of this type moves along the ray with this index."""
    return piece_type == QUEEN or piece_type == (ROOK if ray_index < 4 else BISHOP)


class LegalMoves(object):
    """The legal moves of a position, as a view: iterate it, ask `move in`, count it."""

    def __init__(self, board):
        self.board = board

    def __iter__(self):
        return iter(self.board.generate_legal_moves())

    def __contains__(self, move):
        return self.board.is_legal(move)

    def __len__(self):
        return len(self.board.generate_legal_moves())

    def __bool__(self):
        return bool(self.board.generate_legal_moves())

    def count(self):
        return len(self)


# ---------------------------------------------------------------- the board

class Board(object):
    """A position and the moves that led to it (`move_stack`), which repetition and PGN need."""

    def __init__(self, fen=STARTING_FEN):
        self.move_stack = []
        self._stack = []
        self.set_fen(fen)

    # -- reading and writing positions

    def set_fen(self, fen):
        parts = fen.split()
        if not 1 <= len(parts) <= 6:
            raise ValueError("not a FEN: %r" % (fen,))
        parts += ["w", "-", "-", "0", "1"][len(parts) - 1:]
        placement, turn, castling, ep, half, full = parts
        squares = [None] * 64
        rows = placement.split("/")
        if len(rows) != 8:
            raise ValueError("a FEN board needs 8 ranks: %r" % (fen,))
        for i, row in enumerate(rows):
            rank, f = 7 - i, 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                elif ch.lower() in "pnbrqk":
                    if f > 7:
                        raise ValueError("a FEN rank is too long: %r" % (row,))
                    squares[square(f, rank)] = Piece.from_symbol(ch)
                    f += 1
                else:
                    raise ValueError("not a FEN piece: %r" % (ch,))
            if f != 8:
                raise ValueError("a FEN rank must cover 8 files: %r" % (row,))
        if turn not in ("w", "b"):
            raise ValueError("a FEN turn is w or b: %r" % (turn,))
        rights = set()
        if castling != "-":
            for ch in castling:
                if ch not in "KQkq":
                    raise ValueError("not a castling right: %r" % (ch,))
                rights.add({"K": H1, "Q": A1, "k": H8, "q": A8}[ch])
        self.ep_square = None if ep == "-" else parse_square(ep)
        try:
            self.halfmove_clock, self.fullmove_number = int(half), int(full)
        except ValueError:
            raise ValueError("FEN move counters must be numbers: %r" % (fen,)) from None
        self._squares = squares
        self.turn = turn == "w"
        self.castling_rights = frozenset(rights)
        self.move_stack.clear()
        self._stack.clear()

    def board_fen(self):
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                p = self._squares[square(f, rank)]
                if p is None:
                    empty += 1
                    continue
                if empty:
                    row, empty = row + str(empty), 0
                row += p.symbol()
            rows.append(row + (str(empty) if empty else ""))
        return "/".join(rows)

    def castling_xfen(self):
        rights = self.clean_castling_rights()
        out = "".join(ch for ch, sq in (("K", H1), ("Q", A1), ("k", H8), ("q", A8)) if sq in rights)
        return out or "-"

    def fen(self):
        """The position in FEN. The en passant square is given only when an en passant capture is legal."""
        ep = SQUARE_NAMES[self.ep_square] if self.has_legal_en_passant() else "-"
        return "%s %s %s %s %d %d" % (self.board_fen(), "w" if self.turn else "b", self.castling_xfen(), ep,
                                      self.halfmove_clock, self.fullmove_number)

    def copy(self, stack=True):
        b = Board.__new__(Board)
        b._squares = list(self._squares)
        b.turn, b.ep_square = self.turn, self.ep_square
        b.castling_rights = self.castling_rights
        b.halfmove_clock, b.fullmove_number = self.halfmove_clock, self.fullmove_number
        b.move_stack = list(self.move_stack) if stack else []
        b._stack = list(self._stack) if stack else []
        return b

    def root(self):
        """The position the move stack starts from."""
        b = self.copy()
        while b.move_stack:
            b.pop()
        return b

    def __eq__(self, other):
        return isinstance(other, Board) and self._key() == other._key() and \
            self.halfmove_clock == other.halfmove_clock and self.fullmove_number == other.fullmove_number

    def __repr__(self):
        return "Board(%r)" % self.fen()

    # -- what is where

    def piece_at(self, sq):
        return self._squares[sq]

    def piece_type_at(self, sq):
        p = self._squares[sq]
        return p.piece_type if p else None

    def piece_map(self):
        return {sq: p for sq, p in enumerate(self._squares) if p is not None}

    def king(self, color):
        k = _PIECES[(KING, color)]
        for sq, p in enumerate(self._squares):
            if p is k:
                return sq
        return None

    def clean_castling_rights(self):
        """The castling rights that still mean something: the rook on its corner, the king on its square."""
        sq = self._squares
        out = set()
        for corner in self.castling_rights:
            color = corner < 8
            if sq[corner] == _PIECES[(ROOK, color)] and sq[4 if color else 60] == _PIECES[(KING, color)]:
                out.add(corner)
        return out

    def is_attacked_by(self, color, sq, empty=None):
        """Whether a piece of `color` attacks sq; the square `empty`, if given, counts as empty."""
        s = self._squares
        knight, king = _PIECES[(KNIGHT, color)], _PIECES[(KING, color)]
        for t in KNIGHT_TO[sq]:
            if s[t] is knight:
                return True
        for t in KING_TO[sq]:
            if s[t] is king:
                return True
        pawn = _PIECES[(PAWN, color)]
        for t in PAWN_ATTACKS[not color][sq]:
            if s[t] is pawn:
                return True
        for i, ray in enumerate(RAYS[sq]):
            for t in ray:
                p = s[t]
                if p is None or t == empty:
                    continue
                if p.color == color and _slides(p.piece_type, i):
                    return True
                break
        return False

    def attackers(self, color, sq):
        """The squares of the pieces of `color` that attack sq."""
        s, out = self._squares, []
        for t in KNIGHT_TO[sq]:
            if s[t] == _PIECES[(KNIGHT, color)]:
                out.append(t)
        for t in KING_TO[sq]:
            if s[t] == _PIECES[(KING, color)]:
                out.append(t)
        for t in PAWN_ATTACKS[not color][sq]:
            if s[t] == _PIECES[(PAWN, color)]:
                out.append(t)
        for i, ray in enumerate(RAYS[sq]):
            for t in ray:
                p = s[t]
                if p is None:
                    continue
                if p.color == color and _slides(p.piece_type, i):
                    out.append(t)
                break
        return out

    def is_check(self):
        k = self.king(self.turn)
        return k is not None and self.is_attacked_by(not self.turn, k)

    # -- moves

    def _pins(self, k):
        """{square of a pinned piece of the side to move: the squares it may still move to}."""
        s, us, pins = self._squares, self.turn, {}
        for i, ray in enumerate(RAYS[k]):
            own = None
            for j, t in enumerate(ray):
                p = s[t]
                if p is None:
                    continue
                if p.color == us:
                    if own is not None:
                        break
                    own = t
                    continue
                if own is not None and _slides(p.piece_type, i):
                    pins[own] = frozenset(ray[:j + 1])
                break
        return pins

    def _targets(self, sq, p):
        """The squares a non-pawn piece on sq can move to (empty or the other side's)."""
        s, out = self._squares, []
        if p.piece_type == KNIGHT or p.piece_type == KING:
            for t in (KNIGHT_TO if p.piece_type == KNIGHT else KING_TO)[sq]:
                q = s[t]
                if q is None or q.color != p.color:
                    out.append(t)
            return out
        for i, ray in enumerate(RAYS[sq]):
            if not _slides(p.piece_type, i):
                continue
            for t in ray:
                q = s[t]
                if q is None:
                    out.append(t)
                    continue
                if q.color != p.color:
                    out.append(t)
                break
        return out

    def _pawn_moves(self, sq, color):
        """(to square, is it an en passant capture) for a pawn on sq, rules of check aside."""
        s, out = self._squares, []
        step = 8 if color else -8
        one = sq + step
        if 0 <= one < 64 and s[one] is None:
            out.append((one, False))
            if square_rank(sq) == (1 if color else 6) and s[one + step] is None:
                out.append((one + step, False))
        for t in PAWN_ATTACKS[color][sq]:
            q = s[t]
            if q is not None and q.color != color:
                out.append((t, False))
            elif q is None and t == self.ep_square and square_rank(t) == (5 if color else 2):
                out.append((t, True))
        return out

    def _expand(self, frm, to, out):
        if square_rank(to) in (0, 7) and self._squares[frm].piece_type == PAWN:
            for pt in (QUEEN, ROOK, BISHOP, KNIGHT):
                out.append(Move(frm, to, pt))
        else:
            out.append(Move(frm, to))

    def _castling_moves(self, out):
        us, s = self.turn, self._squares
        k = 4 if us else 60
        rights = self.clean_castling_rights()
        if not rights or s[k] != _PIECES[(KING, us)] or self.is_attacked_by(not us, k):
            return
        for rook, path, safe, to in ((k + 3, (k + 1, k + 2), (k + 1, k + 2), k + 2),
                                     (k - 4, (k - 1, k - 2, k - 3), (k - 1, k - 2), k - 2)):
            if rook in rights and all(s[t] is None for t in path) and \
                    not any(self.is_attacked_by(not us, t) for t in safe):
                out.append(Move(k, to))

    def generate_legal_moves(self):
        """Every legal move of the side to move, as a list."""
        us, s = self.turn, self._squares
        k = self.king(us)
        out = []
        if k is None:
            return self.generate_pseudo_legal_moves()
        checkers = self.attackers(not us, k)
        # the king's own steps: never onto an attacked square, the king itself not shielding a slider
        for t in self._targets(k, s[k]):
            if not self.is_attacked_by(not us, t, empty=k):
                out.append(Move(k, t))
        if len(checkers) > 1:
            return out
        block = None
        if checkers:
            c = checkers[0]
            block = {c} | _BETWEEN.get((k, c), frozenset())
        else:
            self._castling_moves(out)
        pins = self._pins(k)
        for sq, p in enumerate(s):
            if p is None or p.color != us or p.piece_type == KING:
                continue
            allowed = pins.get(sq)
            if p.piece_type == PAWN:
                for t, ep in self._pawn_moves(sq, us):
                    if ep:
                        if self._ep_is_legal(sq, t, k):
                            out.append(Move(sq, t))
                        continue
                    if (block is None or t in block) and (allowed is None or t in allowed):
                        self._expand(sq, t, out)
                continue
            for t in self._targets(sq, p):
                if (block is None or t in block) and (allowed is None or t in allowed):
                    out.append(Move(sq, t))
        return out

    def _ep_is_legal(self, frm, to, k):
        """An en passant capture takes two pawns off one rank at once, so it is tried on the board."""
        s, us = self._squares, self.turn
        victim = to - 8 if us else to + 8
        saved = s[frm], s[to], s[victim]
        s[to], s[frm], s[victim] = s[frm], None, None
        try:
            return not self.is_attacked_by(not us, k)
        finally:
            s[frm], s[to], s[victim] = saved

    def generate_pseudo_legal_moves(self):
        """Every move by the pieces' movement, whether it leaves the king in check or not."""
        us, s, out = self.turn, self._squares, []
        for sq, p in enumerate(s):
            if p is None or p.color != us:
                continue
            if p.piece_type == PAWN:
                for t, _ep in self._pawn_moves(sq, us):
                    self._expand(sq, t, out)
            else:
                for t in self._targets(sq, p):
                    out.append(Move(sq, t))
        self._castling_moves(out)
        return out

    @property
    def legal_moves(self):
        return LegalMoves(self)

    def is_legal(self, move):
        return move in self.generate_legal_moves()

    def is_pseudo_legal(self, move):
        return move in self.generate_pseudo_legal_moves()

    def is_en_passant(self, move):
        p = self._squares[move.from_square]
        return (p is not None and p.piece_type == PAWN and move.to_square == self.ep_square
                and self._squares[move.to_square] is None
                and abs(move.to_square - move.from_square) in (7, 9))

    def is_capture(self, move):
        q = self._squares[move.to_square]
        return (q is not None and q.color != self.turn) or self.is_en_passant(move)

    def is_castling(self, move):
        p = self._squares[move.from_square]
        return p is not None and p.piece_type == KING and \
            abs(square_file(move.from_square) - square_file(move.to_square)) > 1

    def is_zeroing(self, move):
        p = self._squares[move.from_square]
        return (p is not None and p.piece_type == PAWN) or self.is_capture(move)

    def gives_check(self, move):
        self.push(move)
        try:
            return self.is_check()
        finally:
            self.pop()

    def push(self, move):
        """Play a move (its legality is the caller's to check)."""
        s = self._squares
        p = s[move.from_square]
        self._stack.append((s[move.to_square], self.castling_rights, self.ep_square, self.halfmove_clock,
                            self.fullmove_number, None))
        ep_victim = None
        if self.is_en_passant(move):
            ep_victim = move.to_square - 8 if self.turn else move.to_square + 8
            self._stack[-1] = self._stack[-1][:5] + ((ep_victim, s[ep_victim]),)
            s[ep_victim] = None
        zeroing = p is not None and p.piece_type == PAWN or s[move.to_square] is not None or ep_victim is not None
        s[move.to_square] = _PIECES[(move.promotion, p.color)] if move.promotion and p else p
        s[move.from_square] = None
        if self.is_castling_shape(p, move):
            rf, rt = (move.to_square + 1, move.to_square - 1) if move.to_square > move.from_square \
                else (move.to_square - 2, move.to_square + 1)
            s[rt], s[rf] = s[rf], None
        rights = self.castling_rights - {move.from_square, move.to_square}
        if p is not None and p.piece_type == KING:
            rights -= {A1, H1} if p.color else {A8, H8}
        self.castling_rights = rights
        self.ep_square = None
        if p is not None and p.piece_type == PAWN and abs(move.to_square - move.from_square) == 16:
            self.ep_square = (move.from_square + move.to_square) // 2
        self.halfmove_clock = 0 if zeroing else self.halfmove_clock + 1
        if not self.turn:
            self.fullmove_number += 1
        self.turn = not self.turn
        self.move_stack.append(move)

    @staticmethod
    def is_castling_shape(p, move):
        return p is not None and p.piece_type == KING and \
            abs(square_file(move.from_square) - square_file(move.to_square)) > 1

    def pop(self):
        """Take back the last move -> that move."""
        move = self.move_stack.pop()
        captured, rights, ep, half, full, ep_victim = self._stack.pop()
        s = self._squares
        self.turn = not self.turn
        p = s[move.to_square]
        if move.promotion:
            p = _PIECES[(PAWN, p.color)]
        s[move.from_square] = p
        s[move.to_square] = captured
        if ep_victim is not None:
            s[ep_victim[0]] = ep_victim[1]
        if self.is_castling_shape(p, move):
            rf, rt = (move.to_square + 1, move.to_square - 1) if move.to_square > move.from_square \
                else (move.to_square - 2, move.to_square + 1)
            s[rf], s[rt] = s[rt], None
        self.castling_rights, self.ep_square = rights, ep
        self.halfmove_clock, self.fullmove_number = half, full
        return move

    def peek(self):
        return self.move_stack[-1]

    # -- SAN

    def san(self, move):
        """The move in standard algebraic notation, with + or # (the move must be legal)."""
        san = self._san_body(move)
        self.push(move)
        try:
            if self.is_check():
                san += "#" if not self.generate_legal_moves() else "+"
        finally:
            self.pop()
        return san

    def _san_body(self, move):
        if self.is_castling(move):
            return "O-O" if square_file(move.to_square) > square_file(move.from_square) else "O-O-O"
        p = self._squares[move.from_square]
        to = SQUARE_NAMES[move.to_square]
        capture = self.is_capture(move)
        if p.piece_type == PAWN:
            san = (FILE_NAMES[square_file(move.from_square)] + "x" if capture else "") + to
        else:
            san = PIECE_SYMBOLS[p.piece_type].upper()
            others = {m.from_square for m in self.generate_legal_moves()
                      if m.to_square == move.to_square and m.from_square != move.from_square
                      and self._squares[m.from_square].piece_type == p.piece_type}
            if others:
                same_rank = any(square_rank(o) == square_rank(move.from_square) for o in others)
                same_file = any(square_file(o) == square_file(move.from_square) for o in others)
                if same_rank or not same_file:
                    san += FILE_NAMES[square_file(move.from_square)]
                if same_file:
                    san += RANK_NAMES[square_rank(move.from_square)]
            san += ("x" if capture else "") + to
        if move.promotion:
            san += "=" + PIECE_SYMBOLS[move.promotion].upper()
        return san

    def parse_san(self, text):
        """SAN ('Nf3', 'exd5', 'O-O', 'e8=Q+') -> the legal move it names. Raises ValueError when it names
        no legal move or more than one."""
        t = text.strip()
        legal = self.generate_legal_moves()
        if t.rstrip("+#") in ("O-O", "O-O-O", "0-0", "0-0-0"):
            long_side = t.rstrip("+#") in ("O-O-O", "0-0-0")
            for m in legal:
                if self.is_castling(m) and (square_file(m.to_square) < 4) == long_side:
                    return m
            raise ValueError("illegal san: %r in %s" % (text, self.fen()))
        import re
        m = re.match(r"^([NBKRQ])?([a-h])?([1-8])?[\-x]?([a-h][1-8])(=?[nbrqkNBRQK])?[\+#]?\Z", t)
        if not m:
            raise ValueError("invalid san: %r" % (text,))
        to = parse_square(m.group(4))
        promotion = PIECE_SYMBOLS.index(m.group(5)[-1].lower()) if m.group(5) else None
        if not m.group(1) and m.group(2) and m.group(3):
            # both coordinates of the moving piece ('g1f3'): whatever piece stands there
            frm = parse_square(m.group(2) + m.group(3))
            for mv in legal:
                if mv.from_square == frm and mv.to_square == to and mv.promotion == promotion:
                    return mv
            raise ValueError("illegal san: %r in %s" % (text, self.fen()))
        piece = PIECE_SYMBOLS.index(m.group(1).lower()) if m.group(1) else PAWN
        found = []
        for mv in legal:
            if mv.to_square != to or self._squares[mv.from_square].piece_type != piece:
                continue
            if piece == PAWN and not m.group(2) and square_file(mv.from_square) != square_file(to):
                continue        # a pawn capture names its file
            if m.group(2) and square_file(mv.from_square) != FILE_NAMES.index(m.group(2)):
                continue
            if m.group(3) and square_rank(mv.from_square) != RANK_NAMES.index(m.group(3)):
                continue
            if mv.promotion != promotion:
                continue
            found.append(mv)
        if len(found) != 1:
            raise ValueError("%s san: %r in %s" % ("ambiguous" if found else "illegal", text, self.fen()))
        return found[0]

    def push_san(self, text):
        move = self.parse_san(text)
        self.push(move)
        return move

    # -- the end of a game

    def is_checkmate(self):
        return self.is_check() and not self.generate_legal_moves()

    def is_stalemate(self):
        return not self.is_check() and not self.generate_legal_moves()

    def has_insufficient_material(self, color):
        mine = [p.piece_type for p in self._squares if p is not None and p.color == color]
        if any(t in (PAWN, ROOK, QUEEN) for t in mine):
            return False
        theirs = [p.piece_type for p in self._squares if p is not None and p.color != color]
        if KNIGHT in mine:
            return len(mine) <= 2 and all(t in (KING, QUEEN) for t in theirs)
        if BISHOP in mine:
            bishops = [sq for sq, p in enumerate(self._squares) if p is not None and p.piece_type == BISHOP]
            same_color = all(sq in _LIGHT for sq in bishops) or not any(sq in _LIGHT for sq in bishops)
            return same_color and not any(p is not None and p.piece_type in (PAWN, KNIGHT) for p in self._squares)
        return True

    def is_insufficient_material(self):
        return all(self.has_insufficient_material(c) for c in COLORS)

    def has_legal_en_passant(self):
        if self.ep_square is None:
            return False
        k = self.king(self.turn)
        pawn = _PIECES[(PAWN, self.turn)]
        for frm in PAWN_ATTACKS[not self.turn][self.ep_square]:
            if self._squares[frm] is pawn and self._squares[self.ep_square] is None and \
                    square_rank(self.ep_square) == (5 if self.turn else 2):
                if k is None or self._ep_is_legal(frm, self.ep_square, k):
                    return True
        return False

    def _key(self):
        return (tuple(self._squares), self.turn, frozenset(self.clean_castling_rights()),
                self.ep_square if self.has_legal_en_passant() else None)

    def _reduces_castling_rights(self, move):
        rights = self.clean_castling_rights()
        if move.from_square in rights or move.to_square in rights:
            return True
        p = self._squares[move.from_square]
        if p is not None and p.piece_type == KING:
            return bool(rights & ({A1, H1} if p.color else {A8, H8}))
        return False

    def is_irreversible(self, move):
        return self.is_zeroing(move) or self._reduces_castling_rights(move) or self.has_legal_en_passant()

    def is_repetition(self, count=3):
        """Whether this position has occurred `count` times, counting this one."""
        key, popped = self._key(), []
        try:
            while True:
                if count <= 1:
                    return True
                if len(self.move_stack) < count - 1:
                    return False
                move = self.pop()
                popped.append(move)
                if self.is_irreversible(move):
                    return False
                if self._key() == key:
                    count -= 1
        finally:
            while popped:
                self.push(popped.pop())

    def is_fivefold_repetition(self):
        return self.is_repetition(5)

    def _is_halfmoves(self, n):
        return self.halfmove_clock >= n and bool(self.generate_legal_moves())

    def is_seventyfive_moves(self):
        return self._is_halfmoves(150)

    def is_fifty_moves(self):
        return self._is_halfmoves(100)

    def can_claim_fifty_moves(self):
        if self.is_fifty_moves():
            return True
        if self.halfmove_clock >= 99:
            for move in self.generate_legal_moves():
                if not self.is_zeroing(move):
                    self.push(move)
                    try:
                        if self.is_fifty_moves():
                            return True
                    finally:
                        self.pop()
        return False

    def can_claim_threefold_repetition(self):
        key = self._key()
        seen = {key: 1}
        popped = []
        while self.move_stack:
            move = self.pop()
            popped.append(move)
            if self.is_irreversible(move):
                break
            k = self._key()
            seen[k] = seen.get(k, 0) + 1
        while popped:
            self.push(popped.pop())
        if seen[key] >= 3:
            return True
        for move in self.generate_legal_moves():
            self.push(move)
            try:
                if seen.get(self._key(), 0) >= 2:
                    return True
            finally:
                self.pop()
        return False

    def can_claim_draw(self):
        return self.can_claim_fifty_moves() or self.can_claim_threefold_repetition()

    def outcome(self, claim_draw=False):
        """How the game has ended, or None while it goes on. With claim_draw, a draw either side may claim
        (fifty moves, threefold repetition) ends it too."""
        if self.is_checkmate():
            return Outcome(Termination.CHECKMATE, not self.turn)
        if self.is_insufficient_material():
            return Outcome(Termination.INSUFFICIENT_MATERIAL, None)
        if not self.generate_legal_moves():
            return Outcome(Termination.STALEMATE, None)
        if self.is_seventyfive_moves():
            return Outcome(Termination.SEVENTYFIVE_MOVES, None)
        if self.is_fivefold_repetition():
            return Outcome(Termination.FIVEFOLD_REPETITION, None)
        if claim_draw:
            if self.can_claim_fifty_moves():
                return Outcome(Termination.FIFTY_MOVES, None)
            if self.can_claim_threefold_repetition():
                return Outcome(Termination.THREEFOLD_REPETITION, None)
        return None

    def is_game_over(self, claim_draw=False):
        return self.outcome(claim_draw=claim_draw) is not None

    def result(self, claim_draw=False):
        oc = self.outcome(claim_draw=claim_draw)
        return oc.result() if oc else "*"


def perft(board, depth):
    """The number of move sequences of this length from the position: the standard test of a move generator."""
    moves = board.generate_legal_moves()
    if depth <= 1:
        return len(moves) if depth == 1 else 1
    n = 0
    for m in moves:
        board.push(m)
        n += perft(board, depth - 1)
        board.pop()
    return n


ROSTER = ("Event", "Site", "Date", "Round", "White", "Black", "Result")


def pgn(board, headers=None):
    """The game that led to `board`, from the start of its move stack, as PGN: the seven roster tags (with
    any `headers` given), FEN and SetUp for a game that did not start from the opening position, and the
    moves on one line ending in the result."""
    start = board.root()
    tags = {"Event": "?", "Site": "?", "Date": "????.??.??", "Round": "?", "White": "?", "Black": "?",
            "Result": board.result()}
    extra = {}
    if start.fen() != STARTING_FEN:
        extra = {"FEN": start.fen(), "SetUp": "1"}
    for k, v in (headers or {}).items():
        (tags if k in ROSTER else extra)[k] = v
    lines = ['[%s "%s"]' % (k, tags[k]) for k in ROSTER] + ['[%s "%s"]' % (k, v) for k, v in extra.items()]
    tokens, first = [], True
    for move in board.move_stack:
        if start.turn:
            tokens.append("%d." % start.fullmove_number)
        elif first:
            tokens.append("%d..." % start.fullmove_number)
        tokens.append(start.san(move))
        start.push(move)
        first = False
    tokens.append(tags["Result"])
    return "\n".join(lines + ["", " ".join(tokens)])
