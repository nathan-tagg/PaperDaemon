r"""Messages: texting the residents of the town, on the tablet. A text messaging game: groups or
individuals, whoever the player names; residents can send images, only when it makes sense.

A CHAT IS A PAGE in whatever notebook the player asks in (so it shares that notebook's memories,
rm_residents): a header with who is in it, the thread -- the residents' messages on the left with their
faces (the feeling that shows, and any tell: rm_table), the player's on the right -- and at the bottom a
box to write in. When the thread fills the page, the chat goes on on a new page.

One turn: the player writes in the box -> the model reads it (vision) -> it becomes their bubble and the
ink goes (WHEREVER THEY WROTE: the box is where to write, but writing above it, on the thread, is read just the
same -- a reply written there was once left unread, and the turn said nothing was written) -> the table decides who answers (in a one-to-one chat nearly always; in a group, the ones named
and whoever would chime in, each at most once, often not everyone) -> each answers in their own voice
from what they remember -> now and then a picture, when showing beats telling -> everyone in the chat
remembers what was said.

State: one game entry per chat in the notepad ("messages"), like chess (rm_chess storage).
"""
from paperdaemon import paths
import os
import re
import time
from paperdaemon.pipeline.games import chess as CH
from paperdaemon.pipeline.page import tablets as TB

HERE = os.path.dirname(os.path.abspath(__file__))

PAGE_W, PAGE_H = 1620, 2160      # the page's picture is designed at a Paper Pro page (tablets.picture_page fits it)
# the header starts at the top of the page's safe area (below the tablet's toolbar), the thread under it
HEAD_TOP = int(CH.TOP)
# the picture ends at BOX_TOP: under it is the page itself, the player's space to type or write in (inputarea.py)
THREAD_TOP, THREAD_BOTTOM, BOX_TOP = HEAD_TOP + 140, 1740, 1800
M = 70
AVATAR = 160  # large enough to keep a face's authored detail and tells
AVATAR_GAP = 20
INK, GRAY, RULE = (24, 24, 26), (100, 100, 106), (205, 205, 210)
THEIRS, MINE = (242, 242, 243), (222, 233, 244)

# THE HOUSE STYLE for a picture a resident sends. A resident who is IN the picture goes in as a
# reference (their face icon), so they look like themselves.
PICTURE_STYLE = ("{what}. A picture a friend texted: a flat cartoon illustration with thick, clean black "
                 "outlines of even weight, simple rounded shapes and soft flat colors, like a friendly "
                 "picture book{setting}. No text, no lettering, no "
                 "speech bubbles, no frame.")


def _setting():
    """"; <where the cast lives>" for the house style, or "" when the cast says nothing."""
    from paperdaemon.pipeline.games import characters as RC
    where = RC.setting()
    return "; " + where if where else ""


SELF_STYLE = ("The character in the reference image, drawn in exactly the same flat cartoon style, "
              "{what}. Thick, clean black outlines, simple rounded shapes, soft flat colors; the "
              "same face, colors and clothes as the reference. Preserve the reference's current "
              "expression and small facial or clothing details; do not substitute a generic smile. No text, no lettering.")


def _font(name, size):
    from paperdaemon import paths
    return paths.pil_font(name, size)


def _fit(d, text, font, width):
    """`text` cut to `width` with an ellipsis when it would run past it."""
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "\u2026", font=font) > width:
        text = text[:-1]
    return text.rstrip(" ,") + "\u2026"


def _names_line(d, names, font, width):
    """As many of `names` as fit on one line, then "and N more" (a group chat's member line)."""
    for k in range(len(names), 0, -1):
        line = ", ".join(names[:k]) + ("" if k == len(names) else " and %d more" % (len(names) - k))
        if d.textlength(line, font=font) <= width:
            return line
    return _fit(d, "%d people" % len(names), font, width)


def _wrap(d, text, font, width):
    out = []
    for para in str(text).split("\n"):
        line = ""
        for w in para.split():
            t = (line + " " + w).strip()
            if d.textlength(t, font=font) > width and line:
                out.append(line)
                line = w
            else:
                line = t
        out.append(line)
    return out or [""]


