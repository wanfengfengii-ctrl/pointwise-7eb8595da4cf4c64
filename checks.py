from fractions import Fraction as F
from samples import open_sample
from archive import Store, atomic_upgrade
from analysis import Analysis
from vendor import spline1, poly2

def baseline():
    from native_cases import verify
    verify()
    db = open_sample()
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
    assert a.run("whole") == (6, 4)
    # Target SDK smoke test; no spline transformation or analysis adapter.
    with db:
        poly2.initialize(db)
        native = {"edges": ["0","2"], "mean": ["9","0","0","0"],
                  "uncertainty": {"kind": "cov",
                      "matrix": [["1","0","0","0"],["0"]*4,["0"]*4,["0"]*4]}}
        poly2.replace(db, "native", native)
    assert poly2.value(poly2.read(db, "native"), 2) == 9
    print("BASELINE_OK whole=(6,4) jump-total=(8,1/2) rollback=preserved")
    db.close()

def demo():
    db = open_sample()
    print("legacy curves:", db.execute("SELECT count(*) FROM curves1").fetchone()[0])
    for row in db.execute("SELECT name FROM jobs1 ORDER BY name"):
        print(row[0], Analysis(db).run(row[0]))
    print("jump at 999/1000,1,2:", [Store(db).value("jump", x) for x in [F(999,1000),1,2]])
    db.close()

if __name__ == "__main__":
    import sys
    {"baseline": baseline, "demo": demo}[sys.argv[1]]()
