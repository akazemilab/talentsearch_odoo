"""Panel v2 permission core (05_permissions_matrix.md).

Layer 1: ROLE_PERMS (role -> permissions, per panel purpose).
Layer 3: attribute conditions A1-A5b in ``member.perms()``.
Layer 2 (which client) lives in ``member.can_see`` (assignment.py) and ``result_level`` there.

Deny by default; an unknown permission string raises ValueError (a programming error must not pass silently).
"""
from odoo import fields, models

PURPOSE_CODE = {'education': 'edu', 'employment': 'emp', 'clinical': 'clin', 'benefits': 'ben'}
ALL_ROLES = ('owner', 'admin', 'counselor', 'clinic_director', 'clinician', 'hr_admin', 'hiring_manager',
             'reviewer', 'benefit_admin')

# The table of section 2. A role token may carry a purpose: "owner:emp" = only in employment panels.
_TABLE = {
    'panel:view': 'owner admin counselor clinic_director clinician hr_admin hiring_manager reviewer',
    'panel:profile': 'owner clinic_director hr_admin',
    'panel:settings': 'owner',
    'panel:transfer': 'owner',
    'panel:close': 'owner',
    'members:read': 'owner admin clinic_director hr_admin',
    'members:invite': 'owner clinic_director hr_admin',
    'members:manage': 'owner',
    'members:add_owner': 'owner',
    'clients:read_all': 'owner admin clinic_director hr_admin reviewer',
    'clients:read_own': 'owner admin counselor clinic_director clinician hr_admin hiring_manager reviewer',
    'clients:read_unassigned': 'owner admin counselor:edu clinic_director hr_admin reviewer',
    'clients:write': 'owner admin counselor clinic_director clinician hr_admin hiring_manager',
    'clients:assign': 'owner admin clinic_director hr_admin',
    'clients:be_responsible': 'owner counselor clinic_director clinician hr_admin hiring_manager',
    'clients:archive': 'owner admin clinic_director hr_admin',
    'clients:merge': 'owner admin clinic_director hr_admin',
    'clients:import': 'owner admin counselor clinic_director hr_admin',
    'clients:export': 'owner admin clinic_director hr_admin',
    'groups:manage': 'owner admin counselor clinic_director hr_admin',
    'invites:create': 'owner admin counselor clinic_director clinician hr_admin hiring_manager',
    'invites:bulk': 'owner admin counselor clinic_director hr_admin',
    'invites:manage': 'owner admin counselor clinic_director clinician hr_admin hiring_manager',
    'results:summary': 'owner:emp hr_admin hiring_manager reviewer',
    'results:education': 'owner:edu counselor',
    'results:clinical': 'owner:clin clinic_director clinician',
    'results:export': 'owner:edu owner:emp hr_admin',
    'reports:group': 'owner:edu owner:emp counselor hr_admin reviewer',
    'credits:read': 'owner admin clinic_director hr_admin',
    'audit:read': 'owner',
    'audit:export': 'owner',
    'support:view': 'owner',
    'help:view': 'owner admin counselor clinic_director clinician hr_admin hiring_manager reviewer',
}
ALL_PERMS = frozenset(_TABLE)


def _build():
    out = {}
    for purpose, code in PURPOSE_CODE.items():
        for role in ALL_ROLES:
            token_role = 'admin' if role == 'benefit_admin' else role   # benefit_admin works exactly like admin
            granted = set()
            for perm, tokens in _TABLE.items():
                for t in tokens.split():
                    r, _, only = t.partition(':')
                    if r == token_role and (not only or only == code):
                        granted.add(perm)
            out[(role, purpose)] = frozenset(granted)
    return out


ROLE_PERMS = _build()


def role_has(role, purpose, perm):
    """Role table only, before any attribute condition (used where a state of the person must not matter)."""
    if perm not in ALL_PERMS:
        raise ValueError('unknown permission %r' % perm)
    return perm in ROLE_PERMS.get((role, purpose), frozenset())


def roles_with(perm, purpose=None):
    purposes = [purpose] if purpose else list(PURPOSE_CODE)
    return {r for r in ALL_ROLES for p in purposes if role_has(r, p, perm)}


GATED_REFUSED = frozenset({'invites:create', 'invites:bulk', 'clients:import'})


class TsWorkspaceMember(models.Model):
    _inherit = 'ts.workspace.member'

    def _ts_unverified_pro(self):
        """A clinician or clinic director whose professional verification is not recorded (A5)."""
        self.ensure_one()
        return self.role in ('clinician', 'clinic_director') and self.verification_state != 'verified'

    def perms(self):
        """Effective permission set after the attribute conditions A1-A5b of the matrix."""
        self.ensure_one()
        if not self.active:                                                    # A1
            return frozenset()
        ws = self.workspace_id
        if ws.state in ('suspended', 'closed'):                               # A2
            out = {'panel:view'}
            if ws.state == 'closed' and self.role == 'owner' and 'closed_on' in ws._fields and ws.closed_on:
                if (fields.Datetime.now() - ws.closed_on).days <= 90:
                    out.add('clients:export')
            return frozenset(out)
        if ws.state == 'draft':                                               # A3
            return frozenset({'panel:view'} | ({'panel:settings'} if self.role == 'owner' else set()))
        perms = set(ROLE_PERMS.get((self.role, ws.purpose), frozenset()))
        if ws.gated:                                                          # A4
            perms -= GATED_REFUSED
        if self._ts_unverified_pro():                                         # A5
            return frozenset({'panel:view', 'help:view'})
        if self.role == 'owner' and ws.purpose == 'clinical':                 # A5b
            if not (self.owner_practices and self.verification_state == 'verified'):
                perms.discard('results:clinical')
        return frozenset(perms)

    def has_perm(self, perm):
        self.ensure_one()
        if perm not in ALL_PERMS:
            raise ValueError('unknown permission %r' % perm)
        return perm in self.perms()
