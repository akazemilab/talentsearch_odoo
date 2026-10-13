"""Rate limits of onb2 per hashed network address: invitation and short-link lookups (/invite/, /i/, /j/, /c/: 30 a minute
each family), new guest attempts (5 an hour) and guest answers (200 a minute). A row holds a key such as
'short:<ip hash>' and its time, nothing else; rows older than a day are dropped.

A hit is counted in its own short transaction, committed at once: a lookup of an unknown code ends in a 404 (the request's
own transaction is rolled back), and that miss must still count, or guessing codes would never be slowed down."""
from datetime import timedelta

from odoo import api, fields, models


class TsRateHit(models.Model):
    _name = 'ts.rate.hit'
    _description = 'Talent Search rate-limit hit'
    _log_access = False

    key = fields.Char(required=True, index=True)
    at = fields.Datetime(required=True, index=True, default=fields.Datetime.now)

    @api.model
    def ts_hit(self, key, limit, seconds):
        """Count one hit of `key`; False when `limit` hits already happened within `seconds` (the hit is not counted)."""
        now = fields.Datetime.now()
        since = now - timedelta(seconds=seconds)
        with self.env.registry.cursor() as cr:
            cr.execute('SELECT count(*) FROM ts_rate_hit WHERE key = %s AND at >= %s', [key, since])
            if cr.fetchone()[0] >= limit:
                return False
            cr.execute('INSERT INTO ts_rate_hit (key, at) VALUES (%s, %s)', [key, now])
        return True

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('at', '<', fields.Datetime.now() - timedelta(days=1))]).unlink()
