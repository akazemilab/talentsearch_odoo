"""Rate limits of onb2 per hashed network address: short-link lookups (/i/, /j/, /c/: 30 a minute) and new guest attempts
(3 an hour). A row holds a key such as 'short:<ip hash>' and its time, nothing else; rows older than a day are dropped."""
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
        since = fields.Datetime.now() - timedelta(seconds=seconds)
        S = self.sudo()
        if S.search_count([('key', '=', key), ('at', '>=', since)]) >= limit:
            return False
        S.create({'key': key})
        return True

    @api.autovacuum
    def _gc_old(self):
        self.sudo().search([('at', '<', fields.Datetime.now() - timedelta(days=1))]).unlink()
