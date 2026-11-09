"""A timeline takes dates: the type's description says "date or year", and a project timeline asked for by dates was
refused twice ("could not convert string to float: '2026-01-05'") and drawn empty the third time."""
import datetime

from paperdaemon.pipeline import charts as C


def test_events_stand_by_their_dates_and_their_ticks_say_the_day():
    at, tick = C._when({"date": "2026-01-05", "text": "Kickoff"})
    assert at == float(datetime.date(2026, 1, 5).toordinal()) and tick == "Jan 5"
    at2, tick2 = C._when({"date": "February 2, 2026", "text": "Design review"})
    assert at2 == float(datetime.date(2026, 2, 2).toordinal()) and tick2 == "Feb 2"
    at3, tick3 = C._when({"date": "10 Mar", "text": "Build"})
    assert at3 == float(datetime.date(datetime.date.today().year, 3, 10).toordinal()) and tick3 == "Mar 10"
    assert C._when({"year": 1969, "text": "Moon"}) == (float(datetime.date(1969, 1, 1).toordinal()), "1969")
    assert C._when({"at": 3, "text": "third"}) == (3.0, "3")
    assert C._when({"date": "2026-04", "text": "beta"})[1] == "Apr 2026"


def test_a_dated_timeline_renders(tmp_path):
    spec = {"type": "timeline", "title": "Project", "events": [
        {"date": "2026-01-05", "text": "Kickoff"}, {"date": "2026-02-02", "text": "Design review"},
        {"date": "2026-03-10", "text": "Build starts"}, {"date": "2026-04-14", "text": "Beta"},
        {"date": "2026-05-01", "text": "Launch"}]}
    out = str(tmp_path / "t.png")
    C.render(spec, png_path=out)
    from PIL import Image
    with Image.open(out) as im:
        assert im.width > 500 and im.height > 100


def test_an_event_with_no_date_is_refused_by_name():
    try:
        C._when({"text": "nothing to place it by"})
        raise AssertionError("placed an event with no date")
    except ValueError as ex:
        assert "needs" in str(ex)
