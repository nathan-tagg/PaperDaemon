r"""Games on the tablet, from the host's side.

A game is a step like a chart or a picture: the plan names it (`do: game`), and the host starts it
on a page of its own. After that the page is a GAME PAGE -- its state lives in the notebook's
notepad (rm_chess.save_state) -- and every job on it is one turn, played here with no plan:

  1. What the player WROTE, if anything, is read first by the model's eyes (`ask_vision`) and
     turned into one of the legal moves, a resignation, a draw offer or a remark. The model only
     translates; the engine decides what is legal. The writing comes off once it is read.
  2. Otherwise a piece the player DRAGGED is read off the pictures (drop zones, no model).
  3. The opponent answers: the engine lists moves at its strength, the character picks one of a
     handful in its own way (`ask_text`), and says how it feels and one line.
  4. Every piece is tidied onto its square, the talk strip under the board is replaced, and the
     state and history are saved.

The model is never trusted with the position; without a model at all the game still plays (the
character picks by its traits and says nothing), and only written moves wait for one.

    ask_text(prompt) -> reply text               ask_vision(prompt, png_path) -> reply text
"""
import json
import os
import re
import time
import uuid
from paperdaemon import paths

HERE = os.path.dirname(os.path.abspath(__file__))
from paperdaemon.pipeline import TEMPLATES as TPL_DIR
INK, INK_2, PAPER = (20, 20, 20), (90, 90, 90), (255, 255, 255)


def _log(log, msg):
    (log or print)(msg)


def game_on_page(doc, page_id):
    """The game that lives on this page, or None."""
    from paperdaemon.pipeline.games import chess as CH
    try:
        return CH.game_for_page(doc, page_id)
    except Exception:
        return None


# ------------------------------------------------------------------------------ the talk strip
def _font(name, size):
    from paperdaemon import paths
    return paths.pil_font(name, size)


def _wrap(draw, text, font, width):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


NARRATOR_INK = (0x4F, 0x7F, 0x3A)          # the board's green, as in the dialog chart


def talk_png(lines, width, out):
    """The talk strip as a picture: each line is (speaker, mood, text); speaker "narrator" is the
    game's own voice, set apart in italics. A stand-in until the characters' dialog chart draws
    faces and bubbles. -> (path, height in page units)"""
    from PIL import Image, ImageDraw
    name_f, text_f, narr_f = _font("reMarkableSans-Bold.ttf", 34), _font("reMarkableSans-Regular.ttf", 34), \
        _font("reMarkableSans-RegularItalic.ttf", 40)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    rows = []
    for line in lines:                       # (speaker, mood, text[, marks[, look]])
        who, mood, text = line[0], line[1], line[2]
        text = " ".join(str(text or "").split())
        if not text:
            continue
        if who == "narrator":
            for ln in _wrap(probe, text, narr_f, width - 16):
                rows.append(("narr", ln))
        else:
            head = "%s%s:" % (who, (" (%s)" % mood) if mood and mood != "neutral" else "")
            body = _wrap(probe, text, text_f, width - 16 - probe.textlength(head + " ", font=name_f))
            rows.append(("say", head, body[0] if body else ""))
            for ln in body[1:]:
                rows.append(("cont", head, ln))
        rows.append(("gap",))
    rows = rows[:-1] if rows and rows[-1] == ("gap",) else rows
    lh = 50
    h = max(60, sum(16 if r[0] == "gap" else lh for r in rows) + 16)
    im = Image.new("RGB", (int(width), int(h)), PAPER)
    d = ImageDraw.Draw(im)
    y = 8
    for r in rows:
        if r[0] == "gap":
            y += 16
            continue
        if r[0] == "narr":
            d.text((8, y), r[1], fill=NARRATOR_INK, font=narr_f)
        elif r[0] == "say":
            d.text((8, y), r[1], fill=INK, font=name_f)
            d.text((8 + d.textlength(r[1] + " ", font=name_f), y), r[2], fill=INK, font=text_f)
        else:
            d.text((8 + d.textlength(r[1] + " ", font=name_f), y), r[2], fill=INK, font=text_f)
        y += lh
    im.save(out)
    return out, h


