"""Exact legacy-spline to poly2 conversion and target-side integration.

No legacy SDK calls are made here: the B-spline evaluation used to derive the
target coefficients is implemented locally, and target integration works on
decoded poly2 payloads only.
"""
import json
from fractions import Fraction as F
from rational import dot, quadratic

# Four interior points of the open Newton-Cotes rule, normalised to a segment.
NODES = (F(1, 5), F(2, 5), F(3, 5), F(4, 5))
# Vandermonde matrix for a cubic in z at those nodes, and its inverse.
_V = [[z ** j for j in range(4)] for z in NODES]


def _invert(matrix):
    n = len(matrix)
    aug = [list(row) + [F(int(i == j)) for j in range(n)]
           for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = next((r for r in range(col, n) if aug[r][col]), None)
        if pivot is None:
            raise ValueError("singular matrix")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        lead = aug[col][col]
        aug[col] = [value / lead for value in aug[col]]
        for row in range(n):
            if row != col and aug[row][col]:
                factor = aug[row][col]
                aug[row] = [a - factor * b for a, b in zip(aug[row], aug[col])]
    return [row[n:] for row in aug]


_VINV = _invert(_V)


def parse_legacy(raw):
    """Validate and decode a legacy payload, matching the legacy SDK's rules.

    ``raw`` may be the stored JSON text or an already decoded payload dict.
    """
    obj = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
    if set(obj) != {"knots", "mean", "cov"}:
        raise ValueError("legacy fields")
    t = list(map(F, obj["knots"]))
    m = list(map(F, obj["mean"]))
    c = [list(map(F, row)) for row in obj["cov"]]
    n = len(m)
    if not 4 <= n <= 8 or len(t) != n + 4:
        raise ValueError("legacy dimensions")
    if t != sorted(t) or not t[3] < t[n]:
        raise ValueError("legacy domain")
    if t[:4] != [t[3]] * 4 or t[n:] != [t[n]] * 4:
        raise ValueError("not clamped")
    if t.count(t[3]) != 4 or t.count(t[n]) != 4:
        raise ValueError("endpoint multiplicity")
    if any(t.count(x) > 4 for x in t[4:n]):
        raise ValueError("internal multiplicity")
    if len(c) != n or any(len(row) != n for row in c):
        raise ValueError("cov dimensions")
    if any(c[i][j] != c[j][i] for i in range(n) for j in range(n)):
        raise ValueError("cov symmetry")
    return t, m, c


def _basis(t, n, x):
    """Local clamped cubic B-spline basis; right-hand segment at internal knots."""
    final_span = max(i for i in range(len(t) - 1) if t[i] < t[i + 1])

    def b(i, degree):
        if degree == 0:
            if x == t[n]:
                return F(int(i == final_span))
            return F(int(t[i] <= x < t[i + 1]))
        left = right = F(0)
        if t[i + degree] != t[i]:
            left = (x - t[i]) / (t[i + degree] - t[i]) * b(i, degree - 1)
        if t[i + degree + 1] != t[i + 1]:
            right = (t[i + degree + 1] - x) / (t[i + degree + 1] - t[i + 1]) * b(i + 1, degree - 1)
        return left + right

    return [b(i, 3) for i in range(n)]


def segment_edges(t, n):
    """Strictly increasing boundaries of the non-empty polynomial segments."""
    return sorted(set(t[3:n + 1]))


def conversion_map(raw):
    """Return the segment edges and the linear map from legacy B-spline
    coefficients to flat target power coefficients.

    Each positive-length segment is sampled at four interior nodes, where the
    legacy spline is a cubic in the local variable, and the interpolating
    power-basis coefficients are recovered through the inverse Vandermonde
    matrix.
    """
    t, m, _ = parse_legacy(raw)
    n = len(m)
    edges = segment_edges(t, n)
    rows = []
    for a, b in zip(edges, edges[1:]):
        h = b - a
        sampled = [_basis(t, n, a + h * z) for z in NODES]
        for j in range(4):
            rows.append([sum(_VINV[j][s] * sampled[s][i] for s in range(4))
                         for i in range(n)])
    return edges, rows


def convert_legacy(raw):
    """Return a target payload with full joint polynomial covariance.

    The same linear map transports the legacy coefficient covariance exactly,
    keeping all cross-segment correlations.
    """
    _, m, c = parse_legacy(raw)
    n = len(m)
    edges, rows = conversion_map(raw)
    mean = [dot(row, m) for row in rows]
    q = len(rows)
    matrix = [[sum(rows[i][u] * c[u][v] * rows[j][v]
                   for u in range(n) for v in range(n))
               for j in range(q)] for i in range(q)]
    return {"edges": edges, "mean": mean,
            "uncertainty": {"kind": "cov", "matrix": matrix}}


def check_interval(payload, lo, hi):
    lo, hi = F(lo), F(hi)
    edges = payload["edges"]
    if not edges[0] <= lo <= hi <= edges[-1]:
        raise ValueError("bad interval")
    return lo, hi


def integration_weights(payload, lo, hi):
    """Exact coefficients of the interval integral in the target basis."""
    lo, hi = check_interval(payload, lo, hi)
    edges = payload["edges"]
    weights = [F(0)] * len(payload["mean"])
    for i, (a, b) in enumerate(zip(edges, edges[1:])):
        left, right = max(a, lo), min(b, hi)
        if left >= right:
            continue
        lz, rz = left - a, right - a
        for j in range(4):
            weights[4 * i + j] = (rz ** (j + 1) - lz ** (j + 1)) / F(j + 1)
    return weights


def variance(payload, weights):
    u = payload["uncertainty"]
    if u["kind"] == "cov":
        return quadratic(weights, u["matrix"])
    loadings, latent = u["loadings"], u["latent_cov"]
    reduced = [sum(loadings[i][k] * weights[i] for i in range(len(weights)))
               for k in range(len(latent))]
    return quadratic(reduced, latent)


def integrate(payload, lo, hi):
    weights = integration_weights(payload, lo, hi)
    return dot(weights, payload["mean"]), variance(payload, weights)
