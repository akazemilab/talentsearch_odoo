import secrets

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.sms.tools.sms_api import SmsApi
from ..tools.kavenegar import Kavenegar, KavenegarError


class ResCompany(models.Model):
    _inherit = 'res.company'

    kv_enabled = fields.Boolean('Send SMS via Kavenegar')
    kv_api_key = fields.Char('Kavenegar API key', groups='base.group_system')
    kv_sender = fields.Selection('_kv_line_selection', string='Default sender line',
                                 help='Pick one of the account lines (use "Fetch lines" to refresh the list)')
    kv_inbox_line = fields.Selection('_kv_line_selection', string='Inbox line',
                                     help='Line that receives SMS (leave empty to disable inbox)')
    kv_lines = fields.Char('Known lines', readonly=True, copy=False,
                           help='Comma separated. Kavenegar has no API that lists lines, so they are read from the account outbox/inbox history.')
    kv_default_tag = fields.Char('Default tag', help='Tag created in the Kavenegar panel (letters, digits, -)')
    kv_debug = fields.Boolean('Debug mode', help='Kavenegar accepts requests but sends nothing and charges nothing.')
    kv_webhook_secret = fields.Char('Webhook secret', groups='base.group_system', copy=False)
    kv_webhook_base = fields.Char('Webhook base URL', help='Public HTTPS origin Kavenegar calls, e.g. https://ts.innerquest.me')
    kv_webhook_status_url = fields.Char(compute='_compute_kv_urls')
    kv_webhook_inbound_url = fields.Char(compute='_compute_kv_urls')
    # what the Kavenegar account has (unavailable ones are blocked with a clear message)
    kv_has_lookup = fields.Boolean('Advanced service (Verify Lookup)')
    kv_has_ip_whitelist = fields.Boolean('IP whitelist (outbox / select)')
    kv_has_messenger = fields.Boolean('Internal messenger line (media)')
    kv_min_credit = fields.Integer('Low credit alarm (rial)')
    kv_alert_user_ids = fields.Many2many('res.users', 'kv_company_alert_user_rel', 'company_id', 'user_id',
                                         string='Low credit alert users')
    kv_credit = fields.Float('Credit (rial)', readonly=True)
    kv_expire = fields.Char('Account expiry', readonly=True)
    kv_account_type = fields.Char('Account type', readonly=True)
    kv_last_sync = fields.Datetime('Last account sync', readonly=True)

    @api.model
    def _kv_line_selection(self):
        lines = []
        for c in self.env['res.company'].sudo().search([]):
            for x in (c.kv_lines or '').split(','):
                x = x.strip()
                if x and x not in lines:
                    lines.append(x)
        return [(x, x) for x in lines]

    def kv_fetch_lines(self):
        """Discover the account's lines: sender of the latest outbox, lines seen in stored messages,
        the account default sender and the lines already chosen."""
        self.ensure_one()
        found = set((self.kv_lines or '').split(','))
        found |= {self.kv_sender, self.kv_inbox_line}
        cl = self._kv_client()
        try:
            for e in cl.latest_outbox(200) or []:
                found.add(str(e.get('sender') or ''))
        except KavenegarError:
            pass
        try:
            cfg = cl.account_config_get()
            found.add(str((cfg[0] if cfg else {}).get('defaultsender') or ''))
        except KavenegarError:
            pass
        Msg = self.env['kavenegar.message'].sudo()
        for m in Msg.search([('company_id', '=', self.id), ('direction', '=', 'out'), ('sender', '!=', False)]):
            found.add(m.sender)
        for m in Msg.search([('company_id', '=', self.id), ('direction', '=', 'in'), ('receptor', '!=', False)]):
            found.add(m.receptor)
        lines = sorted(x.strip() for x in found if x and x.strip().isdigit())
        self.sudo().kv_lines = ','.join(lines)
        return lines

    def _compute_kv_urls(self):
        for c in self:
            base = (c.kv_webhook_base or c.get_base_url() or '').rstrip('/')
            secret = c.sudo().kv_webhook_secret
            c.kv_webhook_status_url = '%s/kavenegar/%s/status' % (base, secret) if secret else False
            c.kv_webhook_inbound_url = '%s/kavenegar/%s/inbound' % (base, secret) if secret else False

    def _get_sms_api_class(self):
        self.ensure_one()
        if self.kv_enabled:
            from ..tools.sms_api import SmsApiKavenegar
            return SmsApiKavenegar
        return super()._get_sms_api_class()

    def _kv_client(self):
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_str('ts_kavenegar.api_base') or None
        return Kavenegar(self.sudo().kv_api_key, base_url=base)

    def _kv_call(self, fn, *args, **kw):
        """Run a client call and turn API errors into a UserError."""
        try:
            return fn(*args, **kw)
        except KavenegarError as e:
            raise UserError(_('Kavenegar: %s', e.message))

    def kv_generate_secret(self):
        for c in self.sudo():
            c.kv_webhook_secret = secrets.token_urlsafe(24)

    def kv_sync_account(self):
        """account/info + account/config -> stored on the company."""
        self.ensure_one()
        cl = self._kv_client()
        info = self._kv_call(cl.account_info)
        info = info[0] if info else {}
        self.sudo().write({
            'kv_credit': float(info.get('remaincredit') or 0),
            'kv_expire': str(info.get('expiredate') or ''),
            'kv_account_type': info.get('type') or '',
            'kv_last_sync': fields.Datetime.now(),
        })
        try:
            self.kv_fetch_lines()
        except Exception:
            pass
        self._kv_check_credit_alarm()
        return info

    def _kv_check_credit_alarm(self):
        for c in self:
            if c.kv_min_credit and c.kv_credit < c.kv_min_credit and c.kv_alert_user_ids:
                c.kv_alert_user_ids.partner_id.sudo().message_notify(
                    partner_ids=c.kv_alert_user_ids.partner_id.ids,
                    subject=_('Kavenegar credit is low'),
                    body=_('Remaining credit %(c)s rial is below the alarm level %(m)s rial.',
                           c='{:,.0f}'.format(c.kv_credit), m='{:,}'.format(c.kv_min_credit)),
                )

    def kv_push_config(self):
        """Send debug mode and default sender to Kavenegar (account/config)."""
        self.ensure_one()
        kw = {'debugmode': 'enabled' if self.kv_debug else 'disabled'}
        if self.kv_sender:
            kw['defaultsender'] = self.kv_sender
        if self.kv_min_credit:
            kw['mincreditalarm'] = self.kv_min_credit
        return self._kv_call(self._kv_client().account_config_set, **kw)

    @api.model
    def _kv_cron_account(self):
        for c in self.sudo().search([('kv_enabled', '=', True)]):
            try:
                c.kv_sync_account()
            except UserError:
                pass
