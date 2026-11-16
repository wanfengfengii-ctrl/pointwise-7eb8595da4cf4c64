from fractions import Fraction as F
from archive import version
from convert import check_interval, convert_legacy, integrate
from vendor import poly2

# The task binding, the bound curve and the schema version come from one
# statement, so a run never mixes a binding with a curve replaced under it.
_JOIN = {
    1: "SELECT m.version,j.curve_id,j.lo,j.hi,c.payload FROM meta m "
       "LEFT JOIN jobs1 j ON j.name=? LEFT JOIN curves1 c ON c.id=j.curve_id",
    2: "SELECT m.version,j.curve_id,j.lo,j.hi,c.payload FROM meta m "
       "LEFT JOIN jobs2 j ON j.name=? LEFT JOIN curves2 c ON c.id=j.curve_id",
}

class Analysis:
    def __init__(self, db):
        self.db = db

    def save(self, name, curve_id, lo, hi):
        if version(self.db) == 1:
            row = self.db.execute("SELECT payload FROM curves1 WHERE id=?",
                                  (curve_id,)).fetchone()
            if row is None:
                raise KeyError(curve_id)
            check_interval(convert_legacy(row[0]), lo, hi)
            table = "jobs1"
        else:
            check_interval(poly2.read(self.db, curve_id), lo, hi)
            table = "jobs2"
        with self.db:
            self.db.execute("INSERT INTO " + table + " VALUES(?,?,?,?) "
                            "ON CONFLICT(name) DO UPDATE SET curve_id=excluded.curve_id,"
                            "lo=excluded.lo,hi=excluded.hi",
                            (name, curve_id, str(F(lo)), str(F(hi))))

    def run(self, name):
        seen = version(self.db)
        row = self.db.execute(_JOIN[seen], (name,)).fetchone()
        if row is None:  # no meta row: nothing can be resolved
            raise KeyError(name)
        _, curve_id, lo, hi, raw = row
        if curve_id is None:
            raise KeyError(name)
        if raw is None:
            raise KeyError(curve_id)
        payload = convert_legacy(raw) if seen == 1 else poly2.decode(raw)
        return integrate(payload, lo, hi)
