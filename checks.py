from fractions import Fraction as F
from samples import open_sample
from archive import Store, atomic_upgrade
from analysis import Analysis
from vendor import spline1, poly2
from migration import upgrade


def _legacy_rows(db):
    return dict(db.execute("SELECT id,payload FROM curves1"))


def _assert_legacy_public(db):
    """Original baseline assertions, valid for both v1 and v2 via the same API."""
    s, a = Store(db), Analysis(db)
    assert [s.value("offset", x) for x in [0, F(1,3), 1, 2]] == [3]*4
    assert a.run("whole") == (6, 4)
    assert a.run("empty") == (0, 0)
    assert s.value("jump", F(999,1000)) == 1
    assert s.value("jump", 1) == 7
    assert s.value("jump", 2) == 7
    assert a.run("jump-total") == (8, F(1,2))
    for mult in range(1, 5):
        raw = db.execute("SELECT payload FROM curves1 WHERE id=?", ("m"+str(mult),)).fetchone()[0]
        curve = spline1.load(raw)
        for x in [0, F(1,3), 1, F(5,3), 2]:
            assert sum(spline1.basis(curve, x)) == 1
        assert a.run("m"+str(mult))[1] >= 0


def baseline():
    from native_cases import verify
    verify()
    db = open_sample()
    _assert_legacy_public(db)
    legacy_before = _legacy_rows(db)
    jobs_before = db.execute("SELECT name,curve_id,lo,hi FROM jobs1 ORDER BY name").fetchall()
    # Existing transaction facility still rolls back a populated target.
    def populate(c):
        poly2.initialize(c)
        c.execute("INSERT INTO jobs2 VALUES('probe','offset','0','2')")
    def fail():
        raise RuntimeError("injected")
    try:
        atomic_upgrade(db, populate, fail)
    except RuntimeError as exc:
        assert str(exc) == "injected"
    else:
        raise AssertionError("fault not propagated")
    assert db.execute("SELECT version FROM meta").fetchone()[0] == 1
    assert db.execute("SELECT name FROM sqlite_master WHERE name='jobs2'").fetchone() is None
    assert Analysis(db).run("whole") == (6, 4)
    # Target SDK smoke test; no spline transformation or analysis adapter.
    with db:
        poly2.initialize(db)
        native = {"edges": ["0","2"], "mean": ["9","0","0","0"],
                  "uncertainty": {"kind": "cov",
                      "matrix": [["1","0","0","0"],["0"]*4,["0"]*4,["0"]*4]}}
        poly2.replace(db, "native", native)
    assert poly2.value(poly2.read(db, "native"), 2) == 9
    print("BASELINE_OK whole=(6,4) jump-total=(8,1/2) rollback=preserved")
    # Same public API and assertions again after the real upgrade.
    assert upgrade(db) is True
    _assert_legacy_public(db)
    assert upgrade(db) is False
    assert _legacy_rows(db) == legacy_before
    assert db.execute("SELECT name,curve_id,lo,hi FROM jobs1 ORDER BY name").fetchall() == jobs_before
    assert db.execute("SELECT name,curve_id,lo,hi FROM jobs2 ORDER BY name").fetchall() == jobs_before
    print("BASELINE_UPGRADED_OK same assertions pass through v2")
    db.close()


import contextlib

@contextlib.contextmanager
def _without_sdk1():
    """Make every legacy SDK entry point raise, proving the v2 path is independent."""
    def boom(*args, **kwargs):
        raise AssertionError("legacy SDK used after upgrade")
    saved = {}
    for name in ("load", "basis", "weights", "value", "integral"):
        saved[name] = getattr(spline1, name)
        setattr(spline1, name, boom)
    try:
        yield
    finally:
        for name, original in saved.items():
            setattr(spline1, name, original)


def _native_replace(db, existing):
    """Restore the saved existing object's view and run both native representations."""
    from native_cases import cases
    for name, payload, expected in cases():
        # Reuse the existing curve ID; old task endpoints stay in the new domain.
        poly2.replace(db, "offset", payload)
        for tag, interval in [("left", ("0", "1")), ("right", ("1", "2")),
                              ("whole", ("0", "2")), ("empty", ("1", "1"))]:
            job = "native-" + name + "-" + tag
            existing.save(job, "offset", *interval)
            assert existing.run(job) == expected[tag], (name, tag, existing.run(job))
        assert all(poly2.value(poly2.read(db, "offset"), x) == 9
                   for x in [0, F(1,2), 1, F(3,2), 2])


