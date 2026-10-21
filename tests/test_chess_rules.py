"""PaperDaemon's own chess rules, proved against known answers:

- perft: the number of move sequences of each length from the well-known test positions, against the
  published counts (a move generator that miscounts here is wrong somewhere);
- SAN as people write it, and how games end by every rule, on positions whose outcome is known.
"""
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
    ("4k3/8/8/8/8/8/8/R3K3 w - - 99 60", ["Ra2"], "FIFTY_MOVES"),          # a hundred quiet half-moves
    ("4k3/8/8/8/8/8/8/R3K3 w - - 149 90", ["Ra2"], "SEVENTYFIVE_MOVES"),   # a hundred and fifty
])
def test_how_games_end(fen, moves, end):
    b = R.Board(fen)
    for san in moves:
        b.push_san(san)
    assert b.outcome(claim_draw=True).termination.name == end


def test_the_draws_a_player_must_claim_do_not_end_the_game_alone():
    b = R.Board("4k3/8/8/8/8/8/8/1N2K1N1 w - - 0 1")
    for san in ["Nc3", "Kd8", "Nb1", "Ke8"] * 2:
        b.push_san(san)
    assert b.can_claim_threefold_repetition() and b.outcome() is None
    b = R.Board("4k3/8/8/8/8/8/8/R3K3 w - - 99 60")
    b.push_san("Ra2")
    assert b.can_claim_fifty_moves() and b.outcome() is None
    b = R.Board("4k3/8/8/8/8/8/8/R3K3 w - - 40 60")
    b.push_san("Ra2")
    assert not b.can_claim_fifty_moves() and b.outcome(claim_draw=True) is None
