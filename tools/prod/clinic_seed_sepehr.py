# Clinic phase 2: Sepehr workspace setup (docs/clinic/01_architecture.md section 10). Run inside `odoo shell`:
#   ... odoo-bin shell -d eot_tsNN < tools/prod/clinic_seed_sepehr.py
# Needs ts_battery installed. Idempotent: a second run creates nothing and prints the same counts.
# Env (pass through `sudo -u odoo env VAR=... odoo-bin shell`):
#   TS_ALLOW_LIVE=1          allow a database whose name does not start with eot_ts (live: only when the owner says so)
#   TS_SEPEHR_OWNER_LOGIN    login of the panel owner (a portal user); required on live. On clones, when absent,
#                            a fictional portal user ts.clinic.owner@example.invalid is created.
#   TS_SEPEHR_PHONES         path of a JSON file [{"name": ..., "phone": ...}] for the 9 counselors; required on live.
#                            On clones, when absent, fictional numbers 09129991001..009 are used.
#   TS_DRY=1                 roll back at the end instead of committing.
# Prints counts only: never phone numbers or names.
import json
import os
import re

from odoo import SUPERUSER_ID, fields

LIVE_OK = os.environ.get('TS_ALLOW_LIVE') == '1'
assert env.cr.dbname.startswith('eot_ts') or LIVE_OK, 'refusing to run outside an eot_ts* clone (set TS_ALLOW_LIVE=1)'
is_clone = env.cr.dbname.startswith('eot_ts')
assert 'ts.battery' in env, 'ts_battery is not installed'

su = env(user=SUPERUSER_ID)
NAME = 'سپهر هیجان اندیش'
BATTERIES = ['BAT-INTAKE-1', 'BAT-DISTRESS-1', 'BAT-LIFE-1', 'BAT-COUPLE-1', 'BAT-CHILD-1', 'BAT-WORK-1']
SINGLES = ['inventory_013', 'inventory_035', 'inventory_006']
COUNSELORS = [  # (name, role); the first one directs the clinic
    ('ناصرالدین کاظمی حقیقی', 'clinic_director'),
    ('مهوش طالبی', 'clinician'),
    ('زینت السادات میرطاهری', 'clinician'),
    ('راضیه جهانشاهی', 'clinician'),
    ('مریم ملک', 'clinician'),
    ('محمد صادق علیخانی', 'clinician'),
    ('نجده مساعدیان', 'clinician'),
    ('طیبه مالمیر', 'clinician'),
    ('محیا سامت', 'clinician'),
]


def norm_name(s):
    s = (s or '').replace('ي', 'ی').replace('ك', 'ک').replace('‌', '')
    return re.sub(r'\s+', '', s)


# ------------------------------------------------------------------ 1. organization
Partner = su['res.partner']
org = Partner.search([('name', '=', NAME), ('is_company', '=', True)], limit=1)
created = {'partner': 0, 'workspace': 0, 'owner_user': 0, 'owner_member': 0, 'invites': 0}
if not org:
    org = Partner.create({'name': NAME, 'is_company': True})
    org.write({'is_company': True})   # Odoo recomputes is_company on create
    created['partner'] = 1

# ------------------------------------------------------------------ 2. catalog
bats = su['ts.battery'].search([('code', 'in', BATTERIES)])
missing_b = sorted(set(BATTERIES) - set(bats.mapped('code')))
assert not missing_b, 'starter batteries missing: %s' % missing_b
unpublished = bats.filtered(lambda b: b.state != 'published')
assert not unpublished, 'starter batteries not published: %s' % unpublished.mapped('code')
singles = su['ts.instrument'].search([('code', 'in', SINGLES), ('state', '=', 'published')])
assert len(singles) == len(SINGLES), 'single instruments missing or not published: %s' % (
    sorted(set(SINGLES) - set(singles.mapped('code'))))
catalog_insts = bats.mapped('line_ids.instrument_id') | singles

# ------------------------------------------------------------------ 3. workspace
W = su['ts.workspace']
ws = W.search([('partner_id', '=', org.id), ('purpose', '=', 'clinical')], limit=1)
if not ws:
    ws = W.create({'name': NAME, 'purpose': 'clinical', 'partner_id': org.id, 'state': 'pilot',
                   'escalation_contact_id': org.id, 'data_contact_id': org.id})
    created['workspace'] = 1
vals = {}
if ws.catalog_mode != 'granted':
    vals['catalog_mode'] = 'granted'
