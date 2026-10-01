"""Erase workflow (S18, PRV-4; 04_data_model.md section 6, steps 1-6). A platform manager runs it on a `ts.data.request`
of kind `erase`, or the person's panel is closed.

Attempts are emptied, not deleted: answers, results, fields and cells go; dates, instrument and panel stay for counts.
A clinical panel's attempts are not erased (restricted instead: hidden from everyone) because a retention duty may apply
(open legal item L2); the request then closes with the code `legal_hold` and the person is told.
"""
from odoo import fields, models
from odoo.exceptions import UserError

from .consent import SHARE_VERSION


class TsAttemptErase(models.Model):
    _inherit = 'ts.attempt'

    erased_on = fields.Datetime('زمان پاک‌سازی', readonly=True, copy=False)

    def ts_erase_content(self):
        """Empty one attempt. Returns 1 when something was erased."""
        self.ensure_one()
        sudo = self.sudo()
        sudo.answer_ids.unlink()
        sudo.result_ids.unlink()
        for rel in ('field_ids', 'cell_ids'):
            if rel in sudo._fields:
                sudo[rel].unlink()
        vals = {'subject_label': False, 'released': False, 'erased_on': fields.Datetime.now()}
        if 'profile_json' in sudo._fields:
            vals['profile_json'] = False
        sudo.write(vals)
        return 1


class TsDataRequestErase(models.Model):
    _inherit = 'ts.data.request'

    def action_erase(self):
        """Run the erase for the requester. Counts only in the audit."""
        self._ts_manager_only()
        for req in self.filtered(lambda r: r.kind == 'erase' and r.state in ('new', 'in_review')):
            user = req.user_id.sudo()
            A, At, C = self.env['ts.assignment'].sudo(), self.env['ts.attempt'].sudo(), self.env['ts.panel.client'].sudo()
            attempts = At.search([('user_id', '=', user.id)])
            clinical = attempts.filtered(lambda a: a.workspace_id.purpose == 'clinical')
            erasable = attempts - clinical
            # 1. every share is revoked
            shares = A.search([('attempt_id', 'in', attempts.ids), ('share_level', '!=', 'none')])
            for s in shares:
                s.share_level = 'none'
                self.env['ts.consent.record']._log('share_revoke', user, assignment=s, version=SHARE_VERSION)
            # 2. content goes (clinical: hidden, kept)
            n_att = sum(a.ts_erase_content() for a in erasable if not a.erased_on)
            for a in clinical:
                a.write({'released': False})
            # 3. client rows linked to the account
            n_cl = C.search([('user_id', '=', user.id)]).ts_anonymise()
            # 5. the account is deactivated (not when a clinical duty keeps something)
            decision = 'legal_hold' if clinical else 'done'
            if not clinical:
                user.write({'active': False})
            req.sudo().write({'state': 'done', 'decision_code': decision, 'handled_by_id': self.env.uid})
            self.env['ts.audit.event'].sudo().log('data.erase', req, shares=len(shares), attempts=n_att,
                                                  restricted=len(clinical), clients=n_cl, decision=decision)
            self.env['ts.notification']._notify(req.user_id, 'data_request_update', '/my/privacy')
        return True
