from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..tools.kavenegar import normalize_receptor

REASONS = [('0', 'Web service'), ('1', 'Panel'), ('2', 'Recipient cancel (لغو۱۱)'), ('3', 'Admin'), ('10', 'Unknown')]


class KavenegarBlocked(models.Model):
    _name = 'kavenegar.blocked'
    _description = 'Kavenegar blocked number (line blacklist)'
    _rec_name = 'number'
    _order = 'id desc'

    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    number = fields.Char(required=True, index=True)
    line = fields.Char('Line', required=True, default=lambda s: s.env.company.kv_sender)
    reason = fields.Selection(REASONS)
    blocked_date = fields.Datetime()

    _uniq = models.Constraint('unique(company_id, line, number)', 'This number is already blocked on that line.')

    @api.model_create_multi
    def create(self, vals_list):
        # locally created rows are pushed to Kavenegar (max 200 per call); synced rows are not
        recs = super().create(vals_list)
        if not self.env.context.get('kv_no_push'):
            for company, group in recs.grouped('company_id').items():
                for line, g in group.grouped('line').items():
                    for i in range(0, len(g), 200):
                        part = g[i:i + 200]
                        nums = [normalize_receptor(n) or n for n in part.mapped('number')]
                        company._kv_call(company._kv_client().blocked_add, line, nums)
                        part.write({'reason': '0'})
        return recs

    def unlink(self):
        if not self.env.context.get('kv_no_push'):
            for company, group in self.grouped('company_id').items():
                for line, g in group.grouped('line').items():
                    for i in range(0, len(g), 50):
                        company._kv_call(company._kv_client().blocked_remove, line, g[i:i + 50].mapped('number'))
        return super().unlink()

    def action_check_remote(self):
        for company, group in self.grouped('company_id').items():
            for line, g in group.grouped('line').items():
                res = company._kv_call(company._kv_client().blocked_exists, line, g.mapped('number'))
                if not res:
                    raise UserError(_('No answer.'))
        return True

    @api.model
    def action_sync(self):
        company = self.env.company
        line = company.kv_sender
        if not line:
            raise UserError(_('Set the default sender line first.'))
        cl = company._kv_client()
        page, seen = 1, set()
        while page <= 200:
            rows = company._kv_call(cl.blocked_list, line, None, None, page)
            if not rows:
                break
            for e in rows:
                num = str(e.get('receptor') or e.get('number') or '')
                if not num:
                    continue
                seen.add(num)
                vals = {'reason': str(e.get('blockreason', 10)) if str(e.get('blockreason', 10)) in dict(REASONS) else '10'}
                rec = self.search([('company_id', '=', company.id), ('line', '=', line), ('number', '=', num)], limit=1)
                if rec:
                    rec.write(vals)
                else:
                    self.with_context(kv_no_push=True).create(dict(vals, number=num, line=line, company_id=company.id))
            page += 1
        gone = self.search([('company_id', '=', company.id), ('line', '=', line), ('number', 'not in', list(seen))])
        gone.with_context(kv_no_push=True).unlink()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': _('%s blocked numbers synchronised', len(seen)), 'type': 'success'}}
