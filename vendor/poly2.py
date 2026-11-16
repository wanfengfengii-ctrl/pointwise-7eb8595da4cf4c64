"""Offline target SDK: native polynomial storage and value lookup only."""
import json
from fractions import Fraction as F
from rational import dumps, dot

SCHEMA = """
CREATE TABLE IF NOT EXISTS curves2(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs2(name TEXT PRIMARY KEY, curve_id TEXT NOT NULL,
 lo TEXT NOT NULL, hi TEXT NOT NULL);
"""

def initialize(db):
    # execute statements separately: executescript would commit a caller transaction.
    for statement in SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)

def decode(raw):
    obj = json.loads(raw)
    edges = list(map(F, obj["edges"]))
    mean = list(map(F, obj["mean"]))
    q = 4*(len(edges)-1)
    if len(edges) < 2 or any(a >= b for a, b in zip(edges, edges[1:])):
        raise ValueError("edges")
    if len(mean) != q:
        raise ValueError("mean")
    u = obj["uncertainty"]
    if u["kind"] == "cov":
        c = [list(map(F, row)) for row in u["matrix"]]
        if len(c) != q or any(len(row) != q for row in c):
            raise ValueError("cov dimensions")
        if any(c[i][j] != c[j][i] for i in range(q) for j in range(q)):
            raise ValueError("cov symmetry")
        u = {"kind": "cov", "matrix": c}
    elif u["kind"] == "factor":
        a = [list(map(F, row)) for row in u["loadings"]]
        c = [list(map(F, row)) for row in u["latent_cov"]]
        k = len(c)
        if k < 1 or len(a) != q or any(len(row) != k for row in a+c):
            raise ValueError("factor dimensions")
        if any(c[i][j] != c[j][i] for i in range(k) for j in range(k)):
            raise ValueError("latent symmetry")
        u = {"kind": "factor", "loadings": a, "latent_cov": c}
    else:
        raise ValueError("uncertainty kind")
    return {"edges": edges, "mean": mean, "uncertainty": u}

def replace(db, curve_id, payload):
    decode(dumps(payload))
    db.execute("INSERT INTO curves2 VALUES(?,?) ON CONFLICT(id) DO UPDATE "
               "SET payload=excluded.payload", (curve_id, dumps(payload)))

def read(db, curve_id):
    row = db.execute("SELECT payload FROM curves2 WHERE id=?", (curve_id,)).fetchone()
    if row is None:
        raise KeyError(curve_id)
    return decode(row[0])

def value(payload, x):
    edges, m = payload["edges"], payload["mean"]
    x = F(x)
    if not edges[0] <= x <= edges[-1]:
        raise ValueError("outside domain")
    i = len(edges)-2 if x == edges[-1] else next(
        i for i in range(len(edges)-1) if edges[i] <= x < edges[i+1])
    z = x-edges[i]
    return dot(m[4*i:4*i+4], [F(1), z, z*z, z*z*z])