# ------------------------------------------------------------------------------ the state
def new_state(doc, members, title=None):
    from paperdaemon.pipeline.games import characters as RC
    seed = CH.new_seed()
    now = int(time.time())
    names = [RC.get(c)["short"] for c in members]
    title = title or (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1] if len(names) <= 3
                      else ", ".join(names[:3]) + " & %d others" % (len(names) - 3))
    return {"game": "messages", "version": 1, "id": "chat-" + seed[:8], "doc": doc, "page_id": None, "pages": [],
            "first": {}, "title": title[:80], "members": list(members), "messages": [],
            "rng": {"seed": seed, "draws": 0}, "status": "open", "created": now, "updated": now}


def summary_lines(state):
    last = state["messages"][-1] if state["messages"] else None
    return ["messages %s: a chat with %s" % (state["id"], state["title"]),
            "%d messages%s" % (len(state["messages"]), (" ; last from %s: %s" % (last["from"], last["text"][:80])) if last else "")]


CH.SUMMARIES["messages"] = summary_lines


# ------------------------------------------------------------------------------ the page
def _bubble_h(d, m, font, width, img_h):
    lines = _wrap(d, m["text"], font, width - 44) if m.get("text") else []
    height = len(lines) * 40 + (26 if lines else 0) + (img_h + 16 if m.get("image") else 0)
    return max(height + 30, AVATAR + 22) if m["from"] != "me" else height


def _image_h(m, want_w=520):
    if not m.get("image_path") or not os.path.exists(m["image_path"]):
        return 0
    from PIL import Image
    with Image.open(m["image_path"]) as im:
        w, h = im.size
    return int(round(want_w * h / float(w)))


def layout(state, first):
    """Which messages fit on the current page, starting at `first` -> (the ones that fit, overflowed)."""
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = _font("reMarkableSans-Regular.ttf", 30)
    y, fit = THREAD_TOP, []
    for m in state["messages"][first:]:
        h = _bubble_h(d, m, font, 1000, _image_h(m)) + 24
        if y + h > THREAD_BOTTOM:
            return fit, True
        fit.append(m)
        y += h
    return fit, False


