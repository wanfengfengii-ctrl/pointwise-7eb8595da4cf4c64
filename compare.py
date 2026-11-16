"""Independent semantic comparison of the migration against the legacy SDK.

The legacy SDK is the oracle for point values and integral weights.  Expected
target coefficients are re-derived here from ``spline1.value`` samples and a
local Vandermonde solve, so nothing in convert.py is trusted for the check.
No business result is rebuilt from the audit tables.
"""
import json
from fractions import Fraction as F
from rational import dot
from samples import open_sample
from vendor import spline1, poly2
from convert import integrate
from migration import upgrade

NODES = (F(1, 5), F(2, 5), F(3, 5), F(4, 5))


def _inverse(matrix):
    n = len(matrix)
    aug = [list(row) + [F(int(i == j)) for j in range(n)]
           for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = next(r for r in range(col, n) if aug[r][col])
        aug[col], aug[pivot] = aug[pivot], aug[col]
        lead = aug[col][col]
        aug[col] = [v / lead for v in aug[col]]
        for row in range(n):
            if row != col and aug[row][col]:
                f = aug[row][col]
                aug[row] = [a - f * b for a, b in zip(aug[row], aug[col])]
    return [row[n:] for row in aug]


_VINV = _inverse([[z ** j for j in range(4)] for z in NODES])


def _independent_map(raw):
    """Expected (edges, coefficient rows) from SDK point values only.

    Each unit legacy mean isolates one column of the linear conversion map,
    and the map is shared by the mean and the covariance transport.
    """
    t, m, _ = spline1.load(raw)
    n = len(m)
    zero = [[F(0)] * n for _ in range(n)]
    edges = sorted(set(t[3:n + 1]))
    rows = []
    for a, b in zip(edges, edges[1:]):
        h = b - a
        columns = []
        for k in range(n):
            unit = [F(int(k == i)) for i in range(n)]
            columns.append([spline1.value((t, unit, zero), a + h * z)
                            for z in NODES])
        for j in range(4):
            rows.append([sum(_VINV[j][s] * columns[k][s] for s in range(4))
                         for k in range(n)])
    return edges, rows


def _legacy_rows(db):
    return dict(db.execute("SELECT id,payload FROM curves1"))


def _target_rows(db):
    return dict(db.execute("SELECT id,payload FROM curves2"))


def _check_target_shape(payload):
    assert set(payload) == {"edges", "mean", "uncertainty"}
    edges = payload["edges"]
    assert len(edges) >= 2 and all(a < b for a, b in zip(edges, edges[1:]))
    q = 4 * (len(edges) - 1)
    assert len(payload["mean"]) == q
    u = payload["uncertainty"]
    if u["kind"] == "cov":
        assert len(u["matrix"]) == q and all(len(r) == q for r in u["matrix"])
        assert all(u["matrix"][i][j] == u["matrix"][j][i]
                   for i in range(q) for j in range(q))
    else:
        assert len(u["loadings"]) == q
    return q


def _check_persisted(db, curve_id):
    """Persisted target must equal the oracle's exact conversion of the audit row."""
    raw = _legacy_rows(db)[curve_id]
    t, m, c = spline1.load(raw)
    edges, rows = _independent_map(raw)
    n = len(m)
    stored = json.loads(_target_rows(db)[curve_id])
    assert [F(x) for x in stored["edges"]] == edges
    assert [F(x) for x in stored["mean"]] == [dot(row, m) for row in rows]
    u = stored["uncertainty"]
    assert u["kind"] in {"cov", "factor"}
    # Oracle-integrated variance at full domain, independent of the stored form.
    payload = poly2.read(db, curve_id)
    _, var_full = integrate(payload, edges[0], edges[-1])
    legacy_var = spline1.integral((t, m, c), edges[0], edges[-1])[1]
    assert var_full == legacy_var
    if u["kind"] == "cov":
        matrix = [[F(x) for x in row] for row in u["matrix"]]
        for i in range(len(rows)):
            for j in range(len(rows)):
                expect = sum(rows[i][a] * c[a][b] * rows[j][b]
                             for a in range(n) for b in range(n))
                assert matrix[i][j] == expect, (curve_id, i, j)


def _boundary_points(raw):
    t, m, _ = spline1.load(raw)
    lo, hi = t[3], t[len(m)]
    points = {lo, hi, F(lo + hi, 2)}
    for knot in t[3:len(m) + 1]:
        points.add(knot)
        for delta in (F(1, 1000), F(1, 97)):
            for x in (knot - delta, knot + delta):
                if lo <= x <= hi:
                    points.add(x)
    return sorted(points)


def _intervals(raw):
    t, m, _ = spline1.load(raw)
    lo, hi = t[3], t[len(m)]
    edges = sorted(set(t[3:len(m) + 1]))
    mid = F(lo + hi, 2)
    result = [(lo, hi), (lo, lo), (hi, hi), (mid, mid), (lo, mid), (mid, hi)]
    result += [(a, b) for a, b in zip(edges, edges[1:])]
    if len(edges) >= 3:
        result.append((edges[0], edges[-1]))
    return result


def compare_after_upgrade():
    """Upgrade a fresh library and compare all curves against the legacy SDK."""
    db = open_sample()
    from analysis import Analysis
    jobs = Analysis(db)  # created before the switch, reused afterwards
    names, before = [], {}
    for curve_id, raw in _legacy_rows(db).items():
        t, m, _ = spline1.load(raw)
        lo, hi = t[3], t[len(m)]
        mid = F(lo + hi, 2)
        for tag in ("whole", "empty", "half"):
            a, b = {"whole": (lo, hi), "empty": (mid, mid),
                    "half": (lo, mid)}[tag]
            name = "gen-" + curve_id + "-" + tag
            jobs.save(name, curve_id, a, b)
            names.append(name)
    for name in names:
        before[name] = jobs.run(name)
    audit = _legacy_rows(db)
    audit_jobs = db.execute("SELECT name,curve_id,lo,hi FROM jobs1 ORDER BY name").fetchall()

    assert upgrade(db) is True
    assert upgrade(db) is False  # idempotent
    assert db.execute("SELECT version FROM meta").fetchone()[0] == 2

    # Existing Analysis object immediately sees target curves and joins.
    for name in names:
        assert jobs.run(name) == before[name], name

    # Points: every knot, both sides, the right end, interior and domain edges.
    for curve_id, raw in _legacy_rows(db).items():
        curve = spline1.load(raw)
        edges, _ = _independent_map(raw)
        payload = poly2.read(db, curve_id)
        for x in _boundary_points(raw):
            assert poly2.value(payload, x) == spline1.value(curve, x), (curve_id, x)
        # Integrals: across segments, singletons, empty, half intervals.
        for a, b in _intervals(raw):
            assert integrate(payload, a, b) == spline1.integral(curve, a, b), \
                (curve_id, a, b)
        # Empty interval is exactly (0, 0) even at a jump.
        assert integrate(payload, edges[0], edges[0]) == (0, 0)

    # Persisted target payloads and untouched audit text: compare the audit
    # rows with the copies captured before the switch.
    assert _legacy_rows(db) == audit
    assert db.execute("SELECT name,curve_id,lo,hi FROM jobs1 ORDER BY name").fetchall() == audit_jobs
    assert db.execute("SELECT version FROM meta").fetchone()[0] == 2
    for curve_id in _legacy_rows(db):
        _check_persisted(db, curve_id)
        _check_target_shape(poly2.read(db, curve_id))
    db.close()


if __name__ == "__main__":
    compare_after_upgrade()
    print("SEMANTIC_COMPARE_OK points+integrals+knots+payload+audit")
