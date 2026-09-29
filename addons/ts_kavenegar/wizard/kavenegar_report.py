import json

from odoo import fields, models, _
from odoo.exceptions import UserError


def _ts(d):
    return int(d.timestamp()) if d else None


class KavenegarReportWizard(models.TransientModel):
    _name = 'kavenegar.report.wizard'
    _description = 'Kavenegar reports and lookups'

    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, required=True)
    kind = fields.Selection([
        ('count_outbox', 'Count of sent messages (CountOutbox)'),
        ('select_outbox', 'Sent messages list (SelectOutbox, import into the log)'),
        ('latest_outbox', 'Latest sent messages (LatestOutbox, import into the log)'),
        ('by_receptor', 'Status by number (StatusByReceptor)'),
        ('select', 'Select messages by id (Select)'),
        ('status_local', 'Status by local id (StatusLocalMessageId)'),
        ('count_inbox', 'Count of received messages (CountInbox)'),
        ('inbox', 'Pull inbox page (InboxPaged, import)'),
        ('server_time', 'Server time (utils/getdate)'),
        ('account_config', 'Read account configuration'),
    ], required=True, default='count_outbox')
    date_from = fields.Datetime()
    date_to = fields.Datetime()
    line = fields.Char('Line / sender')
    status = fields.Integer('Status filter (0 = all)')
    receptor = fields.Char()
    ids_text = fields.Text('Ids (comma separated, max 500)')
    pagesize = fields.Integer(default=200)
    pagenumber = fields.Integer(default=1)
    include_read = fields.Boolean('Include already read')
    result = fields.Text(readonly=True)

    def action_run(self):
        self.ensure_one()
        c = self.company_id
        cl = c._kv_client()
        ids = [x for x in (self.ids_text or '').replace('\n', ',').split(',') if x.strip()]
        k = self.kind
        Msg = self.env['kavenegar.message']
        if k == 'count_outbox':
            res = c._kv_call(cl.count_outbox, _ts(self.date_from), _ts(self.date_to), self.status or None)
        elif k in ('select_outbox', 'latest_outbox'):
            if not c.kv_has_ip_whitelist:
                raise UserError(_('Outbox reports need the server IP in the Kavenegar whitelist (enable it in Settings once done).'))
            res = c._kv_call(cl.select_outbox, _ts(self.date_from), _ts(self.date_to), self.line or None) \
                if k == 'select_outbox' else c._kv_call(cl.latest_outbox, self.pagesize, self.line or None)
            n = Msg._kv_import_outbox(c, res)
            res = [{'imported': n}]
        elif k == 'by_receptor':
            res = c._kv_call(cl.status_by_receptor, self.receptor, _ts(self.date_from), _ts(self.date_to))
        elif k == 'select':
            if not c.kv_has_ip_whitelist:
                raise UserError(_('Select needs the server IP in the Kavenegar whitelist.'))
            res = c._kv_call(cl.select, ids)
            Msg._kv_import_outbox(c, res)
        elif k == 'status_local':
            res = c._kv_call(cl.status_localid, ids)
        elif k == 'count_inbox':
            res = c._kv_call(cl.count_inbox, _ts(self.date_from), _ts(self.date_to), self.line or c.kv_inbox_line,
                             1 if self.include_read else 0)
        elif k == 'inbox':
            line = self.line or c.kv_inbox_line
            if not line:
                raise UserError(_('Set the inbox line.'))
            rows, meta = c._kv_call(cl.inbox_paged, line, 1 if self.include_read else 0,
                                    _ts(self.date_from), _ts(self.date_to), self.pagenumber or 1)
            new = Msg._kv_store_inbound(c, rows)
            res = [{'received': len(rows), 'new': len(new), 'meta': meta}]
        elif k == 'server_time':
            res = c._kv_call(cl.get_date)
        else:
            res = c._kv_call(cl.account_config_get)
        self.result = json.dumps(res, ensure_ascii=False, indent=1)
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new'}
