"""clin7 (owner 2026-10-14, Sepehr hand-over): an office sends the invitations, the therapist reads the report.

A clinical panel with exactly ONE therapist (a member whose role can be responsible, can act; an owner only when
practising) gives every new client to that therapist when the creator cannot be responsible himself (the office, a
non-practising owner, the permanent link). With two or more therapists nothing is guessed: the one-screen invitation asks.
"""
from odoo import models

from odoo.addons.ts_org.models.assignment import RESPONSIBLE_ROLES


class TsWorkspaceMemberClin7(models.Model):
    _inherit = 'ts.workspace.member'

    def ts_clin7_therapists(self, workspace):
        ws = workspace.sudo()
        if ws.purpose != 'clinical':
            return self.browse()
        return ws.member_ids.filtered(
            lambda m: m.active and m.role in RESPONSIBLE_ROLES and m.can_act() and (m.role != 'owner' or m.owner_practices))

    def ts_panel_default_responsible(self, workspace_id, user_id):
        res = super().ts_panel_default_responsible(workspace_id, user_id)
        if res:
            return res
        ws = self.env['ts.workspace'].sudo().browse(int(workspace_id))
        ts = self.ts_clin7_therapists(ws)
        return ts if len(ts) == 1 else self.browse()
