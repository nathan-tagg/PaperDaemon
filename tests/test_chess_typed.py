"""A chess move TYPED on the game's page: a legal move in chess's notation is played as it is, no model asked; anything
else typed is read by the text model, as handwriting is by the vision model (games.read_typed)."""
from paperdaemon.pipeline import games as G

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _state(fen=START, user="w"):
    return {"fen": fen, "colors": {"user": user, "engine": "b" if user == "w" else "w"}}


def test_a_typed_move_is_played_as_it_is_without_a_model():
    asked = []
    got = G.read_typed(_state(), "  e4 ", lambda p: asked.append(p) or "SAY: no")
    assert got == {"kind": "move", "uci": "e2e4", "raw": "e4"} and asked == []
    assert G.read_typed(_state(), "Nf3", None)["uci"] == "g1f3"


def test_typed_words_are_read_by_the_text_model():
    asked = []

    def model(prompt):
        asked.append(prompt)
        return "SAY: Good luck, Barty"
    got = G.read_typed(_state(), "Good luck, Barty!", model)
    assert got["kind"] == "say" and got["text"] == "Good luck, Barty" and len(asked) == 1
    assert "e4" in asked[0] and "White" in asked[0]          # the model is given the legal moves and the side
    words = G.read_typed(_state(), "knight to f3", lambda p: "MOVE: Nf3")
    assert words["kind"] == "move" and words["uci"] == "g1f3"


def test_nothing_typed_is_nothing_and_a_move_out_of_turn_is_not_played():
    assert G.read_typed(_state(), "   ", None) is None
    black_to_move = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    got = G.read_typed(_state(black_to_move, user="w"), "d4", lambda p: "SAY: d4")
    assert got["kind"] == "say"                               # not their turn: no move is legal for them


def _after(moves):
    from paperdaemon.pipeline.games.chess import rules as chess
    b = chess.Board()
    for m in moves.split():
        b.push_san(m)
    return _state(b.fen())


def test_handwriting_in_notation_is_played_as_copied_not_as_the_reader_chose():
    # after 8...Qb4+ the knight on b5 can also go to c3: a reader asked only to choose answered Nc3 for a written "c3"
    st = _after("e4 e6 d4 d5 Nc3 Nf6 Bg5 h6 Bxf6 Qxf6 e5 Qe7 Qg4 Nd7 Nb5 Qb4+")
    got = G.read_writing(st, b"png", lambda prompt, png: "WROTE: c3\nMOVE: Nc3")
    assert got["kind"] == "move" and got["uci"] == "c2c3" and "WROTE: c3" in got["raw"]
    words = G.read_writing(st, b"png", lambda prompt, png: "WROTE: knight back to c3\nMOVE: Nc3")
    assert words["kind"] == "move" and words["uci"] == "b5c3"          # words are the reader's to translate
    assert G.read_writing(st, b"png", lambda prompt, png: "MOVE: Kd1")["uci"] == "e1d1"     # one line still reads
    say = G.read_writing(st, b"png", lambda prompt, png: "WROTE: good game\nSAY: good game")
    assert say["kind"] == "say" and say["text"] == "good game"
    asked = []
    G.read_writing(st, b"png", lambda prompt, png: asked.append(prompt) or "NOTHING")
    assert "WROTE:" in asked[0] and "Nc3" in asked[0] and "c3" in asked[0]
