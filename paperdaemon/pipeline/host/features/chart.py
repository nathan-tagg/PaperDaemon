"""Charts and calendars: the spec the model writes, the facts the host adds, and the picture on the page."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from paperdaemon.pipeline import charts as CH
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline import host as H

_GEO_CACHE = {}


def t_chart(spec, place=None):
    """Draw a REAL chart from data, into a box you planned.

    The model supplies numbers and labels; the axes, ticks, scale and legend are computed: structure from the
    model, geometry from code.

    Rendered at 1200-1620 px, the band where the decomposer traces at full resolution; below it a 1-px rule
    turns gray and is dropped.
    """
    plan = JOB.plan or {}
    boxes = plan.get("places") or {}
    if not boxes:
        return {"error": "call plan() first and give the chart a place of its own, "
                         "e.g. {\"id\": \"chart\", \"kind\": \"chart\", \"size\": \"large\"}."}
    if place is None:
        place = H._cur_place()
    if place not in boxes:
        return {"error": "there is no place called %r in your plan. You planned: %s."
                         % (place, ", ".join(sorted(boxes)))}
    box = boxes[place]
    try:
        spec = json.loads(spec) if isinstance(spec, str) else spec
    except Exception as ex:
        return {"error": "the spec is not valid JSON: %s" % str(ex)[:120]}
    if not isinstance(spec, dict):
        return {"error": "the spec must be a JSON object with a 'type'."}
    # keys as the model MEANT them: a thinking turn produced `"title: "` and `"type: "` (a colon
    # and a space inside the key), and the spec then had no type at all
    # ...and a curly quote INSIDE a key: `"days”: {...}` dropped every event and card of a
    # redone week without a word
    spec = dict((str(k).strip().strip(":").strip().strip("\"'“”‘’`").strip()
                 .strip(":").strip().lower(), v) for k, v in spec.items())
    if not spec.get("type"):
        # the shape says what a CALENDAR is, so a calendar spec without "type" still draws. A bare
        # categories/series spec is NOT guessed (a pie read as a bar): an explicit error costs one turn
        if "days" in spec and "marks" not in spec and "month" not in spec:
            spec["type"] = "week"
        elif "marks" in spec or "month" in spec:
            spec["type"] = "calendar"
        else:
            return {"error": "the spec has no 'type'. Say which chart: bar, hbar, line, pie, donut, "
                             "area, scatter ... (calendar and week are inferred from their shape)."}
    ctype = str(spec.get("type") or "").lower()
    # a clipped post is a picture, so a picture's place takes one (t_fetch puts a Reddit picture
    # there as its post)
    if box["kind"] not in ("chart", "calendar") and not (ctype == "posts" and box["kind"] == "image"):
        return {"error": "the place %r is a %s, not a chart. Plan it as kind='chart' (or "
                         "'calendar' for a month or a week)." % (place, box["kind"])}
    dropped = []
    if ctype in ("calendar", "week"):
        # A month or a week is built for the page. The forecast, the holidays and the user's home
        # place come from here, not from the model -- it only ever gets those wrong.
        if box["kind"] != "calendar":
            return {"error": "a %s takes the whole page: plan its place as kind='calendar', "
                             "size='full', then call chart again." % ctype}
        H._calendar_defaults(spec)
    elif ctype == "posts":
        err = H._fill_posts(spec, place)         # the real posts, from the site: never the model's
        if err:
            return {"error": err}
    # Validate. A card that does not scan or does not fit is DROPPED, and the model told, rather than the whole
    # page refused: the calendar is the job, and a second chart() call would draw the month twice.
    for _ in range(40):
        try:
            CH.validate(spec)
            break
        except CH.SpecError as ex:
            key = H._drop_card(spec, str(ex))
            if key is None:
                return {"error": str(ex)}
            dropped.append("%s: %s" % (key, str(ex)[:150]))
    else:
        return {"error": "the spec keeps failing after dropping %d cards: %s" % (len(dropped), dropped[-1])}
    png = os.path.join(H._STATE, "rm-host-chart.png")
    strokes, bh = None, float(box["h"])
    # THE PICTURE PATH (direct image insert): the render itself goes onto the page as an image the way the app
    # places a capture (rm_images) -- pixel for pixel, true color, no tracing. It joins the draft now and is
    # written at commit() with the ink.
    # A CHART IN A COLUMN IS DRAWN AT THE COLUMN'S WIDTH, so its text lands at the same size as a full-width
    # chart's rather than shrunk. For drawing only: the recorded spec stays as it was, so a redo into a wide
    # box is laid out wide again.
    spec_r = spec
    full = float(H._safe()[2] - H._safe()[0])
    if not spec.get("width") and not spec.get("page") and float(box["w"]) < 0.85 * full:
        spec_r = dict(spec, width=max(420, int(round(float(box["w"]) * CH.WIDTH / full))))
    try:
        CH.render(spec_r, png, scale=2.0, crisp=False)
    except Exception as ex:
        return {"error": "the chart would not render: %s: %s" % (type(ex).__name__, str(ex)[:120])}
    from PIL import Image as _Im
    with _Im.open(png) as _im:
        pw, ph = _im.size
        # A CHART FILLS ITS BOX'S WIDTH and its height follows: the page scrolls, and the places
        # after it are laid out again below where it actually landed (_reflow). The box's height
        # is the planner's guess, made before the chart existed, and fitted to it a tall chart
        # shrinks until it cannot be read. That came round one kind at a time -- a redone week
        # 1,195 wide instead of 1,410, four clipped posts a thin column down
        # the middle of the page, a 42-item checklist 472 px wide with its text 7 px
        # high. The rule stands: a chart is the full width of the
        # safe area, almost without exception.
        # ...AND NEVER MORE THAN ITS OWN SIZE. A chart laid out narrower than the width it was
        # drawn for -- one post card, half the chart -- keeps that width rather than being blown
        # up to the whole box (cards can easily be half width even with images).
        _lw = float(spec_r.get("width") or CH.WIDTH)
        s = min(float(box["w"]) / pw, float(box["w"]) / (2.0 * _lw))
        wu, hu = pw * s, ph * s                         # the picture's size in page units
        x0 = float(box["x0"]) + (float(box["w"]) - wu) / 2.0
        y0 = float(box["y0"])
        aw, ah = int(round(wu * 1.25)), int(round(hu * 1.25))   # ~1.1 device px per asset px
        asset = _im.convert("RGB")
        if pw > aw:
            asset = asset.resize((aw, ah), _Im.LANCZOS)
        apath = os.path.join(H.QUEUE, "_host_img_%s.png" % place.replace("/", "_"))
        asset.save(apath, "PNG", optimize=True)
    prev = [im for im in (JOB.images or []) if im["place"] == place]
    JOB.images = [im for im in (JOB.images or []) if im["place"] != place]
    # A picture ALREADY ON THE PAGE under the new one is the old chart being updated ("add Thursday to the
    # steps chart"): it goes when this one lands, so the page never carries both.
    replacing = []
    try:
        from paperdaemon.pipeline.page import images as IM
        nb = (x0, y0, x0 + wu, y0 + hu)
        for old in IM.items(JOB.doc, JOB.page):
            ob = old["box"]
            ix = max(0.0, min(nb[2], ob[2]) - max(nb[0], ob[0]))
            iy = max(0.0, min(nb[3], ob[3]) - max(nb[1], ob[1]))
            area = max(1.0, (ob[2] - ob[0]) * (ob[3] - ob[1]))
            if ix * iy / area > 0.4:
                replacing.append(tuple(ob))
    except Exception:
        replacing = []
    JOB.images.append({"place": place, "png": apath, "box": (x0, y0, x0 + wu, y0 + hu),
                          "type": ctype, "title": str(spec.get("title") or "")[:40],
                          "spec": H._as_recorded(spec),
                          "replaces": replacing})
    H._mark()
    JOB.ops.append("chart %r (%s) as a picture in %r" % (str(spec.get("title") or "")[:30],
                                                            ctype, place))
    out = dict({"ok": True, "picture": True, "seconds": 0,
                "box": {"x0": round(x0, 1), "y0": round(y0, 1), "x1": round(x0 + wu, 1),
                        "y1": round(y0 + hu, 1), "w": round(wu, 1), "h": round(hu, 1)},
                "note": "The chart is in the draft as a PICTURE -- the render itself, placed in "
                        "your place. render() and LOOK at it; commit() puts it on the page with "
                        "the ink. Calling chart again for the same place replaces it."},
               **H._did())
    if dropped:
        out["dropped_cards"] = dropped
        out["note"] = ("Drawn WITHOUT %d card(s) that did not scan or fit (see dropped_cards). "
                       % len(dropped)) + out["note"]
    if prev:
        out["replaced"] = True
    if replacing:
        out["replaces_pictures"] = len(replacing)
        out["note"] = ("It lies over %d picture(s) already on the page; they are removed when "
                       "this one is placed at commit(). " % len(replacing)) + out["note"]
    return out


def _as_shown(spec):
    """A picture's spec as the model is shown it, for a redo: without what _calendar_defaults fills
    in by itself. Shown the whole recorded month, the model typed back its latitude, longitude and
    page size and looped on them until the runaway guard cut it off 19 s later. Only the host's
    own values go: a place the model chose stays."""
    auto = {"holidays": H.HOME_HOLIDAYS, "place": H.HOME_PLACE, "lat": H.HOME_LAT, "lon": H.HOME_LON, "page": "tablet"}
    return dict((k, v) for k, v in (spec or {}).items() if not (k in auto and v == auto[k]))


def _calendar_defaults(spec):
    """Fill in what the model should never have to say: where the user is, which holidays, the page."""
    import datetime as _d
    today = _d.date.today()
    # A PLACE THE MODEL NAMED (the city a user gave when asked) is found here, its holidays with it; the
    # user's own place fills in otherwise
    named = str(spec.get("place") or "").strip()
    if named and named != H.HOME_PLACE and (spec.get("lat") is None or spec.get("lon") is None):
        hit = H._find_place(named)
        if hit:
            spec["lat"], spec["lon"] = hit["lat"], hit["lon"]
            if hit.get("holidays"):
                spec.setdefault("holidays", hit["holidays"])
    spec.setdefault("holidays", H.HOME_HOLIDAYS)
    if H.HOME_PLACE:
        spec.setdefault("place", H.HOME_PLACE)
    if (spec.get("lat") is None or spec.get("lon") is None) and H.HOME_LAT is not None:
        spec["lat"], spec["lon"] = H.HOME_LAT, H.HOME_LON
    if spec.get("type") == "calendar":
        spec.setdefault("page", "tablet")
        try:
            spec["year"] = int(spec.get("year") or today.year)
            spec["month"] = int(spec.get("month") or today.month)
        except (TypeError, ValueError):
            spec["year"], spec["month"] = today.year, today.month
        if not spec.get("title"):
            spec["title"] = _d.date(spec["year"], spec["month"], 1).strftime("%B %Y")
        key = "marks"
    else:
        key = "days"
        spec.pop("page", None)
    # the shapes a model actually emits: a day as a list, an event as a bare string, a card with
    # its lines under "lines" or as one string with newlines
    marks = spec.get(key)
    if isinstance(marks, list):
        marks = dict((str(i + 1), v) for i, v in enumerate(marks))
    if not isinstance(marks, dict):
        spec.pop(key, None)
        return
    fixed = {}
    for k, v in marks.items():
        if isinstance(v, list):
            v = {"events": v}
        elif isinstance(v, str):
            v = {"events": [{"text": v}]}
        if not isinstance(v, dict):
            continue
        evs = v.get("events")
        if evs is None and "text" in v and "card" not in v:
            evs = [v]
        v["events"] = [({"text": e} if isinstance(e, str) else e) for e in (evs or [])
                       if isinstance(e, (str, dict))]
        for e in v["events"]:
            if isinstance(e.get("text"), str):
                e["text"] = e["text"].strip()
            if e.get("kind") not in (None, "holiday", "national", "season", "birthday", "personal"):
                e["kind"] = "personal"
        card = v.get("card")
        if isinstance(card, dict):
            lines = card.get("text", card.get("lines"))
            if isinstance(lines, str):
                lines = [l.strip() for l in lines.replace("/", "\n").splitlines() if l.strip()]
            card = {"year": card.get("year"), "title": str(card.get("title") or "").split()[0:1] and
                    str(card.get("title")).split()[0] or "", "text": lines}
            v["card"] = card
        elif card is not None:
            v.pop("card", None)
        fixed[str(k).strip()] = v
    spec[key] = fixed


def _geocode(place):
    """A place name -> (lat, lon) from OpenStreetMap's Nominatim; None when it cannot be found."""
    key = " ".join(str(place).lower().split())
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    try:
        q = urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
        req = urllib.request.Request("https://nominatim.openstreetmap.org/search?" + q,
                                     headers={"User-Agent": "PaperDaemon/1.0 (reMarkable assistant)"})
        with H._net.urlopen(req, timeout=20) as r:
            rows = json.loads(r.read().decode("utf-8"))
        hit = (float(rows[0]["lat"]), float(rows[0]["lon"])) if rows else None
    except Exception:
        hit = None
    _GEO_CACHE[key] = hit
    return hit