def page_png(state, first, out, col_px=None):
    """The chat page's picture: who is in it, the thread from message `first`, and at its foot where to answer, from
    `col_px` (the typed-text column's left edge, design pixels). The picture is cut at BOX_TOP when it is placed. Laid
    out in design pixels, drawn at twice the tablet's resolution (draw.scaled)."""
    from paperdaemon.pipeline.games import characters as RC
    from paperdaemon.pipeline.draw import scaled as SD
    from PIL import Image
    im, d = SD.canvas(PAGE_W, PAGE_H)
    big, reg, small, name_f = (_font("reMarkableSans-Bold.ttf", 40), _font("reMarkableSans-Regular.ttf", 30),
                               _font("reMarkableSans-Regular.ttf", 22), _font("reMarkableSans-Medium.ttf", 22))
    # HEADER, as a group chat's: the first few members' faces overlapping (for one with alters, whoever they pass as
    # now), "+N" for the rest; beside them who the chat is with -- the name, or two or three names, or "N people" with
    # the names that fit under it and how many more. Every line is cut to the page.
    from paperdaemon.pipeline.games import table as TB
    members = state["members"]
    names = []
    for cid in members:
        fr = TB.front(state, cid)
        names.append(RC.get((fr or {}).get("shows") or cid)["short"])
    shown = members[:5] if len(members) <= 6 else members[:4]
    x, step = M, 60                                             # 84-pixel faces, each over the one before by 24
    for cid in shown:
        fr = TB.front(state, cid)
        d.ellipse((x - 4, HEAD_TOP - 4, x + 88, HEAD_TOP + 88), fill="white")
        with Image.open(RC.face_png(cid, "neutral", (), fr["shows"] if fr else None)) as f:
            SD.paste(im, f.convert("RGBA"), (x, HEAD_TOP), (84, 84), mask=True)
        x += step
    if len(members) > len(shown):                               # the rest, counted
        d.ellipse((x - 4, HEAD_TOP - 4, x + 88, HEAD_TOP + 88), fill="white")
        d.ellipse((x, HEAD_TOP, x + 84, HEAD_TOP + 84), fill=THEIRS, outline=RULE, width=2)
        more = "+%d" % (len(members) - len(shown))
        mf = _font("reMarkableSans-Medium.ttf", 30 if len(more) <= 3 else 24)
        d.text((x + 42, HEAD_TOP + 42), more, font=mf, fill=GRAY, anchor="mm")
        x += step
    tx = x + 24 + (84 - step)
    room = PAGE_W - M - tx
    few = names[0] if len(members) == 1 else ", ".join(names[:-1]) + " & " + names[-1]
    if len(members) <= 3 and d.textlength(few, font=big) <= room:    # everyone named in the title itself
        d.text((tx, HEAD_TOP + 18), few, font=big, fill=INK)
    else:                                                       # a count, and under it the names that fit
        d.text((tx, HEAD_TOP - 2), _fit(d, "%d people" % len(members), big, room), font=big, fill=INK)
        d.text((tx, HEAD_TOP + 54), _names_line(d, names, reg, room), font=reg, fill=GRAY)
    d.line((M, HEAD_TOP + 108, PAGE_W - M, HEAD_TOP + 108), fill=RULE, width=2)
    fit, _over = layout(state, first)
    y = THREAD_TOP
    for m in fit:
        img_h = _image_h(m)
        lines = _wrap(d, m["text"], reg, 1000 - 44) if m.get("text") else []
        tw = max([d.textlength(l, font=reg) for l in lines] + [0])
        bw = int(max(tw + 44, (560 if m.get("image") else 0), 120))
        bh = len(lines) * 40 + (26 if lines else 0) + (img_h + 16 if m.get("image") else 0)
        if m["from"] == "me":
            bx = PAGE_W - M - bw
            d.rounded_rectangle((bx, y, bx + bw, y + bh), 26, fill=MINE, outline=(185, 200, 216), width=2)
            by = y
        else:
            p = RC.get(m.get("look") or m["from"])
            with Image.open(RC.face_png(m["from"], m.get("shows") or "neutral", tuple(m.get("marks") or ()),
                                        m.get("look"))) as f:
                SD.paste(im, f.convert("RGBA"), (M, y + 22), (AVATAR, AVATAR), mask=True)
            d.text((M + AVATAR + AVATAR_GAP, y), 'Scene' if m.get('scene_event') else p["short"], font=name_f, fill=GRAY)
            bx, by = M + AVATAR + AVATAR_GAP, y + 30
            d.rounded_rectangle((bx, by, bx + bw, by + bh), 26, fill=THEIRS, outline=RULE, width=2)
        ty = by + 13
        if m.get("image") and img_h:
            with Image.open(m["image_path"]) as src:
                SD.paste(im, src.convert("RGB"), (bx + 20, ty + 4), (520, img_h))
            ty += img_h + 16
        for l in lines:
            d.text((bx + 22, ty), l, font=reg, fill=INK)
            ty += 40
        y += _bubble_h(d, m, reg, 1000, img_h) + 24
    from paperdaemon.pipeline.games import inputarea as IA
    IA.foot(d, BOX_TOP, "Message: type or write it below", M if col_px is None else col_px, _font("reMarkableSans-Medium.ttf", 30), IA.LABEL_INK, RULE)
    im.save(out)
    return out


# ------------------------------------------------------------------------------ the model's prompts
READ_PROMPT = """This is the player's handwriting on a messaging page on a tablet, alone: their next message (or the
rest of it, after what they typed).
Read what they wrote, top to bottom. Answer with one line:
MESSAGE: <exactly what they wrote, spelling fixed, line breaks as spaces>
or NOTHING if nothing is written or it is unreadable."""

