from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..tools.kavenegar import KavenegarError, normalize_receptor, sms_parts


class KavenegarSendWizard(models.TransientModel):
    _name = 'kavenegar.send.wizard'
    _description = 'Send with Kavenegar'

    mode = fields.Selection([('sms', 'SMS (Send / SendArray)'), ('lookup', 'Verify Lookup template'),
                             ('call', 'Voice call (text to speech)')], default='sms', required=True)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, required=True)
    receptors = fields.Text('Numbers', help='One per line or comma separated (max 200 per Kavenegar call, more are chunked).')
    message = fields.Text('Message')
    line_ids = fields.One2many('kavenegar.send.wizard.line', 'wizard_id', string='Different message per number')
    sender = fields.Char('Sender line')
    schedule = fields.Datetime('Schedule at')
    tag = fields.Char()
    hide = fields.Boolean('Hide number in panel')
    policy = fields.Char()
    display_type = fields.Selection([('0', 'Flash (0)'), ('1', 'Mobile memory (1)'), ('2', 'Sim (2)'), ('3', 'App (3)')])
    media_id = fields.Many2one('kavenegar.media')
    characters = fields.Integer(compute='_compute_len')
    parts = fields.Integer(compute='_compute_len')
    # lookup
    template_id = fields.Many2one('kavenegar.template', domain="[('approval', '=', 'Approved')]")
    token = fields.Char()
    token2 = fields.Char()
    token3 = fields.Char()
    token10 = fields.Char()
    token20 = fields.Char()
    lookup_type = fields.Selection([('sms', 'SMS'), ('call', 'Voice call')], default='sms')
    repeat = fields.Integer('Repeat (0-5)')

    @api.depends('message')
    def _compute_len(self):
        for w in self:
            w.characters, w.parts = sms_parts(w.message)

    def _numbers(self):
        raw = (self.receptors or '').replace(',', '\n').split()
        out = []
        for n in raw:
            r = normalize_receptor(n)
            if not r:
                raise UserError(_('Invalid number: %s', n))
            out.append(r)
        return out

    def _notify(self, text):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': text, 'type': 'success', 'next': {'type': 'ir.actions.act_window_close'}}}

    def action_send(self):
        self.ensure_one()
        c = self.company_id
        if not c.kv_enabled:
            raise UserError(_('Enable Kavenegar in Settings first.'))
        if self.mode == 'sms':
            return self._send_sms()
        numbers = self._numbers()
        if not numbers:
            raise UserError(_('Enter at least one number.'))
        cl = c._kv_client()
        date = int(self.schedule.timestamp()) if self.schedule else None
        Msg = self.env['kavenegar.message']
        if self.mode == 'lookup':
            if not c.kv_has_lookup:
                raise UserError(_('Verify Lookup needs the advanced service (enable it in Settings).'))
            if not self.template_id or not self.token:
                raise UserError(_('Choose an approved template and fill the first token.'))
            logs = []
            for n in numbers:
                res = c._kv_call(cl.lookup, n, self.template_id.name, self.token, self.token2, self.token3,
                                 self.token10, self.token20, self.lookup_type, self.tag or c.kv_default_tag)
                e = res[0] if res else {}
                logs.append({'company_id': c.id, 'kind': 'lookup', 'messageid': str(e.get('messageid') or ''),
                             'receptor': n, 'sender': e.get('sender'), 'body': e.get('message') or '',
                             'kv_status': int(e.get('status') or 1), 'status_text': e.get('statustext'),
                             'cost': float(e.get('cost') or 0), 'template_name': self.template_id.name})
            Msg.sudo()._kv_log_sent(logs)
        else:
            if not self.message:
                raise UserError(_('Write the text to be spoken.'))
            logs = []
            for n in numbers:
                res = c._kv_call(cl.make_tts, n, self.message, date, None, self.repeat or None, self.tag)
                e = res[0] if res else {}
                logs.append({'company_id': c.id, 'kind': 'call', 'messageid': str(e.get('messageid') or ''),
                             'receptor': n, 'body': self.message, 'kv_status': int(e.get('status') or 1),
                             'status_text': e.get('statustext'), 'cost': float(e.get('cost') or 0),
                             'scheduled': bool(date)})
            Msg.sudo()._kv_log_sent(logs)
        return self._notify(_('%s request(s) accepted by Kavenegar', len(numbers)))

    def _send_sms(self):
        Sms = self.env['sms.sms'].with_company(self.company_id)
        base = {'kv_sender': self.sender, 'kv_date': self.schedule, 'kv_tag': self.tag, 'kv_hide': self.hide,
                'kv_policy': self.policy, 'kv_type': self.display_type, 'kv_media_id': self.media_id.id}
        vals = []
        for line in self.line_ids:
            vals.append(dict(base, number=line.number, body=line.message))
        if self.receptors:
            if not self.message:
                raise UserError(_('Write a message.'))
            vals += [dict(base, number=n, body=self.message) for n in self._numbers()]
        if not vals:
            raise UserError(_('Enter numbers and a message.'))
        Log = self.env['kavenegar.message']
        for v in vals:
            v['partner_id'] = Log._kv_find_partner(v['number']).id or False
        sms = Sms.create(vals)
        sms.send(unlink_sent=False, raise_exception=False)
        bad = sms.filtered(lambda s: s.state == 'error')
        if bad:
            raise UserError(_('%(n)s of %(t)s failed: %(r)s', n=len(bad), t=len(sms),
                              r=dict(bad._fields['failure_type'].selection).get(bad[0].failure_type, bad[0].failure_type)))
        return self._notify(_('%s SMS handed to Kavenegar', len(sms)))


class KavenegarSendWizardLine(models.TransientModel):
    _name = 'kavenegar.send.wizard.line'
    _description = 'Kavenegar send array line'

    wizard_id = fields.Many2one('kavenegar.send.wizard', ondelete='cascade')
    number = fields.Char(required=True)
    message = fields.Text(required=True)