if catalog_insts - ws.catalog_instrument_ids:
    vals['catalog_instrument_ids'] = [fields.Command.link(i.id) for i in catalog_insts - ws.catalog_instrument_ids]
if bats - ws.catalog_battery_ids:
    vals['catalog_battery_ids'] = [fields.Command.link(b.id) for b in bats - ws.catalog_battery_ids]
if not ws.escalation_contact_id:
    vals['escalation_contact_id'] = org.id
if ws.state == 'draft':
    vals['state'] = 'pilot'
if vals:
    ws.write(vals)
if ws.gated:
    ws.action_approve()       # superuser is in ts_core.group_ts_manager (group data adds base.user_root)
assert not ws.gated and ws.state in ('pilot', 'active'), 'workspace not approved / not running'

# ------------------------------------------------------------------ 4. owner
login = os.environ.get('TS_SEPEHR_OWNER_LOGIN')
U = su['res.users'].with_context(no_reset_password=True)
if login:
    owner_user = U.search([('login', '=', login)], limit=1)
    assert owner_user, 'TS_SEPEHR_OWNER_LOGIN: no such user'
else:
    assert is_clone, 'TS_SEPEHR_OWNER_LOGIN is required outside a clone'
    login = 'ts.clinic.owner@example.invalid'
    owner_user = U.search([('login', '=', login)], limit=1)
    if not owner_user:
        owner_user = U.create({'name': 'مالک آزمایشی کلینیک', 'login': login, 'email': login,
                               'group_ids': [fields.Command.set([env.ref('base.group_portal').id])]})
        created['owner_user'] = 1
assert owner_user.share, 'the panel owner must be a portal user'
M = su['ts.workspace.member']
owner = M.search([('workspace_id', '=', ws.id), ('user_id', '=', owner_user.id), ('active', '=', True)], limit=1)
if not owner:
    owner = M.create({'workspace_id': ws.id, 'user_id': owner_user.id, 'role': 'owner'})
    created['owner_member'] = 1
assert owner.role == 'owner', 'that user already holds another role in this panel'
assert owner.has_perm('members:invite'), 'owner cannot invite colleagues (panel state?)'

# ------------------------------------------------------------------ 5. colleague invites (prepared, never sent)
path = os.environ.get('TS_SEPEHR_PHONES')
if path:
    rows = json.load(open(path, encoding='utf-8'))
    by_name = {norm_name(r.get('name')): r.get('phone') for r in rows}
    phones = [by_name.get(norm_name(n)) for n, _r in COUNSELORS]
    assert all(phones), 'TS_SEPEHR_PHONES: %d of %d counselors have no phone' % (
        sum(1 for p in phones if not p), len(COUNSELORS))
else:
    assert is_clone, 'TS_SEPEHR_PHONES is required outside a clone'
    phones = ['09129991%03d' % (n + 1) for n in range(len(COUNSELORS))]

from odoo.addons.ts_org.models.panel import norm_phone   # noqa: E402

I = su['ts.member.invite']
skipped = renewed = 0
for (cname, role), raw in zip(COUNSELORS, phones):
    phone = norm_phone(raw)
    assert phone, 'a phone number in TS_SEPEHR_PHONES is not a valid Iranian mobile'
    existing = I.search([('workspace_id', '=', ws.id), ('phone', '=', phone), ('state', 'in', ('pending', 'accepted'))],
                        limit=1)
    if existing.state == 'pending' and existing.expires_at < fields.Datetime.now():
        existing.ts_resend(owner)       # revokes the expired link and issues a fresh 7-day one for the same person
        renewed += 1
        continue
    if existing:
        skipped += 1
        continue
    I.ts_create(owner, role, phone_raw=phone)
    created['invites'] += 1

# ------------------------------------------------------------------ report (counts only)
pending = I.search_count([('workspace_id', '=', ws.id), ('state', '=', 'pending')])
print('SEPEHR created=%s existing_invites=%d renewed_invites=%d' % (created, skipped, renewed))
print('SEPEHR workspace mode=%s gated=%s state=%s batteries=%d instruments=%d members=%d pending_invites=%d' % (
    ws.catalog_mode, ws.gated, ws.state, len(ws.catalog_battery_ids), len(ws.catalog_instrument_ids),
    len(ws.member_ids.filtered('active')), pending))
print('SEPEHR owner allowed: instruments=%d batteries=%d' % (len(owner.allowed_instruments()), len(owner.allowed_batteries())))
if os.environ.get('TS_DRY') == '1':
    env.cr.rollback()
    print('SEPEHR dry run: rolled back')
else:
    env.cr.commit()
    print('SEPEHR committed')