REPLY_PROMPT = """You are texting as a resident of the town. Who you are:
{brief}
{knows}
What you remember that bears on this (your own memories, in this notebook):
{memory}
This is a {kind}. The conversation so far, oldest first ("you" is the player):
{thread}
{addressed}
{table}
Reply the way {short} would text: one message, short, in {short}'s own voice, true to what you remember
(never invent a memory you don't have; if you don't know something, you can say so).
Answer in these lines:
SAY: <your one message>   (or NO REPLY if {short} would leave it unanswered)
IMAGE: <now and then, as people text a photo -- where you are, what you're up to, something you're talking
about, a selfie -- what the picture shows, in one sentence, and it goes with your message; most messages have
none, so leave this line out unless {short} would really send one>
IMAGE OF: <self if {short} is in the picture, other if not; only with an IMAGE line>
FEEL: <one of {emotions}> <1-10> [at <whom>]
FACE: <one fitting signature ID from the private menu above, or none; not a tell>
REMEMBER: <one short thing {short} will remember from this exchange, in their own words, or none>
TRUTH: true, lie or bluff -- whether what you said is true (nobody sees this line)"""


# A LINE'S VALUE IS ON ITS OWN LINE: [ 	]*, never \s*, after the label -- an empty "IMAGE:" took the next line
# ("IMAGE OF: ...") as what the picture shows, and a picture nobody asked for was drawn. A value that is only
# another line's label is no value.
_LABEL = re.compile(r"(?i)^(SAY|IMAGE|IMAGE OF|FEEL|FACE|REMEMBER|TRUTH):")


def _line(label, t):
    m = re.search(r"(?im)^[ \t]*%s:[ \t]*(\S.*)$" % label, t)
    v = m.group(1).strip() if m else ""
    return "" if _LABEL.match(v) else v


def parse_reply(text):
    t = str(text or "")
    say, img, rem = _line("SAY", t), _line("IMAGE", t), _line("REMEMBER", t)
    said = say.strip('"')
    if re.fullmatch(r"(?i)\(?no reply\)?\.?", said) or not said and re.search(r"(?i)\bNO REPLY\b", t):
        said = ""
    remember = rem
    if re.fullmatch(r"(?i)none\.?|nothing\.?|-", remember):
        remember = ""
    image = img
    if re.fullmatch(r"(?i)none\.?|no\.?|-|n/a", image):
        image = ""
    feel, strong, at = CH.parse_feel(t)
    from paperdaemon.pipeline.games import cast as rm_cast
    of = re.search(r"(?im)^\s*IMAGE OF:\s*(self|other)\b", t)
    return {"say": said, "image": image, "image_of": of.group(1).lower() if of else "other",
            "remember": remember, "feel": feel, "intensity": strong, "at": at,
            "truth": CH.parse_truth(t), "presentation": rm_cast.parse_face(t)}


# ------------------------------------------------------------------------------ starting a chat
def pick_members(members, what="", ask_text=None):
    """Who the chat is with -> [ids]. `members` are the step's: each a resident's id, short name or full name,
    matched to the roster exactly (case aside). With none that match, the model picks from the roster by what the
    player asked for (a group they describe: "the chess club")."""
    from paperdaemon.pipeline.games import characters as RC
    r = RC.roster()
    by = {}
    for cid, p in r.items():
        for k in (cid, p["short"], p["name"]):
            by[str(k).strip().lower()] = cid
    found = []
    for m in members or ():
        cid = by.get(str(m).strip().lower())
        if cid and cid not in found:
            found.append(cid)
    if found or ask_text is None or not str(what or "").strip():
        return found
    menu = "\n".join("%s: %s -- %s" % (cid, p["name"], p["summary"][:80]) for cid, p in sorted(r.items()))
    reply = ask_text("The player wants to text: \"%s\". These are the residents:\n%s\nAnswer with the ids of who "
                     "should be in the chat, comma separated, and nothing else." % (str(what)[:300], menu))
    out = []
    for c in str(reply or "").replace(",", " ").split():
        if c in r and c not in out:
            out.append(c)
    return out


def start(doc, page_no, page_id, members, workdir=None, first_message=""):
    """A chat on this (new) page -> state. `first_message`, if the player wrote one with the request, waits
    in the thread for the residents to answer on the next turn."""
    state = new_state(doc, members)
    state["page_id"], state["pages"], state["first"] = page_id, [page_id], {page_id: 0}
    if first_message:
        state["messages"].append({"n": 1, "from": "me", "text": first_message[:600], "at": int(time.time()), "page": page_id})
    _draw(doc, page_no, page_id, state, workdir)
    CH.save_state(state)
    return state


