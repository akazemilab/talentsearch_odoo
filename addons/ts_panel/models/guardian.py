"""Minors and guardian consent (S16, GRD-1 .. GRD-7; 05_permissions_matrix.md section 5 step 7).

The school (the panel) attests that it holds the guardian's consent (decision D2). The attestation is a ledger row of kind
`guardian_attest` given by a panel member, never by the guardian. A minor's result stays at 'status' level until it exists.
"""
from odoo import fields, models

ATTEST_VERSION = 'TS-GUARDIAN-1405-07-v1'


class TsPanelClientGuardian(models.Model):
    _inherit = 'ts.panel.client'

    guardian_consent = fields.Selection([('none', 'ثبت نشده'), ('attested', 'تأیید مؤسسه'), ('confirmed', 'تأیید خود ولی')],
                                        'رضایت ولی', default='none', required=True)
    guardian_consent_on = fields.Datetime('زمان ثبت رضایت ولی')

    def ts_needs_guardian(self):
        """True for a minor whose guardian consent is not on record."""
        self.ensure_one()
        return self.age_group == 'minor' and self.guardian_consent == 'none'

    def ts_attest_guardian(self, member):
        """The panel member says the guardian's consent is held. Writes the ledger and one audit event (ids only)."""
        Rec = self.env['ts.consent.record']
        for c in self.sudo():
            if c.guardian_consent != 'none' or c.age_group != 'minor':
                continue
            c.write({'guardian_consent': 'attested', 'guardian_consent_on': fields.Datetime.now()})
            Rec._log('guardian_attest', member.user_id, workspace=c.workspace_id, version=ATTEST_VERSION, method='attestation',
                     given_as='panel_member', client=c)
            self.env['ts.audit.event'].sudo().log('guardian.attest', c, workspace=c.workspace_id, member=member)


class TsAssignmentGuardian(models.Model):
    _inherit = 'ts.assignment'

    def _ts_guardian_blocks(self):
        self.ensure_one()
        c = self.client_id
        return bool(c and c.age_group == 'minor' and c.guardian_consent == 'none')

    def action_accept(self, *a, **kw):
        res = super().action_accept(*a, **kw)
        for rec in self:
            c = rec.client_id
            if c and rec.instrument_id.audience in ('child', 'adolescent') and rec.user_id and c.user_id == rec.user_id:
                c.sudo().account_is_guardian = True                                       # GRD-7
        return res


class TsCampaignGuardian(models.Model):
    _inherit = 'ts.campaign'

    guardian_attested_by_id = fields.Many2one('ts.workspace.member', 'تأییدکنندهٔ رضایت ولی', ondelete='set null')
    guardian_attested_on = fields.Datetime('زمان تأیید رضایت ولی')


class TsAttemptConsentLedger(models.Model):
    _inherit = 'ts.attempt'

    def give_consent(self, research=False, role='self', subject=None):
        was = {a.id: a.state for a in self}
        res = super().give_consent(research=research, role=role, subject=subject)
        Rec = self.env['ts.consent.record']
        for a in self:
            if was.get(a.id) == 'consent' and a.state == 'in_progress':
                user = self.env.user
                Rec._log('service', user, attempt=a, workspace=a.workspace_id, version=a.consent_version, method='checkbox',
                         given_as='guardian' if role == 'guardian' else 'self', client=a.client_id)
                if research:
                    Rec._log('research', user, attempt=a, workspace=a.workspace_id, version=a.consent_version, method='checkbox',
                             given_as='guardian' if role == 'guardian' else 'self', client=a.client_id)
        return res
