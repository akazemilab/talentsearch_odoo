# Panel v2 S15 (consent ledger, up to 3 shares, my data). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits.
import io
import json
import zipfile
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn):
    try:
        with env.cr.savepoint():
            fn()
    except Exception:
        return True
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, T = (env[m] for m in ('ts.workspace', 'ts.workspace.member', 'ts.assignment', 'ts.attempt'))
Inst = env['ts.instrument']
C, DR = env['ts.consent.record'], env['ts.data.request']
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s15.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id})
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def finish(att):
    att.give_consent()
    for it in att.active_items():
        att.save_answer(it.id, 1 + it.id % 5)
    att.action_submit()
    return att


inst = Inst.search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)
edu = [panel('education', 'پنل S15 آموزشی %d' % i) for i in range(1, 5)]
emp = panel('employment', 'پنل S15 کاری')
me, other = puser(), puser()


def own_attempt(user):
    at = T.create({'user_id': user.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
    return finish(at)


at = own_attempt(me)
at_other = own_attempt(other)

# ---- consent ledger is append-only (PRV-1)
row = C._log('share', me, attempt=at, workspace=edu[0], level='summary')
check('a ledger row is written', row and row.kind == 'share' and row.user_id == me and row.level == 'summary')
check('a row cannot be created by hand', raises(lambda: C.sudo().create({'kind': 'share'})))
check('a row cannot be changed', raises(lambda: row.write({'level': 'none'})))
check('a row cannot be deleted', raises(lambda: row.unlink()))
check('a row holds no name, phone or free text field', not ({'name', 'phone', 'note', 'text', 'email'} & set(C._fields)))

# ---- up to three panels (D3)
before = C.search_count([('user_id', '=', me.id), ('kind', '=', 'share')])
s1 = A.ts_share_attempt(at, edu[0].code, me)
s2 = A.ts_share_attempt(at, edu[1].code, me)
s3 = A.ts_share_attempt(at, edu[2].code, me)
check('three panels can each receive the same result', len({s1.id, s2.id, s3.id}) == 3 and all(s.share_level == 'summary' for s in (s1, s2, s3)))
check('each share wrote a ledger row', C.search_count([('user_id', '=', me.id), ('kind', '=', 'share')]) == before + 3)
check('a fourth panel is refused', raises(lambda: A.ts_share_attempt(at, edu[3].code, me)))
check('the same panel twice is refused', raises(lambda: A.ts_share_attempt(at, edu[0].code, me)))
check('someone else cannot share my result', raises(lambda: A.ts_share_attempt(at, edu[3].code, other)))
check('the report block lists all three shares', len(at.ts_shares()) == 3)

# ---- revoke and re-share
rv_before = C.search_count([('user_id', '=', me.id), ('kind', '=', 'share_revoke')])
s2.action_revoke_share(me)
check('revoking writes a share_revoke row', C.search_count([('user_id', '=', me.id), ('kind', '=', 'share_revoke')]) == rv_before + 1)
check('the revoked panel sees nothing', s2.share_level == 'none')
s4 = A.ts_share_attempt(at, edu[3].code, me)
check('after a revoke a free slot is open for another panel', s4.share_level == 'summary' and s4.workspace_id == edu[3])
s1.action_revoke_share(me)
back = A.ts_share_attempt(at, edu[0].code, me)
check('re-sharing with a panel revoked earlier reuses the same record', back.id == s1.id and back.share_level == 'summary')
n_rv = C.search_count([('user_id', '=', me.id), ('kind', '=', 'share_revoke')])
s1.action_revoke_share(me)
s1.action_revoke_share(me)
check('revoking twice writes one row only', C.search_count([('user_id', '=', me.id), ('kind', '=', 'share_revoke')]) == n_rv + 1)
check('ts_org_assignment prefers an active share', at.ts_org_assignment().share_level != 'none')
check('the level word names what the panel sees', 'بدون پاسخ‌های خام' in s3.ts_level_word() and 'لغو' in s2.ts_level_word())

ICP = env['ir.config_parameter'].sudo()
ICP.set_str('ts_panel.share_max_panels', '1')
at3 = own_attempt(me)
A.ts_share_attempt(at3, edu[0].code, me)
check('the limit is a setting (1 panel)', raises(lambda: A.ts_share_attempt(at3, edu[1].code, me)))
ICP.set_str('ts_panel.share_max_panels', '3')

# ---- an accepted invitation writes a share row; declining the share writes none
n0 = C.search_count([('kind', '=', 'share')])
a1 = A.sudo().create({'workspace_id': emp.id, 'instrument_id': inst.id, 'invitee_name': 'دعوت S15 یک'})
a1.action_accept(puser(), share=True)
check('accepting with sharing ticked writes a share row', C.search_count([('kind', '=', 'share')]) == n0 + 1)
a2 = A.sudo().create({'workspace_id': emp.id, 'instrument_id': inst.id, 'invitee_name': 'دعوت S15 دو'})
a2.action_accept(puser(), share=False)
check('accepting without sharing writes none', C.search_count([('kind', '=', 'share')]) == n0 + 1)

# ---- data requests (ACC-5, ACC-6)
req = DR.ts_open(me, 'export')
job = req.job_id
check('an export request runs a job to the end', req.state == 'done' and job.state == 'done' and job.kind == 'data_export')
check('the job expires in about 24 hours', job.expires_at and timedelta(hours=23) < job.expires_at - fields.Datetime.now() <= timedelta(hours=24, minutes=1))
check('the owner may download it, nobody else', job.can_download_own(me) and not job.can_download_own(other))
from odoo.addons.ts_panel.models.job import att_bytes
z = zipfile.ZipFile(io.BytesIO(att_bytes(job.result_attachment_id)))
check('the file has one JSON and one CSV', sorted(z.namelist()) == ['my-data.csv', 'my-data.json'])
data = json.loads(z.read('my-data.json').decode('utf-8'))
check('it holds my profile and my attempts', data['profile']['login'] == me.login and any(a['id'] == at.id for a in data['attempts']))
check('it does not hold the other person\'s attempt', not any(a['id'] == at_other.id for a in data['attempts']))
check('it holds my shares and consents', len(data['shares']) >= 3 and any(c['kind'] == 'share' for c in data['consents']))
text = z.read('my-data.json').decode('utf-8') + z.read('my-data.csv').decode('utf-8')
check('it never holds an access token, a score key or an item text', 'access_token' not in text and 'reverse' not in text and 'key_json' not in text)
job.expires_at = fields.Datetime.now() - timedelta(minutes=1)
check('an expired file is refused', not job.can_download_own(me))
env['ts.job']._cron_expire_jobs()
check('the expiry cron removes the file', job.state == 'expired' and not job.result_attachment_id)
check('a second export request is allowed', DR.ts_open(me, 'export').state == 'done')

er = DR.ts_open(me, 'erase')
check('an erase request is only recorded, due in 30 days', er.state == 'new' and (er.due_on - fields.Date.today()).days == 30 and not er.job_id)
check('nothing was erased by it', at.state == 'done' and at.exists() and s3.share_level == 'summary')
check('a second open erase request is refused', raises(lambda: DR.ts_open(me, 'erase')))
check('the other person has no request of mine', not DR.sudo().search_count([('user_id', '=', other.id)]))
check('an unknown request kind is refused', raises(lambda: DR.ts_open(me, 'sell')))
check('the audit trail records the request without content', env['ts.audit.event'].sudo().search_count([('event_type', '=', 'data.request'), ('res_id', '=', er.id)]) == 1)

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