def _draw(doc, page_no, page_id, state, workdir=None):
    """The page's picture, replaced."""
    from paperdaemon.pipeline.page import images as IM
    workdir = workdir or os.path.join(paths.state_dir(), "rm-queue")
    os.makedirs(workdir, exist_ok=True)
    old = (state.get("picture") or {}).get(page_id)
    if old:
        try:
            IM.remove_in_box(doc, page_no, tuple(old["box"]), page_id=page_id)
        except Exception:
            pass
    png = os.path.join(workdir, "_chat_%d.png" % int(time.time() * 1000))
    try:
        from paperdaemon.pipeline.games import inputarea as IA
        page_png(state, state["first"].get(page_id, 0), png, col_px=IA.column_px(doc, page_no, PAGE_W))
        r = IA.place(doc, page_no, page_id, png, BOX_TOP)          # the picture ends where the player's space begins
        IM.record_placement(r["doc"], page_no, r["name"], r["box"], hash=r["hash"], kind="messages", game=state["id"])
        state.setdefault("picture", {})[page_id] = {"hash": r["hash"], "name": r["name"], "box": list(r["box"])}
    finally:
        try:
            os.remove(png)
        except OSError:
            pass


# ------------------------------------------------------------------------------ one turn
def _ink_top(doc, page_no):
    """Where the player's writing may start: under the toolbar's band (the daemon's notes, and his retry box)."""
    from paperdaemon.pipeline import page as PG
    return PG.safe_area(tuple(TB.frame_of(doc, page_no)))[1]


def _read(doc, page_no, ask_vision, workdir):
    """The player's message: what they typed, then what they handwrote anywhere under the band (inputarea.read)."""
    from paperdaemon.pipeline.games import inputarea as IA
    return IA.read(doc, page_no, _ink_top(doc, page_no), ask_vision, READ_PROMPT, "MESSAGE", workdir)


def _erase_ink(doc, page_no):
    """The player's message off the page once it is read (it is their bubble now): what they typed, and all their
    ink under the band, wherever they wrote it."""
    from paperdaemon.pipeline.games import inputarea as IA
    IA.clear(doc, page_no, _ink_top(doc, page_no))


def _thread_text(state, last=14):
    from paperdaemon.pipeline.games import characters as RC
    out = []
    for m in state["messages"][-last:]:
        who = 'Scene' if m.get('scene_event') else ("you" if m["from"] == "me" else RC.get(m.get("look") or m["from"])["short"])
        out.append("%s: %s%s" % (who, m.get("text") or "", " [sent a picture: %s]" % m["image"] if m.get("image") else ""))
    return "\n".join(out) or "(nothing yet)"