def express(state, feel, intensity=0.6, at=""):
    """What a character's FACE shows for what it FEELS -> the emotion to draw. The feeling is its
    true state (the model's call, answering to how the game really stands); the face is what reaches
    it -- its expressiveness, its mask, and the tells that leak through (rm_characters.shown). Both go
    in the game's state, so the notepad keeps the truth the player is meant to read off the faces.
    Drawn with the game's own seed."""
    from paperdaemon.pipeline.games import chess as CH
    feel = feel if feel in CH.EMOTIONS else "neutral"
    shows, why, cue = feel, "felt", ""
    cid = state["persona"].get("character")
    if cid:
        try:
            from paperdaemon.pipeline.games import characters as RC
            if hasattr(RC, "shown"):
                rng = CH.Rng(**state["rng"])
                r = RC.shown(cid, feel, intensity, rng.random) or {}
                state["rng"] = rng.state()
                shows = r.get("shows") if r.get("shows") in CH.EMOTIONS else shows
                why, cue = r.get("why") or why, r.get("cue") or ""
        except Exception:
            pass
    mood = {"feels": feel, "intensity": round(float(intensity), 2), "at": at, "shows": shows,
            "why": why, "cue": cue, "ply": len(state.get("history") or [])}
    state["persona"]["mood"] = mood
    state["moods"] = (state.get("moods") or [])[-59:] + [mood]
    return shows


def _trim(png, pad=14):
    """Cut a picture's empty bottom off (the dialog builder lays out from the top), and its empty left
    edge, so what it shows first -- the opponent's face -- starts where the picture is placed."""
    from PIL import Image, ImageChops
    with Image.open(png) as im:
        im.load()
    flat = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im.convert("RGBA")).convert("RGB")
    box = ImageChops.difference(flat, Image.new("RGB", im.size, "white")).getbbox()
    if box and (box[0] > 0 or box[3] + pad < im.size[1]):
        im.crop((box[0], 0, im.size[0], min(im.size[1], box[3] + pad))).save(png)


def dialog_png(state, lines, out, width=None):
    """The talk as the characters' dialog chart -- the opponent's face in the mood it is in, its
    words in a bubble, the narrator in plain text (rm_characters, rm_tabletop). `width` = the page
    pixels it will sit in: drawn at that size, on a canvas tall enough for the larger faces, and cut
    to what it holds -- a strip drawn at its own 1450 x 380 and shrunk into the top of a game page
    would have a face and words too small to read. -> path, or None when the opponent is not a
    roster character or the chart will not render."""
    cid = state["persona"].get("character")
    if not cid:
        return None
    try:
        from paperdaemon.pipeline.games import characters as RC
        from paperdaemon.pipeline import charts as CHART
        spec_lines = []
        for line in lines:
            who, mood, text = line[0], line[1], line[2]
            marks = [m for m in (line[3] if len(line) > 3 and line[3] else []) if m in RC.MARKS]
            look = line[4] if len(line) > 4 else None            # an alter's face (who they pass as)
            if who == "narrator":
                spec_lines.append(RC.narrate(text))
            elif str(text or "").strip():
                spec_lines.append(RC.say(cid, mood if mood in RC.EMOTIONS else "neutral", text, marks, look))
            else:
                spec_lines.append(RC.emote(cid, mood if mood in RC.EMOTIONS else "neutral", marks, look))   # a face, no words
        spec = RC.dialog(spec_lines, page="strip")
        if width:
            spec["width"], spec["height"] = int(round(width)), 800
        CHART.render(spec, out)
        if not os.path.exists(out):
            return None
        _trim(out)
        return out
    except Exception:
        return None


TALK_READABLE = 0.55        # the least scale a talk strip is drawn at before its earlier speech is quoted


def talk_lines(lines):
    """The lines a talk strip shows: each with words, or a character's face alone (an emote: it shows,
    it says nothing) -- but not a face that says nothing and shows no mark when the same speaker's face
    comes again further down. It adds nothing, and the strip keeps one face row, so the strip, the face
    and the name under it stay large enough to read (two rows at the start of a game -- the greeting's
    face and the reply's -- shrank the whole strip to under half its size)."""
    lines = [l for l in lines if l and (str(l[2] or "").strip() or (l[0] != "narrator" and l[1]))]

    def bare(i, l):
        return (l[0] != "narrator" and not str(l[2] or "").strip() and not (len(l) > 3 and l[3])
                and any(m[0] == l[0] for m in lines[i + 1:]))
    return [l for i, l in enumerate(lines) if not bare(i, l)]


