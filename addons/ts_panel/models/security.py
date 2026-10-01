"""Staff idle timeout (SEC-6) and the 15-character password rule on Talent Search forms (SEC-7).

Both act only on requests that arrive on the Talent Search website (website 4). eot.ir and every other website go through
unchanged: the checks return before touching the session. The timeout is switched by `ts_panel.staff_idle_hours`
(default 8, 0 = off) and applies to people who belong to at least one panel; participants keep Odoo's default session.
"""
import time

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.http import request

MIN_PASSWORD = 15
TOUCH_EVERY = 60          # seconds between updates of the last-seen mark


def on_ts_site():
    """True when the current request is for the Talent Search website. Never raises."""
    try:
        env = request.env
        site = env.ref('ts_website.website_ts', raise_if_not_found=False)
        return bool(site) and env['website'].sudo().get_current_website().id == site.id
    except Exception:                                   # noqa: BLE001  (no request: cron, shell)
        return False


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        cls._ts_idle_check()
        return super()._authenticate(endpoint)

    @classmethod
    def _ts_idle_check(cls):
        sess = request.session
        uid = sess.uid
        if not uid:
            return
        try:
            if not on_ts_site():
                return
            hours = request.env['ir.config_parameter'].sudo().get_float('ts_panel.staff_idle_hours', 8.0)
            if not hours or hours <= 0:
                return
            now = time.time()
            last = sess.get('ts_last_seen')
            if last and now - last > hours * 3600 and cls._ts_is_staff(uid):
                ctx = {k: v for k, v in request.env.context.items() if k in ('lang', 'tz', 'website_id')}
                sess.logout(keep_db=True)
                request.env = api.Environment(request.env.cr, None, ctx)       # same as an expired session
                return
            if not last or now - last > TOUCH_EVERY:
                sess['ts_last_seen'] = now
        except Exception:                               # noqa: BLE001  the timeout must never break a request
            return

    @classmethod
    def _ts_is_staff(cls, uid):
        cr = request.env.cr
        cr.execute("SELECT 1 FROM ts_workspace_member WHERE user_id = %s AND active LIMIT 1", [uid])
        return bool(cr.fetchone())


class ResUsersPassword(models.Model):
    _inherit = 'res.users'

    @api.constrains('password')
    def _ts_check_password_length(self):
        """Only for requests on the Talent Search website: a password that is set must have 15 characters or more."""
        if not on_ts_site():
            return
        for pw in self.mapped('password'):
            if pw and len(pw) < MIN_PASSWORD:
                raise ValidationError('گذرواژه باید دست‌کم ۱۵ نویسه باشد.')
