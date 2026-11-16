"""Public native compatibility fixtures; no spline conversion or integration API."""
import sqlite3
from fractions import Fraction as F
from rational import dumps
from vendor import poly2, spline1
from samples import open_sample

def cases():
    result = []
    for sign, label in [(1, "shared"), (-1, "opposed")]:
        loading = [2, 0, 0, 0, 2*sign, 0, 0, 0]
        expected = {"left": (F(9), F(4)), "right": (F(9), F(4)),
                    "whole": (F(18), F(16 if sign == 1 else 0)),
                    "empty": (F(0), F(0))}
        for kind in ["cov", "factor"]:
            if kind == "cov":
                uncertainty = {"kind": kind,
                    "matrix": [[str(a*b) for b in loading] for a in loading]}
            else:
                uncertainty = {"kind": kind,
                    "loadings": [[str(a)] for a in loading],
                    "latent_cov": [["1"]]}
            payload = {"edges": ["0", "1", "2"],
                       "mean": ["9", "0", "0", "0", "9", "0", "0", "0"],
                       "uncertainty": uncertainty}
            result.append((label+"-"+kind, payload, expected))
    return result

def verify():
    # Old SDK is an independent oracle for the public shared-offset example.
    db = open_sample()
    raw = db.execute("SELECT payload FROM curves1 WHERE id='offset'").fetchone()[0]
    curve = spline1.load(raw)
    assert spline1.integral(curve, 0, 1) == (3, 1)
    assert spline1.integral(curve, 1, 2) == (3, 1)
    assert spline1.integral(curve, 0, 2) == (6, 4)
    db.close()
    db = sqlite3.connect(":memory:")
    with db:
        poly2.initialize(db)
        for name, payload, expected in cases():
            poly2.replace(db, name, payload)
            decoded = poly2.read(db, name)
            assert [poly2.value(decoded, x) for x in [0, F(1,2), 1, F(3,2), 2]] == [9]*5
            assert db.execute("SELECT payload FROM curves2 WHERE id=?", (name,)).fetchone()[0] == dumps(payload)
            u = decoded["uncertainty"]
            # Only fixture constants are checked here, not arbitrary integration.
            if u["kind"] == "cov":
                matrix = u["matrix"]
                joint = (matrix[0][0], matrix[0][4], matrix[4][4])
            else:
                a, c = u["loadings"], u["latent_cov"][0][0]
                joint = (a[0][0]**2*c, a[0][0]*a[4][0]*c, a[4][0]**2*c)
            cross = F(4 if name.startswith("shared") else -4)
            assert joint == (4, cross, 4)
            assert expected["whole"][1] == joint[0]+2*joint[1]+joint[2]
            assert expected["left"] == expected["right"] == (9, 4)
    db.close()
    print("NATIVE_FIXTURES_OK shared=(18,16) opposed=(18,0) halves=(9,4)")

if __name__ == "__main__":
    verify()
    for name, payload, expected in cases():
        print(name, "expected:", expected)