def place_talk(doc, page_no, state, lines, page_id=None, workdir=None):
    """Replace the talk strip at the top of the page with these lines (or remove it when there are
    none)."""
    from paperdaemon.pipeline.games import chess as CH
    from paperdaemon.pipeline.page import images as IM
    from PIL import Image
    old = state.get("talk") or {}
    if old.get("box"):
        try:
            IM.remove_in_box(doc, page_no, tuple(old["box"]), page_id=page_id)
        except Exception:
            pass
    state["talk"] = {}
    lines = talk_lines(lines)
    if not lines:
        return None
    x0, y0, x1, y1 = CH.talk_box(tuple(state["board"]["box"]))
    w = x1 - x0
    path = os.path.join(workdir or os.path.join(paths.state_dir(), "rm-queue"), "_game_talk_%d.png" % int(time.time() * 1000))
    while True:
        png = dialog_png(state, lines, path, width=w)
        if png is None:
            worded = [l for l in lines if str(l[2] or "").strip()]
            if not worded:
                return None
            png, _h = talk_png(worded, w, path)
        # the strip keeps its own proportions, as large as the other side's space allows (never larger
        # than it was drawn), at the top, its left edge -- the opponent's face -- on the board's left edge
        with Image.open(png) as im:
            pw, ph = im.size
        s = min(1.0, w / float(pw), (y1 - y0) / float(ph))
        # READABLE OR SHORTER: a strip that would shrink below TALK_READABLE says its earlier speech as
        # quoted lines -- a line of text instead of a face row -- and is drawn again, so the turn's own
        # face, its name and every word stay large enough to read on the tablet
        earlier = [i for i, l in enumerate(lines) if l[0] != "narrator"][:-1]
        if s >= TALK_READABLE or not earlier:
            break
        i = earlier[0]
        said = str(lines[i][2] or "").strip()
        lines = lines[:i] + ([("narrator", "", '%s: "%s"' % (_short(state), said))] if said else []) + lines[i + 1:]
    bw, bh = pw * s, ph * s
    box = (x0, y0, x0 + bw, y0 + bh)
    try:
        r = IM.insert(doc, page_no, png, box, page_id=page_id)
        IM.record_placement(r["doc"], page_no, r["name"], box, hash=r["hash"], kind="game-talk", game=state["id"])
        state["talk"] = {"hash": r["hash"], "name": r["name"], "box": list(box),
                         "lines": [list(l) for l in lines]}
    finally:
        try:
            os.remove(png)
        except OSError:
            pass
    return state["talk"]


# ------------------------------------------------------------------------------ reading writing
READ_PROMPT = """This is a chess page on a tablet: a board and its pieces, which are pictures, and
possibly something the player WROTE by hand in ink. Read only the handwriting.
The player plays {side}; {turn}.
Their legal moves now: {moves}
What did they write? Answer with exactly ONE line:
MOVE: <one of the legal moves above>   -- a move however it was written ("knight takes c2",
       "Nxc2", "castle", "promote to knight" = the promotion move to that piece)
RESIGN   -- they give up
DRAW   -- they offer a draw
SAY: <their words>   -- something said to the opponent
NOTHING   -- no handwriting, or it cannot be read"""


def read_writing(state, png, ask_vision):
    """What the player wrote -> {"kind": move|resign|draw|say|nothing, "uci"?, "text"?}"""
    from paperdaemon.pipeline.games.chess import rules as chess
    from paperdaemon.pipeline.games import chess as CH
    board = chess.Board(state["fen"])
    user_turn = ("w" if board.turn == chess.WHITE else "b") == state["colors"]["user"]
    sans = CH.legal_sans(state) if user_turn else []
    reply = ask_vision(READ_PROMPT.format(
        side="White" if state["colors"]["user"] == "w" else "Black",
        turn="it is their turn" if user_turn else "it is NOT their turn (the opponent moves next)",
        moves=", ".join(sans) if sans else "(none: not their turn)"), png)
    line = next((l.strip() for l in str(reply or "").splitlines() if l.strip()), "")
    m = re.match(r"(?i)^MOVE:\s*(.+)$", line)
    if m and sans:
        uci = CH.parse_text_move(state, m.group(1).strip())
        if uci:
            return {"kind": "move", "uci": uci, "raw": line}
        return {"kind": "unclear", "raw": line}
    if re.match(r"(?i)^RESIGN\b", line):
        return {"kind": "resign", "raw": line}
    if re.match(r"(?i)^DRAW\b", line):
        return {"kind": "draw", "raw": line}
    m = re.match(r"(?i)^SAY:\s*(.+)$", line)
    if m:
        return {"kind": "say", "text": m.group(1).strip().strip('"'), "raw": line}
    return {"kind": "nothing", "raw": line}