def _find_place(name):
    """A place's {lat, lon, holidays?}: the city list first (offline, and it knows the holiday region), then
    the map's own search; None when neither knows it."""
    try:
        from paperdaemon import places
        got = places.search(name, limit=1)
        if got:
            return got[0]
    except Exception as ex:
        H._warn("the city list", ex)
    hit = H._geocode(name)
    return {"lat": hit[0], "lon": hit[1]} if hit else None


def _drop_card(spec, msg):
    """If a validation error is about one day's card, remove that card and say which. Else None."""
    import re as _re
    if "haiku" not in msg and "card" not in msg:
        return None
    m = _re.match(r"day (\S+?):", msg) or _re.match(r"days\[(.+?)\]:", msg)
    if not m:
        return None
    key = m.group(1).strip("'\"")
    table = spec.get("marks") if spec.get("type") == "calendar" else spec.get("days")
    if not isinstance(table, dict):
        return None
    for k, v in table.items():
        if str(k).strip("'\"").lower() == key.lower() and isinstance(v, dict) and "card" in v:
            v.pop("card")
            return key
    return None


def t_history(month):
    """Wikipedia's on-this-day facts for one month, compact: what the cards are written from."""
    try:
        mo = int(month)
    except (TypeError, ValueError):
        return {"error": "month must be a number, 1-12"}
    if not 1 <= mo <= 12:
        return {"error": "month must be 1-12"}
    # once per month per job: each answer is a couple of thousand tokens of context the model already has
    seen = JOB.history_months
    if mo in seen:
        return {"ok": True, "note": "You already have month %d's facts above -- use those." % mo}
    from paperdaemon.pipeline.charts import history as _H
    got = _H.month(mo)
    days = {}
    for d in sorted(got):
        rows = []
        for y, t in got[d][:3]:
            t = " ".join(str(t).split())
            rows.append("%s %s" % (y, t[:84] + (".." if len(t) > 84 else "")))
        if rows:
            days[str(d)] = rows
    if not days:
        return {"error": "Wikipedia did not answer; draw the calendar without cards"}
    return {"month": mo, "days": days,
            "note": "A card: {year, title (ONE word), text: [5, 7, 5 syllables, each line under 31 "
                    "characters]} that NAMES the event. Only for days worth it."}


