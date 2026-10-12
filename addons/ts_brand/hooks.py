"""Install: every existing invitation and colleague invitation gets its short code (SMS links, docs/clinic/05_sms_texts.md
rule 2). SQL, once: an ORM write would run the audit hooks of ts.assignment for thousands of rows."""
import logging

from .models.short import new_code

_logger = logging.getLogger(__name__)


def backfill_short_codes(cr):
    out = {}
    for table in ('ts_assignment', 'ts_member_invite'):
        cr.execute('SELECT short_code FROM "%s" WHERE short_code IS NOT NULL' % table)
        used = {r[0] for r in cr.fetchall()}
        cr.execute('SELECT id FROM "%s" WHERE short_code IS NULL ORDER BY id' % table)
        ids = [r[0] for r in cr.fetchall()]
        for rid in ids:
            code = new_code()
            while code in used:
                code = new_code()
            used.add(code)
            cr.execute('UPDATE "%s" SET short_code = %%s WHERE id = %%s' % table, [code, rid])
        out[table] = len(ids)
    _logger.info('ts_brand: short codes backfilled %s', out)
    return out


def post_init_hook(env):
    backfill_short_codes(env.cr)