# ------------------------------------------------------------------------------ one turn
def _name(state):
    return (state["persona"].get("name") or "Opponent").strip()


def _short(state):
    cid = state["persona"].get("character")
    if cid:
        try:
            from paperdaemon.pipeline.games import characters as RC
            return RC.get(cid)["short"]
        except Exception:
            pass
    return _name(state)


def _table_lines(state, r, silent_line=""):
    """A turn's talk from what the table decided (rm_table): the face that shows, with any subtle
    marks, and the words if the character spoke; each act a tell showed, in the narrator's plain
    words (nothing says what it means); and, when nobody spoke, what happened."""
    seen = r.get("table")
    if not seen:                                        # not a roster character: no table state
        shows = express(state, r.get("feel") or "neutral", r.get("intensity", 0.6), r.get("at") or "")
        return [(_name(state), shows, r.get("said") or "")] + ([("narrator", "", silent_line)]
                                                                if silent_line and not r.get("said") else [])
    mood = {"feels": seen["feeling"], "intensity": seen["intensity"], "at": seen["at"], "shows": seen["shows"],
            "why": seen["why"], "marks": seen["marks"], "acts": seen["acts"], "ply": len(state.get("history") or [])}
    state["persona"]["mood"] = mood
    state["moods"] = (state.get("moods") or [])[-59:] + [mood]
    # a character with alters: the face is whoever they pass as, and a new one coming forward in the
    # open is something the table sees
    out = [("narrator", "", "%s %s." % (_short(state), seen["arrives"].rstrip(".")))] if seen.get("arrives") else []
    from paperdaemon.pipeline.games import cast as rm_cast
    out += [("narrator", "", line) for line in rm_cast.scene_lines(state)]
    out += [(_name(state), seen["shows"], r.get("said") or "", seen["marks"], seen.get("look"))]
    out += [("narrator", "", "%s %s." % (_short(state), a.rstrip("."))) for a in seen["acts"]]
    if silent_line and not r.get("said"):
        out.append(("narrator", "", silent_line))
    return out


def _remark(state, context, ask_text, log=None):
    """The player spoke on their own turn: the table decides whether the character answers."""
    from paperdaemon.pipeline.games import chess as CH
    cid = state["persona"].get("character")
    if not cid:
        return []
    from paperdaemon.pipeline.games import table as TB
    current=re.search(r'The player just said to you: "(.*)"',context)
    state['cast_input']=current.group(1) if current else context
    TB.next_turn(state)
    rng = CH.Rng(**state["rng"])
    TB.seat(state, [cid])
    from paperdaemon.pipeline.games import cast as rm_cast
    rm_cast.interact(state,state['cast_input'],ask_text)
    active = rm_cast.prepare(state,cid,rng,())
    rm_cast.challenge_input(state,[active],state['cast_input'],ask_text)
    plan = TB.pre_turn(state, cid, set(), rng, addressed=True, interaction='conversation')
    state["rng"] = rng.state()
    said, feel, strong, at, truth = "", "", None, "", ""
    presentation = None
    if plan["speak"] and ask_text is not None:
        try:
            reply = ask_text("You are this character in a chess game: %s\n%s\n%s\n%s\nReply with a line SAY: what "
                             "the character says back, in their own voice, true to the facts above unless they are "
                             "lying on purpose. Then a line FEEL: what it truly feels now -- one of %s -- how strongly, "
                             "1 to 10, and at whom if anyone. Then a line TRUTH: true, lie or bluff (nobody sees it). "
                             "Then FACE: one fitting signature ID from the private menu above, or none. Not a tell."
                             % (state["persona"].get("profile") or state["persona"].get("text") or "a club player",
                                "\n".join(CH.facts(state)), "\n".join(plan["prompt_lines"]),
                                context + CH.recall_block(state, context), ", ".join(CH.EMOTIONS)))
            m = re.search(r"(?im)^\s*SAY:\s*(.+)$", reply or "")
            said = m.group(1).strip().strip('"') if m else ""
            feel, strong, at = CH.parse_feel(reply)
            truth = CH.parse_truth(reply)
            presentation = rm_cast.parse_face(reply)
            rm_cast.suspicion_from_reply(state,plan,reply)
        except Exception as ex:
            _log(log, "  game: the remark's reply failed: %s" % str(ex)[:90])
    seen = TB.post_turn(state, cid, plan, feel or None, strong, at, truth, speech=said,presentation=presentation)
    said=seen.get('speech', said)
    return _table_lines(state, {"table": seen, "said": said})


