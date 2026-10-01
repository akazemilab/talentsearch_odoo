"""Retention jobs (S18, PRV-3, G24, decision D7; 04_data_model.md section 6).

The daily job ships SWITCHED OFF (`ts_panel.retention_enabled` = 0). Off, it only writes a count per rule ("would remove").
On, it applies the rules marked `auto`; the others are always report-only (they need a stopped state or a purge path that
does not exist yet). Every run is audited with counts only.
"""
from datetime import timedelta

from odoo import api, fields, models

from odoo.addons.ts_org.models.assignment import INVITE_TTL_DAYS

from .lifecycle import ANON_NAME, closed_due

NOTIFICATION_DAYS = 180
INVITE_GRACE_DAYS = 90
AUDIT_YEARS = 5
RULES = [                                   # (code, label, auto)
    ('notifications', 'اعلان‌های قدیمی‌تر از ۱۸۰ روز', True),
    ('invite_contacts', 'اطلاعات تماس دعوت‌های بی‌پاسخ پس از ۹۰ روز از انقضا', True),
    ('closed_panels', 'مراجعان پنل‌های بسته‌شده پس از ۹۰ روز', True),
    ('abandoned_attempts', 'آزمون‌های نیمه‌تمام بدون فعالیت (فقط گزارش)', False),
    ('audit_events', 'رویدادهای ممیزی قدیمی‌تر از ۵ سال (فقط گزارش)', False),
]
AUTO = {code for code, _l, auto in RULES if auto}


class TsRetentionLog(models.Model):
    _name = 'ts.retention.log'
    _description = 'Talent Search retention run'
    _order = 'id desc'

    run_on = fields.Datetime('زمان اجرا', default=fields.Datetime.now, readonly=True, index=True)
    rule = fields.Selection([(c, l) for c, l, _a in RULES], 'قاعده', required=True, readonly=True)
    would_remove = fields.Integer('قابل حذف', readonly=True)
    removed = fields.Integer('حذف‌شده', readonly=True)
    applied = fields.Boolean('اعمال شد', readonly=True)

    @api.model
    def enabled(self):
        return bool(self.env['ir.config_parameter'].sudo().get_bool('ts_panel.retention_enabled', False))

    # ------------------------------------------------------------------ the rules: candidates
    @api.model
    def _candidates(self, rule):
        env, now = self.env, fields.Datetime.now()
        if rule == 'notifications':
            return env['ts.notification'].sudo().search([('create_date', '<', now - timedelta(days=NOTIFICATION_DAYS))])
        if rule == 'invite_contacts':
            cut = now - timedelta(days=INVITE_TTL_DAYS + INVITE_GRACE_DAYS)
            return env['ts.assignment'].sudo().search([
                ('user_id', '=', False), ('create_date', '<', cut), ('invitee_name', '!=', ANON_NAME),
                '|', ('invitee_email', '!=', False), ('invitee_phone', '!=', False)])
        if rule == 'closed_panels':
            return env['ts.panel.client'].sudo().search([
                ('workspace_id', 'in', closed_due(env).ids), ('anonymised_on', '=', False)])
        if rule == 'abandoned_attempts':
            days = env['ir.config_parameter'].sudo().get_int('ts_panel.abandon_days', 180) or 180
            return env['ts.attempt'].sudo().search([('state', 'in', ('consent', 'in_progress')),
                                                    ('write_date', '<', now - timedelta(days=days))])
        if rule == 'audit_events':
            return env['ts.audit.event'].sudo().search([('create_date', '<', now - timedelta(days=365 * AUDIT_YEARS))])
        return env['ts.notification'].browse()

    @api.model
    def _apply(self, rule, rows):
        if rule == 'notifications':
            n = len(rows)
            rows.unlink()
            return n
        if rule == 'invite_contacts':
            n = 0
            for a in rows:
                a.write({'invitee_name': ANON_NAME, 'invitee_email': False, 'invitee_phone': False})
                c = a.client_id
                if c and not c.user_id and not c.attempt_ids and len(c.assignment_ids) == 1:
                    c.ts_anonymise()
                n += 1
            return n
        if rule == 'closed_panels':
            return rows.ts_anonymise()
        return 0

    @api.model
    def _cron_run(self):
        """Daily. Writes one log row per rule; deletes only when the switch is on."""
        on = self.enabled()
        out = {}
        for code, _label, _auto in RULES:
            rows = self._candidates(code)
            n = len(rows)
            removed = 0
            if on and code in AUTO and n:
                removed = self._apply(code, rows)
            self.sudo().create({'rule': code, 'would_remove': n, 'removed': removed, 'applied': bool(on and code in AUTO)})
            out[code] = n
        self.env['ts.audit.event'].sudo().log('retention.run', None, enabled=bool(on), **{k: v for k, v in out.items()})
        return out
