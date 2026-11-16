"""One-shot v1 to v2 migration using the provided atomic transaction facility."""
from archive import atomic_upgrade
from convert import convert_legacy
from vendor import poly2


def populate(db):
    """Write the complete v2 target state inside the caller's transaction."""
    poly2.initialize(db)
    for name, curve_id, lo, hi in db.execute(
            "SELECT name,curve_id,lo,hi FROM jobs1 ORDER BY name"):
        db.execute("INSERT INTO jobs2 VALUES(?,?,?,?)", (name, curve_id, lo, hi))
    for curve_id, raw in db.execute(
            "SELECT id,payload FROM curves1 ORDER BY id"):
        poly2.replace(db, curve_id, convert_legacy(raw))


def upgrade(db, before_commit=lambda: None):
    """Upgrade the legacy library; True on first success, False if already v2.

    The legacy tables are left untouched as audit text.  Any failure, including
    one raised by ``before_commit``, rolls the whole switch back.
    """
    return atomic_upgrade(db, populate, before_commit)