def _remember_turn(doc, page_id, state, heard, said, ended, log=None):
    """WHAT THE OPPONENT REMEMBERS of this turn, in this notebook (rm_residents): what the player said to
    them, what they said back, and how the game ended. The moves themselves are read live from the game
    (rm_residents._games_with). For one with alters, the memory is whoever was out."""
    cid = state["persona"].get("character")
    if not cid or not (heard or said or ended):
        return
    try:
        from paperdaemon.pipeline.games import table as RS
        from paperdaemon.pipeline.games import table as TB
        fr = TB.front(state, cid)
        aid = fr["id"] if fr else None
        if heard:
            RS.remember(doc, cid, "Across the chess board the player said: \"%s\"" % heard[:300], kind="said",
                        page=page_id, weight=0.5, alter=aid)
        for s in said:
            RS.remember(doc, cid, "Across the chess board I said: \"%s\"" % s[:300], kind="chat", page=page_id,
                        weight=0.3, alter=aid)
        if ended and not state.get("end_remembered"):
            state["end_remembered"] = True
            you = state["colors"]["user"]
            res = state.get("result")
            won = (res == "1-0" and you == "b") or (res == "0-1" and you == "w")
            lost = (res == "1-0" and you == "w") or (res == "0-1" and you == "b")
            RS.remember(doc, cid, "Our chess game ended (%s): %s." % (state["status"].replace("_", " "),
                        "I won" if won else "the player won" if lost else "a draw"), kind="game", page=page_id,
                        weight=0.8, alter=aid)
            if state["strength"].get("adaptive"):
                # their level follows the player's: a win makes them easier, a loss harder
                new = RS.adapt(doc, cid, "chess", state["strength"]["elo"], "won" if won else "lost" if lost else "draw")
                _log(log, "  game: %s's chess level here is now %d" % (cid, new))
    except Exception as ex:
        _log(log, "  game: the opponent's memory was not written: %s" % str(ex)[:90])


def _over_line(state):
    """The narrator's line when the game has ended, else ""."""
    st, res = state["status"], state.get("result")
    if st == "playing":
        return ""
    you = state["colors"]["user"]
    won = (res == "1-0" and you == "w") or (res == "0-1" and you == "b")
    lost = (res == "0-1" and you == "w") or (res == "1-0" and you == "b")
    what = st.replace("_", " ")
    if st == "checkmate":
        return "Checkmate. %s" % ("You win." if won else "%s wins." % _name(state))
    if st == "resigned":
        return "Game over: %s." % ("you win" if won else "you resigned" if lost else "draw")
    return "Game over: %s, a draw." % what if res == "1/2-1/2" else "Game over: %s (%s)." % (what, res)


