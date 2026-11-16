from rational import dumps
from vendor import poly2
from convert import convert_legacy, parse_legacy

SCHEMA = """
CREATE TABLE meta(version INTEGER NOT NULL);
INSERT INTO meta VALUES(1);
CREATE TABLE curves1(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE jobs1(name TEXT PRIMARY KEY, curve_id TEXT NOT NULL,
 lo TEXT NOT NULL, hi TEXT NOT NULL);
"""

def create(db):
    db.executescript(SCHEMA)

def version(db):
    return db.execute("SELECT version FROM meta").fetchone()[0]

class Store:
    def __init__(self, db):
        self.db = db

    def replace(self, curve_id, payload):
        if version(self.db) == 1:
            raw = dumps(payload)
            parse_legacy(raw)
            with self.db:
                self.db.execute("INSERT INTO curves1 VALUES(?,?) ON CONFLICT(id) "
                                "DO UPDATE SET payload=excluded.payload", (curve_id, raw))
        else:
            target = convert_legacy(payload)
            with self.db:
                poly2.replace(self.db, curve_id, target)

    def value(self, curve_id, x):
        if version(self.db) == 1:
            row = self.db.execute("SELECT payload FROM curves1 WHERE id=?",
                                  (curve_id,)).fetchone()
            if row is None:
                raise KeyError(curve_id)
            payload = convert_legacy(row[0])
        else:
            payload = poly2.read(self.db, curve_id)
        return poly2.value(payload, x)

def atomic_upgrade(db, populate, before_commit=lambda: None):
    """Provided transaction facility, not a converter. No active caller transaction."""
    if db.in_transaction:
        raise RuntimeError("active transaction")
    db.execute("BEGIN IMMEDIATE")
    try:
        version = db.execute("SELECT version FROM meta").fetchone()[0]
        if version == 2:
            db.rollback()
            return False
        if version != 1:
            raise ValueError("unsupported version")
        populate(db)
        before_commit()
        db.execute("UPDATE meta SET version=2")
        db.commit()
        return True
    except BaseException:
        db.rollback()
        raise
