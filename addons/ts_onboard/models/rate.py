"""Rate limits of onb2 per hashed network address: invitation and short-link lookups (/invite/, /i/, /j/: 60 a minute
each family, /c/: 120), new guest attempts (5 an hour) and guest answers (200 a minute). A row holds a key such as
'short:<ip hash>' and its time, nothing else; rows older than a day are dropped.

A hit is counted in the request's own transaction (no second cursor). The lookups that can miss answer their 404 inside
the request (controllers/invite.py `counted`), so the transaction, and with it the hit, is committed: guessing unknown
codes is slowed down too.

The address is `request.httprequest.remote_addr`. On the production server Odoo runs with proxy_mode and nginx sends
X-Forwarded-Host, X-Forwarded-For and X-Real-IP, so werkzeug's ProxyFix (x_for=1: the hop nginx appends, which a client
cannot forge) gives the visitor's own address (docs/onboarding/02_invites_and_guest.md, «Client addresses»)."""
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
        cr = self.env.cr
        cr.execute('SELECT count(*) FROM ts_rate_hit WHERE key = %s AND at >= %s', [key, now - timedelta(seconds=seconds)])
        if cr.fetchone()[0] >= limit:
            return False
        cr.execute('INSERT INTO ts_rate_hit (key, at) VALUES (%s, %s)', [key, now])
        return True

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('at', '<', fields.Datetime.now() - timedelta(days=1))]).unlink()