def play(doc, page_no, page_id, ask_text=None, ask_vision=None, log=None, workdir=None, paint=None):
    """One job on a game page -> (outcome, note), or None when the page holds no game. `paint(prompt,
    mode, src)` -> a PNG path is the host's picture model, for the games that draw (Ink Adventure)."""
    from paperdaemon.pipeline.games.chess import rules as chess
    from paperdaemon.pipeline.games import chess as CH
    from paperdaemon.pipeline import page as ER
    from paperdaemon.pipeline import page as P
    from paperdaemon.pipeline.page import render as R
    state = game_on_page(doc, page_id)
    if state is None:
        return None
    workdir = workdir or os.path.join(paths.state_dir(), "rm-queue")
    if state.get("game") == "adventure":
        from paperdaemon.pipeline.games import adventure as AD
        return AD.turn(doc, page_no, page_id, state, ask_text, ask_vision, paint=paint, log=log, workdir=workdir)
    if state.get("game") == "messages":
        from paperdaemon.pipeline.games import messages as MS
        return MS.turn(doc, page_no, page_id, state, ask_text, ask_vision, paint=paint, log=log, workdir=workdir)
    talk, notes, context = [], [], ""
    try:
        P.record(doc, page_no, note="before a %s turn" % state.get("game", "game"))
    except Exception:
        pass
    # 1. WHAT WAS WRITTEN comes first: it may be the move itself, or say how to promote
    try:
        ink = [L for L in R.strokes(doc, page_no)]
    except Exception:
        ink = []
    written = None
    if ink:
        if ask_vision is None:
            talk.append(("narrator", "", "I cannot read writing right now; move a piece instead."))
        else:
            png = os.path.join(workdir, "_game_read_%d.png" % int(time.time() * 1000))
            try:
                R.render(doc, page_no, png)
                written = read_writing(state, png, ask_vision)
            except Exception as ex:
                _log(log, "  game: reading the writing failed: %s" % str(ex)[:90])
                written = {"kind": "nothing", "raw": ""}
            finally:
                try:
                    os.remove(png)
                except OSError:
                    pass
            _log(log, "  game: the writing reads %r" % (written.get("raw") or "")[:80])
        # ONLY WRITING THAT WAS READ comes off -- a move, a resignation, a draw offer or a remark, which the page
        # now shows in its own way. Writing that could not be read (no vision model, an unclear or empty reading)
        # stays exactly where the player put it.
        if written and written.get("kind") in ("move", "resign", "draw", "say"):
            try:
                ER.erase(doc, page_no, lambda L: True)
            except Exception as ex:
                _log(log, "  game: the writing was NOT erased: %s" % str(ex)[:90])
    user_moved = False
    if written and written["kind"] == "move":
        r = CH.play_user_uci(doc, page_no, state, written["uci"], page_id)
        if r["ok"]:
            user_moved = True
            notes.append("you wrote %s" % r["san"])
        else:
            talk.append(("narrator", "", "Not played: %s." % r["reason"]))
            CH.tidy(doc, page_no, state, page_id)
    elif written and written["kind"] == "resign" and state["status"] == "playing":
        state["status"] = "resigned"
        state["result"] = "0-1" if state["colors"]["user"] == "w" else "1-0"
        notes.append("you resigned")
    else:
        if written and written["kind"] == "say":
            context = "The player just said to you: \"%s\"" % written["text"][:200]
            notes.append("you said %r" % written["text"][:60])
        elif written and written["kind"] == "unclear":
            talk.append(("narrator", "", "I could not tell which move you wrote; try the move's name, like Nf3."))
        # 2. A DRAGGED PIECE, read off the pictures
        r = CH.user_turn(doc, page_no, state, page_id)
        if r.get("ok") and r.get("uci"):
            user_moved = True
            notes.append("you played %s" % r["san"])
        elif not r.get("ok"):
            talk.append(("narrator", "", "Not legal: %s. The piece went back." % r["reason"]))
            notes.append("refused: %s" % r["reason"])
    # a draw offer: the opponent takes it when it is not ahead
    if written and written["kind"] == "draw" and state["status"] == "playing":
        try:
            with CH.Engine(state["strength"]["elo"]) as eng:
                c = eng.candidates(state["fen"], multipv=1)
            board = chess.Board(state["fen"])
            engine_to_move = ("w" if board.turn == chess.WHITE else "b") == state["colors"]["engine"]
            ahead = (c[0]["cp"] if engine_to_move else -c[0]["cp"]) if c else 0
        except Exception:
            ahead = 0
        if ahead <= 50:
            state["status"], state["result"] = "draw_agreed", "1/2-1/2"
            talk.append((_name(state), express(state, "relieved", 0.6, "the player"), "A draw? Fine by me."))
        else:
            talk.append((_name(state), express(state, "smug", 0.6, "the player"), "A draw? Not a chance."))
    # 3. THE OPPONENT ANSWERS
    board = chess.Board(state["fen"])
    engine_to_move = ("w" if board.turn == chess.WHITE else "b") == state["colors"]["engine"]
    if state["status"] == "playing" and engine_to_move and (user_moved or context):
        if user_moved and state["history"]:
            context = ("The player just played %s. " % state["history"][-1]["san"]) + context
        pick = None
        if ask_text is not None:
            pick = lambda prompt: ask_text(prompt)
        r = CH.engine_turn(doc, page_no, state, page_id, pick=pick, context=context.strip())
        if r.get("ok"):
            notes.append("%s played %s (%s%s)" % (_name(state), r["san"], r["how"], ", a blunder draw" if r.get("blundered") else ""))
            talk += _table_lines(state, r, "%s plays %s." % (_short(state), r["san"]))
    elif context and state["status"] == "playing" and not engine_to_move:
        # a remark on the player's own turn: the character may answer (the table decides; a stone
        # may just look at you), and waits for the move
        talk += _remark(state, context, ask_text, log)
    end = _over_line(state)
    if end:
        talk.append(("narrator", "", end))
    _remember_turn(doc, page_id, state, written.get("text") if written and written["kind"] == "say" else "",
                   [t[2] for t in talk if t[0] != "narrator" and str(t[2] or "").strip()], bool(end), log)
    # 4. THE PAGE: every piece exactly on its square, the talk strip replaced, the state saved. The
    # strip is this turn's lines only, every turn -- a bubble never lingers into the next
    CH.tidy(doc, page_no, state, page_id)
    if talk or notes:
        place_talk(doc, page_no, state, talk, page_id, workdir)
    CH.save_state(state)
    if not notes and not talk:
        return "skipped", "chess: nothing new on the page (no move, no writing)"
    return "done", "chess: " + "; ".join(notes + [t[2] for t in talk if t[0] == "narrator"])[:600]


