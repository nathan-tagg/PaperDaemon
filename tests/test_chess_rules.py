"""PaperDaemon's own chess rules, proved two ways:

- perft: the number of move sequences of each length from the well-known test positions, against the
  published counts (a move generator that miscounts here is wrong somewhere);
- random games played move by move beside python-chess (a test-only dependency, never shipped): the same
  legal moves, the same SAN for every one of them, the same FEN after each move, the same end of the
  game by every rule, and the same PGN.
"""
import random

import pytest

from paperdaemon.pipeline.games.chess import rules as R

PERFT = [
    ("start", R.STARTING_FEN, [20, 400, 8902, 197281]),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862, 4085603]),
    ("position 3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812, 43238, 674624]),
    ("position 4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467, 422333]),
    ("position 4, mirrored", "r2q1rk1/pP1p2pp/Q4n2/bbp1p3/Np6/1B3NBn/pPPP1PPP/R3K2R b KQ - 0 1",
     [6, 264, 9467, 422333]),
    ("position 5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379, 2103487]),
    ("position 6", "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
     [46, 2079, 89890, 3894594]),
]


@pytest.mark.parametrize("name,fen,counts", PERFT, ids=[p[0] for p in PERFT])
def test_perft_matches_the_published_counts(name, fen, counts):
    board = R.Board(fen)
    for depth, want in enumerate(counts, 1):
        assert R.perft(board, depth) == want, "%s, depth %d" % (name, depth)
    assert board.fen() == R.Board(fen).fen()          # every move taken back


chess = pytest.importorskip("chess")
import chess.pgn  # noqa: E402

STARTS = [R.STARTING_FEN, PERFT[1][1], PERFT[2][1], PERFT[3][1], PERFT[5][1], PERFT[6][1],
          "8/P6k/8/8/8/8/6Kp/8 w - - 0 1",                       # promotions on both sides
          "4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1",                    # castling with nothing in the way
          "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"]   # en passant on offer


def _same_position(mine, theirs, where):
    assert mine.fen() == theirs.fen(), where
    assert sorted(m.uci() for m in mine.legal_moves) == sorted(m.uci() for m in theirs.legal_moves), where
    assert mine.is_check() == theirs.is_check(), where
    oc, toc = mine.outcome(claim_draw=True), theirs.outcome(claim_draw=True)
    assert (oc.termination.name, oc.winner, oc.result()) if oc else None == \
        ((toc.termination.name, toc.winner, toc.result()) if toc else None), where
    assert (mine.outcome() is None) == (theirs.outcome() is None), where
    assert mine.is_insufficient_material() == theirs.is_insufficient_material(), where
    assert mine.can_claim_threefold_repetition() == theirs.can_claim_threefold_repetition(), where
    assert mine.can_claim_fifty_moves() == theirs.can_claim_fifty_moves(), where


def _play(seed, fen, plies, every_san):
    rng = random.Random(seed)
    mine, theirs = R.Board(fen), chess.Board(fen)
    for ply in range(plies):
        where = "seed %d, ply %d, %s" % (seed, ply, theirs.fen())
        _same_position(mine, theirs, where)
        if theirs.outcome(claim_draw=False) is not None:
            break
        moves = sorted(theirs.legal_moves, key=lambda m: m.uci())
        if every_san:
            for m in moves:
                san = theirs.san(m)
                assert mine.san(R.Move.from_uci(m.uci())) == san, where
                assert mine.parse_san(san).uci() == m.uci(), where
        # quiet moves more often than chance, so the fifty-move rule and repetitions come up
        quiet = [m for m in moves if not theirs.is_zeroing(m)]
        pick = rng.choice(quiet if quiet and rng.random() < 0.7 else moves)
        mine_move = R.Move.from_uci(pick.uci())
        assert mine.san(mine_move) == theirs.san(pick), where
        assert mine.gives_check(mine_move) == theirs.gives_check(pick), where
        assert mine.is_capture(mine_move) == theirs.is_capture(pick), where
        assert mine.is_en_passant(mine_move) == theirs.is_en_passant(pick), where
        assert mine.is_castling(mine_move) == theirs.is_castling(pick), where
        mine.push(mine_move)
        theirs.push(pick)
    game = chess.pgn.Game.from_board(theirs)
    game.headers["Event"] = "Test %d" % seed
    assert R.pgn(mine, {"Event": "Test %d" % seed}) == str(game)
    while theirs.move_stack:                                     # and every move takes back
        assert mine.pop().uci() == theirs.pop().uci()
        assert mine.fen() == theirs.fen()


@pytest.mark.parametrize("start", range(len(STARTS)))
def test_random_games_agree_with_python_chess_move_by_move(start):
    for seed in range(6):
        _play(1000 * start + seed, STARTS[start], plies=260, every_san=seed < 2)


def test_long_quiet_games_reach_the_draw_rules():
    """Kings, rooks and knights shuffling: repetitions and the move-count rules decide these."""
    seen = set()
    for seed in range(20):
        rng = random.Random(seed)
        mine, theirs = R.Board("4k3/2n5/8/3r4/8/8/2N5/R3K3 w - - 0 1"), chess.Board("4k3/2n5/8/3r4/8/8/2N5/R3K3 w - - 0 1")
        for ply in range(400):
            _same_position(mine, theirs, "seed %d ply %d" % (seed, ply))
            oc = theirs.outcome(claim_draw=True)
            if oc is not None:
                seen.add(oc.termination.name)
                break
            quiet = [m for m in theirs.legal_moves if not theirs.is_capture(m)] or list(theirs.legal_moves)
            pick = rng.choice(sorted(quiet, key=lambda m: m.uci()))
            mine.push(R.Move.from_uci(pick.uci()))
            theirs.push(pick)
    assert "THREEFOLD_REPETITION" in seen


def test_san_reads_what_people_write():
    b = R.Board()
    assert b.parse_san("e4").uci() == "e2e4" and b.parse_san("Nf3").uci() == "g1f3"
    assert b.parse_san("g1f3").uci() == "g1f3"
    with pytest.raises(ValueError):
        b.parse_san("e5")
    with pytest.raises(ValueError):
        b.parse_san("Qh5")
    b = R.Board("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    assert b.parse_san("O-O").uci() == "e1g1" and b.parse_san("0-0-0").uci() == "e1c1"
    b = R.Board("8/P6k/8/8/8/8/6K1/8 w - - 0 1")
    assert b.parse_san("a8=Q").uci() == "a7a8q" and b.parse_san("a8N").uci() == "a7a8n"
    with pytest.raises(ValueError):
        b.parse_san("a8")


@pytest.mark.parametrize("fen,moves,end", [
    ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", [], "STALEMATE"),
    ("7k/8/5QK1/8/8/8/8/8 w - - 0 1", ["Qf7"], "STALEMATE"),
    ("6k1/5ppp/8/8/8/8/8/K3R3 w - - 0 1", ["Re8#"], "CHECKMATE"),
    ("8/8/4k3/8/8/2B5/4K3/8 w - - 0 1", [], "INSUFFICIENT_MATERIAL"),
    ("8/8/4k3/8/8/2N5/4K3/8 w - - 0 1", [], "INSUFFICIENT_MATERIAL"),
    ("4k3/8/8/8/8/8/8/1N2K1N1 w - - 0 1", ["Nc3", "Kd8", "Nb1", "Ke8"] * 4, "FIVEFOLD_REPETITION"),
    ("4k3/8/8/8/8/8/8/1N2K1N1 w - - 0 1", ["Nc3", "Kd8", "Nb1", "Ke8"] * 2, "THREEFOLD_REPETITION"),
])
def test_how_games_end_agrees_with_python_chess(fen, moves, end):
    mine, theirs = R.Board(fen), chess.Board(fen)
    for san in moves:
        mine.push_san(san)
        theirs.push_san(san)
    _same_position(mine, theirs, fen)
    assert mine.outcome(claim_draw=True).termination.name == end
