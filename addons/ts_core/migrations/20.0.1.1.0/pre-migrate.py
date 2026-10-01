"""Panel v2 S1, M2: one active membership per person per panel, before the partial unique index is built.

The kept row is the one with the higher rank (owner > clinic_director = hr_admin > admin > the rest, then the
oldest); the others are deactivated, never deleted. Live data has no such case; clones that ran older suites may.
The old unique(workspace_id, user_id, role) constraint is dropped: with it a person who was deactivated and
invited again with the same role could not be added."""
import logging

_logger = logging.getLogger(__name__)

RANK = {'owner': 5, 'clinic_director': 4, 'hr_admin': 4, 'admin': 3}


def migrate(cr, version):
    cr.execute("SELECT to_regclass('ts_workspace_member') IS NOT NULL")
    if not cr.fetchone()[0]:
        return
    cr.execute("SELECT id, workspace_id, user_id, role FROM ts_workspace_member WHERE active IS TRUE ORDER BY workspace_id, user_id, id")
    groups = {}
    for mid, ws, uid, role in cr.fetchall():
        groups.setdefault((ws, uid), []).append((RANK.get(role, 2), -mid, mid))
    drop = []
    for rows in groups.values():
        if len(rows) > 1:
            rows.sort(reverse=True)           # highest rank first, then the oldest (smallest id)
            drop += [r[2] for r in rows[1:]]
    if drop:
        cr.execute("UPDATE ts_workspace_member SET active = FALSE WHERE id = ANY(%s)", [drop])
    _logger.info('ts_core 20.0.1.1.0: %d duplicate active membership(s) deactivated', len(drop))
    # drop the old three-column unique constraint, whatever its generated name
    cr.execute("""
        SELECT c.conname FROM pg_constraint c
        WHERE c.conrelid = 'ts_workspace_member'::regclass AND c.contype = 'u'
          AND (SELECT array_agg(a.attname::text ORDER BY a.attname) FROM pg_attribute a
               WHERE a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)) = ARRAY['role', 'user_id', 'workspace_id']""")
    for (name,) in cr.fetchall():
        cr.execute('ALTER TABLE ts_workspace_member DROP CONSTRAINT "%s"' % name)