# ------------------------------------------------------------------------------ starting a game
SETUP_PROMPT = """The player asked for a game: "{what}"
These are the characters who can play (id: who they are; how strong they are at chess):
{roster}
Choose the opponent the request fits best, as JSON only, one line:
{{"character": "<an id from the list>", "elo": <a number ONLY if the request names a strength,
else null>, "user_color": "w" or "b"}}
When the request names a strength, still choose the character whose chess is closest to it; when it
does not say a color, "w"."""


def character_setup(cid, elo=None, user_color="w"):
    """A roster character as a chess opponent: its name, its profile as the model plays it, its
    traits, its consistency, and its chess strength unless the request named one."""
    from paperdaemon.pipeline.games import characters as RC
    p = RC.get(cid)
    tr = p["personality"]["traits"]
    return {"game": "chess", "character": cid, "name": p["name"], "profile": RC.brief(cid, "chess"),
            "aggression": float(tr.get("aggression", .5)), "caution": float(tr.get("caution", .5)),
            "risk": float(tr.get("risk", .3)), "consistency": dict(p.get("consistency") or {}),
            "elo": max(400, min(3200, int(elo))) if elo else RC.chess_elo(p), "elo_named": bool(elo),
            "user_color": user_color}


def choose_setup(what, ask_text=None, color=None, strength=None, opponent=None):
    """The opponent and settings for a chess step -> dict, from its fields: `color` (white, black or either),
    `strength` (a rating the player named), `opponent` (a resident's id or name, matched to the roster exactly).
    With no opponent named, the model picks one from the roster by what the player asked for; without a model, the
    resident whose chess is closest to the strength, else to 1200."""
    from paperdaemon.pipeline.games import characters as RC
    elo = int(strength) if isinstance(strength, (int, float)) and 400 <= int(strength) <= 3200 else None
    side = {"white": "w", "black": "b"}.get(str(color or "").lower())
    if side is None:
        side = "w"
    by = {}
    for cid, p in RC.roster().items():
        for k in (cid, p.get("short"), p.get("name")):
            if k:
                by[str(k).strip().lower()] = cid
    cid = by.get(str(opponent or "").strip().lower())
    if cid is None:
        fallback = RC.find(game="chess", elo=elo or 1200, n=1)[0][1]
        cid = fallback
        if ask_text is not None:
            lines = ["%s: %s; chess about %d" % (c, p.get("short") or p.get("summary", "")[:90], RC.chess_elo(p))
                     for c, p in sorted(RC.roster().items())]
            try:
                reply = ask_text(SETUP_PROMPT.format(what=str(what)[:400], roster="\n".join(lines)))
                m = re.search(r"\{.*\}", reply or "", re.S)
                got = json.loads(m.group(0)) if m else {}
            except Exception:
                got = {}
            cid = got.get("character") if got.get("character") in RC.roster() else fallback
    return character_setup(cid, elo, side)


