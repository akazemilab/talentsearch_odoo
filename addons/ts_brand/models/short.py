"""Short links for SMS (docs/clinic/05_sms_texts.md rule 2: a link of at most 34 characters, never the full token).

`ts.assignment.short_code` -> /i/<code> -> 302 /invite/<token>; `ts.member.invite.short_code` -> /j/<code> -> 302
/join/<token>. onb2: new codes have 12 characters of [a-z0-9] (36^12 = 4.7e18); the 8-character codes of earlier
invitations keep working. Unique, set in create (before any SMS is sent from an inner create) and backfilled at install
(hooks.py). The code is as secret as the token it leads to: it is only ever sent to the invitee, and lookups are
rate-limited per network address (ts_onboard). Inside an SMS context (`ts_sms_short`), `invite_url()` answers the short
link, so the old fallback texts never carry the token either.
"""
import re
import secrets
import string

from odoo import api, fields, models

ALPHABET = string.ascii_lowercase + string.digits
CODE_LEN = 12
CODE_RE = re.compile(r'^(?:[a-z0-9]{8}|[a-z0-9]{12})$')     # 12 since onb2; older 8-character codes stay valid


def new_code():
    return ''.join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))


def site_base(env):
    return (env.ref('ts_website.website_ts').sudo().domain or '').rstrip('/')


class _ShortCodeMixin(models.AbstractModel):
    _name = 'ts.brand.short.mixin'
    _description = 'Talent Search short link code'

    short_code = fields.Char('کد پیوند کوتاه', copy=False, index=True, readonly=True)

    @api.model
    def _ts_new_short_code(self):
        for _ in range(8):
            code = new_code()
            if not self.sudo().with_context(active_test=False).search_count([('short_code', '=', code)]):
                return code
        return new_code()      # 8 collisions in a row in 2.8e12 codes: the unique constraint decides

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('short_code'):
                vals['short_code'] = self._ts_new_short_code()
        return super().create(vals_list)

    def ts_short_code(self):
        """The code; a row created before the module (and missed by the backfill) gets one now."""
        self.ensure_one()
        if not self.short_code:
            self.sudo().write({'short_code': self._ts_new_short_code()})
        return self.short_code


class TsAssignmentShort(models.Model):
    _name = 'ts.assignment'
    _inherit = ['ts.assignment', 'ts.brand.short.mixin']

    _short_code_unique = models.Constraint('unique(short_code)', 'کد پیوند کوتاه باید یکتا باشد.')

    def ts_short_url(self):
        self.ensure_one()
        return '%s/i/%s' % (site_base(self.env), self.ts_short_code())

    def invite_url(self):
        if self.env.context.get('ts_sms_short'):
            return self.ts_short_url()
        return super().invite_url()


class TsMemberInviteShort(models.Model):
    _name = 'ts.member.invite'
    _inherit = ['ts.member.invite', 'ts.brand.short.mixin']

    _short_code_unique = models.Constraint('unique(short_code)', 'کد پیوند کوتاه باید یکتا باشد.')

    def ts_short_url(self):
        self.ensure_one()
        return '%s/j/%s' % (site_base(self.env), self.ts_short_code())

    def invite_url(self):
        if self.env.context.get('ts_sms_short'):
            return self.ts_short_url()
        return super().invite_url()
