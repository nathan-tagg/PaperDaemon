"""The job in hand is a typed object in a context variable, never module state: JOB is a proxy that holds
nothing, and two contexts (two threads) each see their own job."""
import threading

import paperdaemon.pipeline.host as H
from paperdaemon.pipeline.host import job as J


def test_no_module_level_job_state():
    assert type(H.JOB) is J._Proxy and J._Proxy.__slots__ == ()
    for name, value in vars(H).items():
        assert not isinstance(value, J.Job), name
        if isinstance(value, dict):
            assert not {"doc", "page", "draw", "ops"} <= set(value), name      # no job dict left anywhere


def test_each_context_has_its_own_job():
    J.begin(doc="mine", page=3)
    seen = {}

    def other():
        J.begin(doc="theirs", page=9)
        seen["other"] = (H.JOB.doc, H.JOB.page)
    t = threading.Thread(target=other)
    t.start()
    t.join()
    assert seen["other"] == ("theirs", 9) and (H.JOB.doc, H.JOB.page) == ("mine", 3)


def test_a_job_starts_empty_and_refuses_unknown_fields():
    J.begin(doc="d")
    H.JOB.tags.append("x")
    assert H.JOB.take("tags") == ["x"] and H.JOB.tags == [] and H.JOB.frame is J.UNSET
    try:
        H.JOB.no_such_field = 1
    except AttributeError:
        pass
    else:
        raise AssertionError("an unknown field was accepted")
    J.begin()
    assert H.JOB.doc is None and H.JOB.scratch["searches"] == []