def start_chess(doc, page_no, page_id, setup, ask_text=None, log=None, workdir=None, moves=None):
    """A chess game on this (empty) page: the board and pieces, the state in the notepad, the moves the
    request already played (`moves`, in order from the start, each checked by the rules), and the
    opponent's reply when it is then its turn. -> state"""
    from paperdaemon.pipeline.games import chess as CH
    adaptive = False
    if setup.get("character") and not setup.get("elo_named"):
        # a character whose level follows the player's: their level at chess in THIS notebook
        from paperdaemon.pipeline.games import characters as RC
        from paperdaemon.pipeline.games import table as RS
        if RC.get(setup["character"]).get("adapts"):
            setup = dict(setup, elo=RS.level(doc, setup["character"], "chess", setup["elo"]))
            adaptive = True
    st = CH.new_game(doc, page_id, user_color=setup["user_color"], persona=setup["profile"],
                     traits={k: setup[k] for k in ("aggression", "caution", "risk")}, elo=setup["elo"])
    st["strength"]["adaptive"] = adaptive
    st["strength"]["named"] = bool(setup.get("elo_named"))
    st["persona"]["name"] = setup["name"]
    st["persona"]["profile"] = setup["profile"] if setup.get("character") else "%s: %s" % (setup["name"], setup["profile"])
    if setup.get("character"):
        st["persona"]["character"] = setup["character"]
    if setup.get("consistency"):
        st["persona"]["consistency"] = setup["consistency"]
    alters = False
    if setup.get("character"):
        from paperdaemon.pipeline.games import characters as RC
        # one body, many players: whoever is out plays at their own strength, unless the player named one
        alters = bool(RC.alters(setup["character"]))
        st["strength"]["by_front"] = alters and not setup.get("elo_named")
    # THE MOVES THE REQUEST ALREADY MADE are on the board before it is drawn: "I'm white. e4" starts
    # after 1. e4, with the opponent to reply
    opened, refused = CH.play_opening(st, moves)
    if opened or refused:
        _log(log, "  game: from the request: %s%s" % (CH.movetext(st) or "nothing",
                                                     ("; not played: %r" % refused) if refused else ""))
    CH.setup_page(doc, page_no, st, page_id)
    talk = []
    if setup.get("character"):
        # the game starts: the table decides whether the character says hello at all (a stone may
        # just nod), and the model says it in their voice
        try:
            from paperdaemon.pipeline.games import table as TB
            cid = setup["character"]
            rng = CH.Rng(**st["rng"])
            TB.seat(st, [cid])
            plan = TB.pre_turn(st, cid, {"start"}, rng, interaction="conversation")
            CH.sync_front(st)                   # with alters: the one who sat down is who greets you
            st["rng"] = rng.state()
            said = ""
            truth, presentation = "", None
            if plan["speak"] and ask_text is not None:
                reply = ask_text("You are this character, sitting down to a chess game with the player: %s\n%s\n%s\n"
                                 "Reply with a line SAY: one short greeting in your own voice, then a line FEEL: one of %s "
                                 "and how strongly, 1 to 10. Then TRUTH: true, lie or bluff (private). "
                                 "Then FACE: one fitting signature ID from the private menu above, or none. Not a tell." % (st["persona"]["profile"], "\n".join(CH.facts(st)),
                                                                 "\n".join(plan["prompt_lines"]), ", ".join(CH.EMOTIONS)))
                m = re.search(r"(?im)^\s*SAY:\s*(.+)$", reply or "")
                said = m.group(1).strip().strip('"') if m else ""
                feel, strong, _at = CH.parse_feel(reply)
                from paperdaemon.pipeline.games import cast as rm_cast
                truth, presentation = CH.parse_truth(reply), rm_cast.parse_face(reply)
            else:
                feel, strong = "", None
            seen = TB.post_turn(st, cid, plan, feel or None, strong, truth=truth, speech=said, presentation=presentation)
            said = seen.get("speech", said)
            talk += _table_lines(st, {"table": seen, "said": said})
        except Exception as ex:
            _log(log, "  game: the greeting failed: %s" % str(ex)[:90])
    side = "Black" if setup["user_color"] == "w" else "White"
    talk.append(("narrator", "", "%s plays %s. Move a piece, or write your move." % (setup["name"], side)
                 if st["strength"].get("by_front") else
                 "%s plays %s at about %d. Move a piece, or write your move." % (setup["name"], side, setup["elo"])))
    if opened:
        talk.append(("narrator", "", "From your request: %s." % CH.movetext(st)))
    if refused:
        talk.append(("narrator", "", "Not played: %r is not a legal move there." % refused[:24]))
    from paperdaemon.pipeline.games.chess import rules as chess
    to_move = "w" if chess.Board(st["fen"]).turn == chess.WHITE else "b"
    if st["status"] == "playing" and to_move == st["colors"]["engine"]:
        r = CH.engine_turn(doc, page_no, st, page_id, pick=ask_text)
        if r.get("ok"):
            talk += _table_lines(st, r, "%s plays %s." % (_short(st), r["san"]))
    place_talk(doc, page_no, st, talk, page_id, workdir)
    CH.save_state(st)
    _log(log, "  game: chess %s started against %s (%d)" % (st["id"], setup["name"], setup["elo"]))
    return st
