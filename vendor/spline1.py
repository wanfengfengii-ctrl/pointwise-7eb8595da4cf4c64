"""Offline legacy SDK. All arithmetic is exact; no target-basis conversion."""
import json
from fractions import Fraction as F
from rational import dot, quadratic

def load(raw):
    obj = json.loads(raw)
    if set(obj) != {"knots", "mean", "cov"}:
        raise ValueError("legacy fields")
    t = list(map(F, obj["knots"]))
    m = list(map(F, obj["mean"]))
    c = [list(map(F, row)) for row in obj["cov"]]
    n = len(m)
    if not 4 <= n <= 8 or len(t) != n+4:
        raise ValueError("legacy dimensions")
    if t != sorted(t) or not t[3] < t[n]:
        raise ValueError("legacy domain")
    if t[:4] != [t[3]]*4 or t[n:] != [t[n]]*4:
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

def basis(curve, x):
    t, m, _ = curve
    x = F(x)
    n = len(m)
    if not t[3] <= x <= t[n]:
        raise ValueError("outside domain")
    final_span = max(i for i in range(len(t)-1) if t[i] < t[i+1])
    def b(i, degree):
        if degree == 0:
            if x == t[n]:
                return F(i == final_span)
            return F(t[i] <= x < t[i+1])
        left = right = F(0)
        if t[i+degree] != t[i]:
            left = (x-t[i])/(t[i+degree]-t[i])*b(i, degree-1)
        if t[i+degree+1] != t[i+1]:
            right = (t[i+degree+1]-x)/(t[i+degree+1]-t[i+1])*b(i+1, degree-1)
        return left+right
    return [b(i, 3) for i in range(n)]

def value(curve, x):
    return dot(basis(curve, x), curve[1])

def weights(curve, lo, hi):
    t, m, _ = curve
    lo, hi = F(lo), F(hi)
    if not t[3] <= lo <= hi <= t[len(m)]:
        raise ValueError("bad interval")
    result = [F(0)]*len(m)
    edges = sorted(set([lo, hi]+[x for x in t if lo < x < hi]))
    # Open four-point Newton-Cotes is exact for cubics and never samples a jump.
    for a, b in zip(edges, edges[1:]):
        for j, coefficient in enumerate([11, 1, 1, 11], 1):
            w = basis(curve, a+(b-a)*F(j, 5))
            for i in range(len(m)):
                result[i] += (b-a)*F(coefficient, 24)*w[i]
    return result

def integral(curve, lo, hi):
    w = weights(curve, lo, hi)
    return dot(w, curve[1]), quadratic(w, curve[2])