def _spec_strings(v, out=None):
    """Every short string in a chart spec -- its labels, series names, events."""
    out = [] if out is None else out
    if isinstance(v, str):
        if 0 < len(v) <= 40:
            out.append(v)
    elif isinstance(v, dict):
        for k, x in v.items():
            if k not in ("type", "color", "colors", "palette", "theme"):
                _spec_strings(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v[:200]:
            _spec_strings(x, out)
    return out


def _calendar_facts(cur):
    """ON THIS DAY, for the dates a calendar will show, fetched by the host and handed over.

    Asked for 'on this day' facts, the model wrote cards from memory -- Pearl Harbor on a
    September Thursday, Woodstock on a Sunday -- because history(month) was a call it had to think
    to make. A month went the same way: its step had no history() to call, so the model planned a
    web search of its own and gave a ship's launch the wrong year. The host knows the dates, so it
    fetches their facts itself and the model only chooses and writes the haiku: a week's seven days,
    four facts each; a month's every day, two each."""
    spec = cur.get("base_spec") or {}
    asked = ST.calendar_what(cur.get("what")) or ("week",)        # the step's what: YYYY-MM or week
    is_week = spec.get("type") == "week" or (not spec and asked[0] == "week")
    try:
        import calendar as _cal
        import datetime as _dt
        from paperdaemon.pipeline.charts import history as _H
        today = _dt.date.today()
        if is_week:
            start = _dt.date.fromisoformat(str(spec["start"])) if spec.get("start") else today
            dates, label = [start + _dt.timedelta(days=i) for i in range(7)], "this week's dates"
            per, cut = 4, 90
            key = lambda d: d.strftime("%a")
        else:
            mo = int(spec.get("month") or (asked[2] if asked[0] == "month" else today.month))
            yr = int(spec.get("year") or (asked[1] if asked[0] == "month" else today.year))
            dates = [_dt.date(yr, mo, n) for n in range(1, _cal.monthrange(yr, mo)[1] + 1)]
            label = dates[0].strftime("%B")
            per, cut = 3, 80
            key = lambda d: str(d.day)
        by_month, rows = {}, []
        for d in dates:
            if d.month not in by_month:
                by_month[d.month] = _H.month(d.month)
            got = by_month[d.month].get(d.day) or []
            # SPREAD OVER THE DAY'S HISTORY, not its first few: Wikipedia lists a day newest first,
            # and the first ones handed the model 2012-2022 shootings and collapses to choose "firsts
            # worth a smile" from
            idx = sorted(set(int(round(i * (len(got) - 1) / float(max(1, per - 1)))) for i in range(per))) \
                if len(got) > per else range(len(got))
            facts = [(got[i][0], " ".join(str(got[i][1]).split())) for i in idx]
            if facts:
                rows.append("  %s (\"%s\"): %s" % (d.strftime("%a %d %b"), key(d),
                                                   " | ".join("%s %s" % (y, t[:cut]) for y, t in facts)))
        if not rows:
            return ""
        return ("ON THIS DAY for %s (Wikipedia). A card goes on ITS OWN day, keyed as shown, and must be "
                "one of these with its year as given -- never a killing or a disaster; pick discoveries, "
                "firsts, things worth a smile:\n" % label + "\n".join(rows))
    except Exception as ex:
        H._warn("fetching on-this-day facts", ex)
        return ""


def _chart_figures():
    """The numbers of any chart this job made, worked out by the host, for words written about it.

    A note beside a steps chart said Tuesday was "nearly 2,300 more than the average"; the average of
    8,200, 10,400, 6,100 and 9,800 is 8,625, so it was 1,775. Arithmetic is
    what a language model does worst and a host does exactly, so the host does it."""
    out = []
    for im in JOB.images or []:
        spec = im.get("spec") or {}
        cats = spec.get("categories") or []
        for s in spec.get("series") or []:
            try:
                vals = [float(v) for v in s.get("values") or []]
            except (TypeError, ValueError):
                continue
            if not vals or len(vals) != len(cats):
                continue
            tot, avg = sum(vals), sum(vals) / len(vals)
            hi, lo = max(range(len(vals)), key=vals.__getitem__), min(range(len(vals)), key=vals.__getitem__)
            def f(v):
                if abs(v) >= 100 or float(v).is_integer():
                    return "{:,.0f}".format(v)
                return ("%.2f" % v).rstrip("0").rstrip(".")
            out.append("%s%s: total %s; average %s; highest %s %s (%s above the average); lowest %s %s "
                       "(%s below); %s" % (
                           spec.get("title") or "the chart", (" / " + s["name"]) if s.get("name") else "",
                           f(tot), f(avg), cats[hi], f(vals[hi]), f(vals[hi] - avg), cats[lo], f(vals[lo]),
                           f(avg - vals[lo]),
                           ", ".join("%s %s (%.0f%%)" % (c, f(v), 100.0 * v / tot if tot else 0)
                                     for c, v in zip(cats, vals))))
    if not out:
        return ""
    return ("THE CHART'S FIGURES, worked out by the host -- use these, not your own arithmetic:\n  "
            + "\n  ".join(out))


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("chart", "The spec for a chart or calendar step; the host places it. Numbers: {type: bar|hbar|line|"
  "pie|donut|area|scatter, title, x_label, y_label, categories: [...], series: [{name, values: "
  "[...]}]} -- up to 4 series; hbar and pie take one; categories keep your order. A month: {type: "
  "'calendar', year, month, marks?: {'14': {events: [{text, at?: 'HH:MM'}], card?: {year, title, "
  "text: [l1, l2, l3]}}}}. The week from today: {type: 'week', days?: {'Thu': {events, card}}}. The "
  "forecast, sunrise and sunset, holidays and observances are fetched and drawn for you. "
  + H._CAL_PLACE_HINT +
  "A card is an on-this-day HAIKU (5-7-5, each line under 31 characters) naming the event; "
  "the facts for its dates come with the calendar step; three to six cards a month. "
  "Never draw a chart, a calendar or a map by hand.",
  # type FIRST, then anything, in any order (see the step schema in plan: a declared key cannot follow an
  # undeclared one, and the server respells a key written out of order)
  {"spec": {"type": "object", "properties": {"type": {"type": "string"}}, "required": ["type"],
            "additionalProperties": True},
   "place": {"type": "string", "optional": True}}, t_chart),
 ("history", "Wikipedia's on-this-day facts for one month, a few per day. A calendar or week STEP "
  "already comes with the facts for its dates, so it never needs this and it is never a plan step; "
  "it is for a chart step that wants them.",
  {"month": "number"}, t_history),
]