def _verify_upgrade():
    from compare import compare_after_upgrade
    compare_after_upgrade()

    db = open_sample()
    existing = Analysis(db)          # created before the switch, reused after
    saved = {name: existing.run(name)
             for (name,) in db.execute("SELECT name FROM jobs1 ORDER BY name")}
    # A curve written through the old interface before upgrading must migrate too.
    Store(db).replace("late", {"knots": ["0"]*4+["1","1"]+["2"]*4,
                               "mean": ["1","2","2","1","-1","3"],
                               "cov": [[str(int(i == j)) for j in range(6)]
                                       for i in range(6)]})
    existing.save("late", "late", F(1, 4), F(7, 4))
    expected_late = spline1.integral(
        spline1.load(db.execute("SELECT payload FROM curves1 WHERE id='late'").fetchone()[0]),
        F(1, 4), F(7, 4))
    assert existing.run("late") == expected_late

    # Inject a failure after target writes but before the version commit.
    def fail():
        raise RuntimeError("pre-commit fault")
    legacy_with_late = _legacy_rows(db)
    try:
        upgrade(db, fail)
    except RuntimeError as exc:
        assert str(exc) == "pre-commit fault"
    else:
        raise AssertionError("fault not propagated")
    assert db.execute("SELECT version FROM meta").fetchone()[0] == 1
    for table in ("curves2", "jobs2"):
        assert db.execute("SELECT name FROM sqlite_master WHERE name=?", (table,)).fetchone() is None
    assert _legacy_rows(db) == legacy_with_late
    assert existing.run("whole") == saved["whole"]
    assert existing.run("late") == expected_late

    # Retry succeeds, and repeating the upgrade is a no-op.
    assert upgrade(db) is True
    assert upgrade(db) is False
    assert _legacy_rows(db) == legacy_with_late
    assert db.execute("SELECT name,curve_id,lo,hi FROM jobs2 ORDER BY name").fetchall() \
        == db.execute("SELECT name,curve_id,lo,hi FROM jobs1 ORDER BY name").fetchall()
    for name, value in saved.items():
        assert existing.run(name) == value, name
    assert existing.run("late") == expected_late

    # Old write interface keeps working after the switch, via the adapter.
    Store(db).replace("offset", {"knots": ["0","0","0","0","1","2","2","2","2"],
                                 "mean": ["3"]*5, "cov": [["1"]*5 for _ in range(5)]})
    assert existing.run("whole") == (6, 4)

    # Native replacement through the already-created Analysis object.
    _native_replace(db, existing)

    # With SDK1 disabled, all saved analyses and the native curves still work.
    targets = {name: existing.run(name)
               for (name,) in db.execute("SELECT name FROM jobs2 ORDER BY name")}
    with _without_sdk1():
        for name, value in targets.items():
            assert existing.run(name) == value, name
        _native_replace(db, existing)
        assert Store(db).value("offset", 1) == 9
        # Every job bound to the reused ID now sees the last native curve.
        assert existing.run("native-shared-cov-whole") == (18, 0)
        assert existing.run("whole") == (18, 0)
        assert existing.run("empty") == (0, 0)
    print("UPGRADE_OK real upgrade, native cov/factor replacement, rollback+retry, sdk1-free reads")
    db.close()


def demo():
    db = open_sample()
    a = Analysis(db)
    print("legacy curves:", db.execute("SELECT count(*) FROM curves1").fetchone()[0])
    for row in db.execute("SELECT name FROM jobs1 ORDER BY name"):
        print("before", row[0], a.run(row[0]))
    print("jump at 999/1000,1,2:", [Store(db).value("jump", x) for x in [F(999,1000),1,2]])
    # Fault before commit: the legacy library survives intact and upgrades on retry.
    def fail_once():
        raise RuntimeError("injected before commit")
    try:
        upgrade(db, fail_once)
    except RuntimeError:
        pass
    print("after injected fault: version",
          db.execute("SELECT version FROM meta").fetchone()[0],
          "curves2", db.execute("SELECT count(*) FROM sqlite_master "
                                "WHERE name LIKE '%2'").fetchone()[0])
    assert upgrade(db) is True
    assert upgrade(db) is False
    print("upgraded: version", db.execute("SELECT version FROM meta").fetchone()[0],
          "curves2", db.execute("SELECT count(*) FROM curves2").fetchone()[0],
          "jobs2", db.execute("SELECT count(*) FROM jobs2").fetchone()[0])
    for row in db.execute("SELECT name FROM jobs2 ORDER BY name"):
        print("after", row[0], a.run(row[0]))
    print("jump at 999/1000,1,2:", [Store(db).value("jump", x) for x in [F(999,1000),1,2]])
    # Two native representations replace curve "offset" through the same Analysis.
    from native_cases import cases
    for name, payload, expected in cases():
        poly2.replace(db, "offset", payload)
        a.save(name, "offset", 0, 2)
        print("native", name, "whole:", a.run(name), "expected:", expected["whole"])
    db.close()


if __name__ == "__main__":
    import sys
    {"baseline": baseline, "demo": demo, "verify": _verify_upgrade}[sys.argv[1]]()