def turn(doc, page_no, page_id, state, ask_text, ask_vision, paint=None, log=None, workdir=None):
    """One turn of a chat -> (outcome, note)."""
    from paperdaemon.pipeline.games import characters as RC
    from paperdaemon.pipeline.games import table as RS
    from paperdaemon.pipeline.games import table as TB
    workdir = workdir or os.path.join(paths.state_dir(), "rm-queue")
    if page_id != state["page_id"]:
        return "skipped", "messages: an earlier page of this chat; it goes on at the last one"
    if ask_text is None or ask_vision is None:
        return "skipped", "messages: the model is not answering, so nobody can read the page"
    text = _read(doc, page_no, ask_vision, workdir)
    pending = [m for m in state["messages"] if m["from"] == "me" and not m.get("answered")]
    if not text and not pending:
        return "skipped", "messages: nothing typed or written on the page yet"
    now = int(time.time())
    members = state["members"]
    if text:
        _erase_ink(doc, page_no)
        state["messages"].append({"n": len(state["messages"]) + 1, "from": "me", "text": text[:600], "at": now,
                                  "page": page_id})
    said = " / ".join(m["text"] for m in state["messages"] if m["from"] == "me" and not m.get("answered"))
    for m in state["messages"]:
        if m["from"] == "me":
            m["answered"] = True
    kind = "one-to-one chat with the player" if len(members) == 1 else "group chat with the player and %s" % ", ".join(
        RC.get(c)["short"] for c in members)

    def out(cid):                              # who is out, for a resident with alters (their memories are theirs)
        fr = TB.front(state, cid)
        return fr["id"] if fr else None
    # who answers: the table decides (one message each at most, often not everyone in a group)
    rng = CH.Rng(**state["rng"])
    state['cast_input']=said
    TB.seat(state, members)
    TB.next_turn(state)
    from paperdaemon.pipeline.games import cast as rm_cast
    # Decide who receives this turn before reading/writing private memories.
    # Preparation is idempotent, so pre_turn below does not roll another switch.
    active = [rm_cast.prepare(state,cid,rng,()) for cid in members]
    # a pack's interaction may turn the input into a scene event, narrated into the thread as a message
    event=rm_cast.interact(state,said,ask_text)
    if event and event.get('scene') and event.get('id') and not any(m.get('scene_event')==event['id'] for m in state['messages']):
        state['messages'].append(dict(n=len(state['messages'])+1,**{'from':event.get('actor') or members[0]},text=event['scene'],
            at=now,page=page_id,shows='neutral',marks=[],scene_event=event['id']))
    rm_cast.challenge_input(state, active, said, ask_text)
    for cid in members:
        RS.remember(doc, cid, "The player texted %s: \"%s\"" % ("me" if len(members) == 1 else "the group chat", said[:300]),
                    kind="said", page=page_id, with_=members, weight=0.45, alter=out(cid))
    low = said.lower()
    plans = []
    for cid in members:
        p = RC.get(cid)
        named = len(members) == 1 or any(re.search(r"\b%s\b" % re.escape(n.lower()), low)
                                         for n in {p["short"], cid.split("-")[0]} if len(n) > 2)
        plan = TB.pre_turn(state, cid, set(), rng, addressed=named, others_speaking=0, budget=1, interaction='conversation')
        plans.append((0 if named else 1, cid, plan))
    state["rng"] = rng.state()
    order = [x for x in sorted(plans, key=lambda t: t[0])]
    # A FEW REPLIES A TURN, as in a real group chat: everyone the message names may answer, and a few others who
    # would chime in -- four at most, however big the group (each reply is a model call)
    named_n = sum(1 for p in plans if p[0] == 0)
    limit = 1 if len(members) == 1 else max(named_n, min(4, (len(members) + 1) // 2))
    replies, images = 0, []
    for _pri, cid, plan in order:
        if replies >= limit or not plan["speak"]:
            TB.post_turn(state, cid, plan)
            continue
        fr = plan.get("front") or {}
        aid = fr.get("id")
        name = TB.who(state, cid)                  # an alter's own name when one is out
        memory = RS.recall(doc, cid, said, with_=members, alter=aid)
        q = REPLY_PROMPT.format(
            brief=RC.brief(cid, table=[c for c in members if c != cid], front=aid, shows=fr.get("shows")),
            knows=RS.about_player(doc, cid, aid),
            memory="\n".join("- " + l for l in memory) or "- nothing yet", kind=kind, thread=_thread_text(state),
            addressed=("The player's message is to you." if len(members) == 1 else
                       "The message names you; answer it." if _pri == 0 else "Chime in only if you would."),
            table="\n".join(plan["prompt_lines"]), short=name, emotions=", ".join(CH.EMOTIONS))
        try:
            reply=ask_text(q)
            rm_cast.suspicion_from_reply(state,plan,reply)
            r = parse_reply(reply)
        except Exception as ex:
            if log:
                log("  messages: %s's reply failed: %s" % (name, str(ex)[:100]))
            TB.post_turn(state, cid, plan)
            continue
        seen = TB.post_turn(state, cid, plan, r["feel"] or None, r["intensity"], r["at"], r["truth"], speech=r['say'], presentation=r['presentation'])
        r['say']=seen.get('speech', r['say'])
        if not r["say"] and not r["image"]:
            continue
        msg = {"n": len(state["messages"]) + 1, "from": cid, "text": r["say"][:600], "at": int(time.time()), "page": page_id,
               "shows": seen["shows"], "marks": seen["marks"], "acts": seen["acts"],
               "player_id": seen.get("player_id")}
        if seen.get("look"):
            msg["look"] = seen["look"]               # whose face: who they pass as
        if r["image"]:
            msg["image"] = r["image"][:240]
            msg["image_of"] = r.get("image_of") or "other"
            images.append(msg)
        state["messages"].append(msg)
        replies += 1
        RS.remember(doc, cid, "I texted back: \"%s\"%s" % (r["say"][:300], (" and sent a picture of %s" % r["image"][:120]) if r["image"] else ""),
                    kind="chat", page=page_id, with_=members, weight=0.35, alter=aid)
        if r["remember"]:
            RS.remember(doc, cid, r["remember"], kind="fact", page=page_id, with_=members, weight=0.75, alter=aid)
        if r["feel"] in ("happy", "relieved") or r["feel"] == "smug" and "player" in (r["at"] or ""):
            RS.warm(doc, cid, 0.03, alter=aid)
        elif r["feel"] in ("angry", "jealous") and "player" in (r["at"] or ""):
            RS.warm(doc, cid, -0.04, alter=aid)
        for other in members:
            if other != cid:
                RS.remember(doc, other, "%s said in the chat: \"%s\"" % (RC.get(seen.get('look') or cid)["short"], r["say"][:240]), kind="heard",
                            page=page_id, with_=[cid], weight=0.3, alter=out(other))
    _paint_images(doc, state, images, paint, log)
    # the page: the thread, or a new page when it no longer fits
    first = state["first"].get(page_id, 0)
    fit, over = layout(state, first)
    if over:
        from paperdaemon.remarkable import library as PG
        from paperdaemon.pipeline.page import render as R
        _draw(doc, page_no, page_id, state, workdir)           # this page keeps what fits on it
        pid = PG.insert_pages(doc, page_id, 1)[0][0]           # the chat goes on right after this page
        pno = [p["id"] for p in R.live_pages(doc)].index(pid) + 1
        state["first"][pid] = max(first + len(fit) - 2, 0)    # the last two carry over for context
        state["page_id"] = pid
        state["pages"].append(pid)
        _draw(doc, pno, pid, state, workdir)
    else:
        _draw(doc, page_no, page_id, state, workdir)
    CH.save_state(state)
    who = [RC.get(m["from"])["short"] for m in state["messages"][-replies:]] if replies else []
    return "done", "messages (%s): you said %r; %s" % (state["title"], said[:60], ("replies from " + ", ".join(who)) if who else "no reply")


def _paint_images(doc, state, msgs, paint, log=None):
    """The pictures residents chose to send: one hand-over of the card for all of them. A resident who is
    in the picture goes in as a reference (their face icon), so they look like themselves."""
    from paperdaemon.pipeline.games import characters as RC
    if not msgs:
        return
    if paint is None:
        for m in msgs:
            m["image_note"] = "the picture could not be drawn"
        return
    keep = os.path.join(CH.NOTEPAD_DIR, doc, "pictures")
    os.makedirs(keep, exist_ok=True)
    for m in msgs:
        who = RC.get(m["from"])
        selfie = m.get("image_of") == "self"          # the resident said they are in it
        try:
            if selfie:
                png = paint(SELF_STYLE.format(what=m["image"]), "edit",
                            RC.face_png(m["from"], m.get("shows") or "happy", tuple(m.get("marks") or ()), m.get("look")))
            else:
                png = paint(PICTURE_STYLE.format(what=m["image"], setting=_setting()), "new", None)
        except Exception as ex:
            if log:
                log("  messages: %s's picture failed: %s" % (who["short"], str(ex)[:100]))
            m["image_note"] = "the picture could not be drawn"
            continue
        dst = os.path.join(keep, "%s-%03d.png" % (state["id"], m["n"]))
        import shutil
        shutil.move(png, dst)
        m["image_path"] = dst
