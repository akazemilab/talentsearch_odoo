import logging
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..tools.kavenegar import (FINAL_STATUSES, KavenegarError, STATUS_TEXT, STATUS_TO_ODOO,
                               normalize_receptor, sms_parts)

_logger = logging.getLogger(__name__)


def _ts(value):
    """Kavenegar UnixTime (int/str) -> naive UTC datetime."""
    try:
        return datetime.utcfromtimestamp(int(value)) if value else False
    except (TypeError, ValueError, OverflowError):
        return False


class KavenegarMessage(models.Model):
    _name = 'kavenegar.message'
    _description = 'Kavenegar message log'
    _order = 'id desc'
    _rec_name = 'receptor'

    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    direction = fields.Selection([('out', 'Outgoing'), ('in', 'Incoming')], required=True, default='out', index=True)
    kind = fields.Selection([('sms', 'SMS'), ('lookup', 'Verify Lookup'), ('call', 'Voice call'),
                             ('inbox', 'Inbox')], required=True, default='sms')
    messageid = fields.Char('Kavenegar message id', index=True)
    sms_uuid = fields.Char('Odoo SMS uuid', index=True)
    receptor = fields.Char(index=True)
    sender = fields.Char()
    body = fields.Text()
    kv_status = fields.Integer('Kavenegar status code')
    status_text = fields.Char('Status')
    state = fields.Selection([
        ('queued', 'Queued'), ('scheduled', 'Scheduled'), ('sent', 'Sent to carrier'),
        ('delivered', 'Delivered'), ('failed', 'Failed'), ('cancelled', 'Cancelled'),
        ('received', 'Received')], compute='_compute_state', store=True, index=True)
    cost = fields.Float('Cost (rial)')
    tag = fields.Char()
    characters = fields.Integer()
    parts = fields.Integer()
    scheduled = fields.Boolean()
    template_name = fields.Char('Template')
    partner_id = fields.Many2one('res.partner', 'Contact', ondelete='set null')
    message_date = fields.Datetime('Kavenegar date')
    last_check = fields.Datetime()
    is_final = fields.Boolean(compute='_compute_state', store=True, index=True)
    error = fields.Char()

    @api.depends('kv_status', 'direction')
    def _compute_state(self):
        mp = {1: 'queued', 2: 'scheduled', 4: 'sent', 5: 'sent', 6: 'failed', 10: 'delivered',
              11: 'failed', 13: 'cancelled', 14: 'failed'}
        for m in self:
            if m.direction == 'in':
                m.state, m.is_final = 'received', True
            else:
                m.state = mp.get(m.kv_status, 'failed' if m.kv_status == 100 else 'queued')
                m.is_final = m.kv_status in FINAL_STATUSES

    # -- logging ---------------------------------------------------------------
    @api.model
    def _kv_log_sent(self, vals_list):
        for v in vals_list:
            if v.get('receptor'):
                v['partner_id'] = v.get('partner_id') or self._kv_find_partner(v['receptor']).id
        return self.create(vals_list)

    @api.model
    def _kv_find_partner(self, number):
        rec = normalize_receptor(number)
        if not rec:
            return self.env['res.partner']
        last10 = rec[-9:]
        P = self.env['res.partner'].sudo()
        flds = [f for f in ('phone', 'mobile') if f in P._fields]
        dom = ['|'] * (len(flds) - 1) + [(f, 'like', last10) for f in flds]
        return P.search(dom, limit=1)

    # -- status -------------------------------------------------------------------
    def _kv_apply_status(self, status, text=None, extra=None):
        for m in self:
            vals = {'kv_status': int(status), 'status_text': text or STATUS_TEXT.get(int(status)),
                    'last_check': fields.Datetime.now()}
            vals.update(extra or {})
            m.write(vals)
        self._kv_sync_native()

    def _kv_sync_native(self):
        """Push the Kavenegar status to the native sms tracker / notifications."""
        Tr = self.env['sms.tracker'].sudo()
        for m in self.filtered(lambda x: x.sms_uuid and x.direction == 'out'):
            state, ft = STATUS_TO_ODOO.get(m.kv_status, (None, None))
            tr = Tr.search([('sms_uuid', '=', m.sms_uuid)], limit=1)
            if not state or not tr:
                continue
            try:
                if state == 'error':
                    tr._action_update_from_sms_state('error', failure_type=ft, failure_reason=m.status_text)
                elif state in ('pending', 'sent', 'canceled'):
                    tr._action_update_from_sms_state(state)
            except Exception:  # native update must never break the log update
                _logger.exception('Kavenegar: native tracker update failed for %s', m.sms_uuid)

    def action_refresh_status(self):
        """Status of up to 500 ids per call, only the last 48 h are known to Kavenegar."""
        todo = self.filtered(lambda m: m.direction == 'out' and m.messageid)
        for company, recs in todo.grouped('company_id').items():
            cl = company._kv_client()
            for i in range(0, len(recs), 500):
                part = recs[i:i + 500]
                try:
                    entries = company._kv_call(cl.status, part.mapped('messageid'))
                except UserError:
                    raise
                by_id = {str(e.get('messageid')): e for e in entries}
                for m in part:
                    e = by_id.get(m.messageid)
                    if e:
                        m._kv_apply_status(e.get('status'), e.get('statustext'))
        return True

    def action_cancel_scheduled(self):
        """Cancel Kavenegar-scheduled messages (cost is refunded, status 13)."""
        todo = self.filtered(lambda m: m.direction == 'out' and m.kv_status == 2 and m.messageid)
        if not todo:
            raise UserError(_('Only scheduled messages can be cancelled.'))
        for company, recs in todo.grouped('company_id').items():
            cl = company._kv_client()
            for i in range(0, len(recs), 500):
                part = recs[i:i + 500]
                entries = company._kv_call(cl.cancel, part.mapped('messageid'))
                by_id = {str(e.get('messageid')): e for e in entries}
                for m in part:
                    e = by_id.get(m.messageid) or {}
                    m._kv_apply_status(e.get('status') or 13, e.get('statustext'))
        return True

    @api.model
    def _kv_cron_poll(self):
        """Fallback for missed webhooks: poll every open message younger than 47 h."""
        limit = fields.Datetime.now() - timedelta(hours=47)
        for company in self.env['res.company'].sudo().search([('kv_enabled', '=', True)]):
            if not company.sudo().kv_api_key:
                continue
            open_msgs = self.sudo().search([
                ('company_id', '=', company.id), ('direction', '=', 'out'), ('is_final', '=', False),
                ('messageid', '!=', False), ('create_date', '>=', limit)], limit=1000)
            try:
                open_msgs.action_refresh_status()
            except UserError as e:
                _logger.info('Kavenegar poll skipped: %s', e)
            # anything older than 48h can no longer be asked: close it
            self.sudo().search([('direction', '=', 'out'), ('is_final', '=', False),
                                ('create_date', '<', fields.Datetime.now() - timedelta(hours=48))]).write(
                {'kv_status': 100, 'status_text': STATUS_TEXT[100]})

    # -- inbox ----------------------------------------------------------------------
    @api.model
    def _kv_store_inbound(self, company, entries):
        """Store incoming SMS (dedupe on messageid) and post them on the contact."""
        new = self.browse()
        for e in entries:
            mid = str(e.get('messageid') or e.get('id') or '')
            if mid and self.sudo().search_count([('direction', '=', 'in'), ('messageid', '=', mid)]):
                continue
            sender = str(e.get('sender') or e.get('from') or '')
            rec = self.sudo().create({
                'company_id': company.id, 'direction': 'in', 'kind': 'inbox', 'messageid': mid,
                'sender': sender, 'receptor': str(e.get('receptor') or e.get('to') or company.kv_inbox_line or ''),
                'body': e.get('message') or '', 'message_date': _ts(e.get('date')) or fields.Datetime.now(),
                'partner_id': self._kv_find_partner(sender).id,
            })
            if rec.partner_id:
                rec.partner_id.sudo().message_post(
                    body=_('Incoming SMS: %s', rec.body), message_type='comment',
                    subtype_xmlid='mail.mt_note')
            new += rec
        return new

    @api.model
    def _kv_cron_inbox(self):
        for company in self.env['res.company'].sudo().search([('kv_enabled', '=', True), ('kv_inbox_line', '!=', False)]):
            if not company.kv_api_key:
                continue
            cl = company._kv_client()
            try:
                for _i in range(10):  # 100 messages per call, they become read afterwards
                    entries = cl.receive(company.kv_inbox_line, 0)
                    if not entries:
                        break
                    self._kv_store_inbound(company, entries)
            except KavenegarError as e:
                _logger.info('Kavenegar inbox pull skipped: %s', e)

    # -- generic import (select / outbox reports) --------------------------------------
    @api.model
    def _kv_import_outbox(self, company, entries):
        n = 0
        for e in entries:
            mid = str(e.get('messageid') or '')
            if not mid:
                continue
            status = int(e.get('status') or 0)
            existing = self.sudo().search([('messageid', '=', mid), ('direction', '=', 'out')], limit=1)
            vals = {'kv_status': status, 'status_text': e.get('statustext') or STATUS_TEXT.get(status),
                    'cost': float(e.get('cost') or 0)}
            if existing:
                existing._kv_apply_status(status, vals['status_text'], {'cost': vals['cost']})
            else:
                body = e.get('message') or ''
                chars, parts = sms_parts(body)
                self._kv_log_sent([dict(vals, company_id=company.id, direction='out', kind='sms', messageid=mid,
                                        receptor=str(e.get('receptor') or ''), sender=e.get('sender'), body=body,
                                        message_date=_ts(e.get('date')), characters=chars, parts=parts)])
            n += 1
        return n
