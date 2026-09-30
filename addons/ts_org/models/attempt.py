from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .assignment import RESPONSIBLE_ROLES


class TsAttempt(models.Model):
    _inherit = 'ts.attempt'

    responsible_id = fields.Many2one(
        'ts.workspace.member', 'کارشناس مسئول', index=True, ondelete='set null',
        help='برای نتیجه‌های واردشده که دعوتی ندارند؛ برای دعوت‌های وب، کارشناس مسئولِ دعوت ملاک است.')

    @api.constrains('responsible_id', 'workspace_id')
    def _check_responsible(self):
        for at in self:
            r = at.responsible_id
            if r and (r.workspace_id != at.workspace_id or not r.active or r.role not in RESPONSIBLE_ROLES):
                raise ValidationError('کارشناس مسئول باید عضو فعال همین فضای کاری با نقش کارشناس باشد.')

    def write(self, vals):
        old = {a.id: a.responsible_id.id for a in self} if 'responsible_id' in vals else {}
        res = super().write(vals)
        for a in self:
            if a.id in old and old[a.id] != a.responsible_id.id:
                self.env['ts.audit.event'].log('attempt.responsible_change', a, workspace=a.workspace_id,
                                               old=old[a.id] or False, new=a.responsible_id.id or False)
        return res

    def ts_org_assignment(self):
        """The workspace invitation behind this attempt (owner-only use in the report)."""
        self.ensure_one()
        return self.env['ts.assignment'].sudo().search(
            [('attempt_id', '=', self.id), ('user_id', '=', self.user_id.id)], limit=1)

    def ts_org_visible_to(self, member):
        """Education workspaces: may this member (owner/counselor of the institute)
        open the participant report of this attempt? Answers are never included.

        Imported historical results of the workspace are visible to its usable
        members; web attempts only through a released assignment with sharing on."""
        self.ensure_one()
        ws = member.workspace_id
        if ws.purpose != 'education' or not member.can_act() or self.workspace_id != ws:
            return False
        if self.state != 'done':
            return False
        if self.source == 'import':
            return member.can_see(self)
        a = self.env['ts.assignment'].sudo().search(
            [('attempt_id', '=', self.id), ('workspace_id', '=', ws.id)], limit=1)
        return bool(a) and a.visible_results(member)[0] == 'education'

    def action_submit(self, *args, **kwargs):
        res = super().action_submit(*args, **kwargs)
        Usage = self.env['ts.usage.event'].sudo()
        for at in self:
            if res and at.state == 'done' and at.workspace_id and at.source != 'import' \
                    and not Usage.search_count([('attempt_id', '=', at.id)]):
                a = self.env['ts.assignment'].sudo().search([('attempt_id', '=', at.id)], limit=1)
                Usage.create({'workspace_id': at.workspace_id.id, 'attempt_id': at.id, 'assignment_id': a.id or False})
        return res
