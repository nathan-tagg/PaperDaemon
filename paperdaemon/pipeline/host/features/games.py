"""Game pages: chess, the adventure and the messages, run by their engines."""
import re
import time
from paperdaemon import ledger as S
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline import host as H


def _game_job(doc_id, page, name, t0):
    """One turn on a game page (rm_games.play) -> converse()'s (outcome, note, seconds, messages)."""
    from paperdaemon.pipeline import games as GM
    up = H._llm_up()
    if not up:
        H.log("  game: the text model is not answering -- the opponent plays by its traits and says nothing")
    try:
        res = GM.play(doc_id, page, JOB.page_id, ask_text=H._ask_text if up else None,
                      ask_vision=H._ask_vision if up else None, log=H.log, workdir=H.QUEUE, paint=H._paint)
    except Exception as ex:
        H._warn("playing the game", ex)
        res = ("skipped", "the game turn failed: %s: %s" % (type(ex).__name__, str(ex)[:120]))
    outcome, note = res or ("skipped", "no game on this page")
    # the host changed the page itself (tidied pieces, the opponent's move, the talk strip): that is
    # this job's own write, never a change "under" it
    JOB.committed = True
    try:
        JOB.sha_commit = S.page_state(doc_id, JOB.page_id)["sha"]
    except Exception:
        pass
    JOB.outcome, JOB.note = outcome, note
    H.log("  %s in %ds -- %s" % (outcome.upper(), int(time.time() - t0), note[:160]))
    return outcome, note, int(time.time() - t0), []


def _paint(prompt, mode="new", src=None):
    """A game's picture (rm_games.play's `paint`): the picture model onto the card, one picture -- an EDIT
    of `src` (the reference-image way) or a new one -- and the talker back. -> a PNG path
    the caller keeps or deletes."""
    if mode == "edit" and src:
        abilities = H._image_offer().get("abilities")
        if abilities is None or "edit_reference" in abilities:
            return H._picture_model(lambda: H._edit_png(src, prompt, mode="ref"))
        # an image model that cannot edit from a reference draws the scene afresh
        H.log("  the image model has no reference editing: the scene is drawn afresh")
    return H._picture_model(lambda: H._generate_png(prompt, 1024))


def _game_page(doc):
    """THE PAGE THAT ASKED is the game's page (the request comes off at commit), with the job's own tag on it so
    every move comes back as a job, for this job's lineup. -> (page id, page number)."""
    from paperdaemon.remarkable import library as PG_
    pid = JOB.page_id
    pno = [i + 1 for i, q in enumerate(R.live_pages(doc)) if q["id"] == pid][0]
    _clear_page(doc, pno)
    try:
        PG_.tag_page(doc, pid, S.TRIGGER)
    except Exception as ex:
        H._warn("tagging the game's page", ex)
    return pid, pno


def _clear_page(doc, pno):
    """A GAME TAKES THE PAGE WHOLE: everything already on it -- the user's ink, typed text and pictures -- comes off
    before the game is drawn, or the board lands on top of it. The page is recorded first, so what was there can be
    restored. The erases the job had staged (the request) are done with it."""
    from paperdaemon.pipeline import page as P
    from paperdaemon.pipeline.page import images as IM
    try:
        P.record(doc, pno, note="before a game took the page")
    except Exception as ex:
        H._warn("recording the page before the game", ex)
    ink = text = pics = 0
    try:
        ink = (P.erase(doc, pno, lambda L: True) or {}).get("erased", 0)
    except Exception as ex:
        H._warn("clearing the ink for the game", ex)
    try:
        text = (P.erase_text(doc, pno) or {}).get("items", 0)
    except Exception as ex:
        H._warn("clearing the typed text for the game", ex)
    try:
        items = [i["item"] for i in IM.items(doc, pno) if i.get("item")]
        pics = IM.remove_items(doc, pno, items) if items else 0
    except Exception as ex:
        H._warn("clearing the pictures for the game", ex)
    JOB.hide, JOB.hide_typed, JOB.hide_images = {}, [], []
    if JOB.plan is not None:
        JOB.plan["erase_done"] = True
    H.log("  the game takes the page: %d stroke(s), %d typed item(s) and %d picture(s) came off" % (ink, text, pics or 0))


def _own_writes():
    """What the game put on the page that asked is the job's own work, written: the job has changed the page (so it
    is done, not skipped, though the commit has nothing left to write), and the page as it is now is the job's, not
    the user's writing to send back to the queue."""
    JOB.committed = True
    try:
        JOB.sha_start = JOB.sha_commit = S.page_state(JOB.doc, JOB.page_id)["sha"]
    except Exception as ex:
        H._warn("reading the game's page", ex)


def _run_game(step):
    """A game step -- chess, adventure or messages -- played on the page that asked (an adventure's sheet and log go
    right after it), with the trigger tag on the page that is played so every move comes back as a job. Its fields
    say how: a chess game's color, strength, opponent and the moves already made; a chat's members. -> (ok, note)"""
    from paperdaemon.pipeline import games as GM
    doc, kind, what = JOB.doc, step["do"], step.get("what") or ""
    if kind == "adventure":
        from paperdaemon.pipeline.games import adventure as AD_
        if not H._llm_up():
            return False, "the text model is not answering, so there is no game master"
        _clear_page(doc, [i + 1 for i, q in enumerate(R.live_pages(doc)) if q["id"] == JOB.page_id][0])
        st, adoc = AD_.start(what, H._ask_text, paint=H._paint, log=H.log, workdir=H.QUEUE, doc=doc, after=JOB.page_id,
                             here=True)
        _own_writes()
        try:
            from paperdaemon.remarkable import library as PG_
            PG_.tag_page(doc, st["page_id"], S.TRIGGER)
        except Exception as ex:
            H._warn("tagging the adventure's scene page", ex)
        nums = [i + 1 for i, q in enumerate(R.live_pages(doc)) if q["id"] in (st.get("pages") or [])]
        return True, ("Ink Adventure “%s” is ready, with %s as the hero: pages %d to %d of this notebook, the story "
                      "on page %d" % (st["title"], st["hero"]["name"], min(nums), max(nums),
                                      [i + 1 for i, q in enumerate(R.live_pages(doc)) if q["id"] == st["page_id"]][0]))
    from paperdaemon import paths as CT_
    if not CT_.games_installed():
        # chess opponents and chat partners are characters from installed content
        return False, CT_.not_installed("The games' character content", "games", "characters")
    ask = H._ask_text if H._llm_up() else None
    if kind == "messages":
        from paperdaemon.pipeline.games import messages as MS
        members = MS.pick_members(step.get("members"), what, ask)
        if not members:
            return False, "nobody to text: name a resident, or several for a group chat"
        pid, pno = H._game_page(doc)
        st = MS.start(doc, pno, pid, members, workdir=H.QUEUE)
        _own_writes()
        return True, "a chat with %s is on this page: write in the box at the bottom" % st["title"]
    setup = GM.choose_setup(what, ask, color=step.get("color"), strength=step.get("strength"),
                            opponent=step.get("opponent"))
    pid, pno = H._game_page(doc)
    st = GM.start_chess(doc, pno, pid, setup, ask_text=ask, log=H.log, workdir=H.QUEUE, moves=step.get("moves"))
    _own_writes()
    from paperdaemon.pipeline.games import chess as CH_
    played = CH_.movetext(st) if st and st.get("history") else ""
    return True, "chess against %s (about %d) is on this page%s" % (
        setup["name"], setup["elo"], ("; the moves so far: %s" % played) if played else "")
