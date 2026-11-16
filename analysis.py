from fractions import Fraction as F
from vendor import spline1

class Analysis:
    def __init__(self, db):
        self.db = db

    def save(self, name, curve_id, lo, hi):
        row = self.db.execute("SELECT payload FROM curves1 WHERE id=?", (curve_id,)).fetchone()
        if row is None:
            raise KeyError(curve_id)
        spline1.weights(spline1.load(row[0]), lo, hi)
        with self.db:
            self.db.execute("INSERT INTO jobs1 VALUES(?,?,?,?) ON CONFLICT(name) "
                            "DO UPDATE SET curve_id=excluded.curve_id,lo=excluded.lo,"
                            "hi=excluded.hi", (name, curve_id, str(F(lo)), str(F(hi))))

    def run(self, name):
        row = self.db.execute("SELECT curve_id,lo,hi FROM jobs1 WHERE name=?", (name,)).fetchone()
        if row is None:
            raise KeyError(name)
        curve_id, lo, hi = row
        raw = self.db.execute("SELECT payload FROM curves1 WHERE id=?", (curve_id,)).fetchone()
        if raw is None:
            raise KeyError(curve_id)
        return spline1.integral(spline1.load(raw[0]), lo, hi)
