# Panel v2 S7 (campaigns: group invitation, open link, join, cap, expiry, close). Run ONLY on an eot_ts* clone via odoo-bin shell.
# Never commits. The SMS sender is patched; nothing is sent.
from datetime import timedelta
from unittest.mock import patch

import psycopg2
from odoo import fields
from odoo.exceptions import UserError, ValidationError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=(UserError, ValidationError, psycopg2.IntegrityError)):
    env.flush_all()
    try:
        with env.cr.savepoint():
            fn()
            env.flush_all()
    except exc:
        return True
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, C, G, K = (env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment'], env['ts.panel.client'],
                    env['ts.panel.group'], env['ts.campaign'])
_n = [0]


def puser():
    _n[0] += 1
    login = 'ts.pv2s7.%d@example.invalid' % _n[0]
    return U.create({'name': 'کاربر %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})


def panel(purpose, approved=True):
    org = env['res.partner'].create({'name': 'پنل آزمون S7', 'is_company': True})
    org.write({'is_company': True})
    ws = W.create({'name': org.name, 'purpose': purpose, 'partner_id': org.id})
    if approved:
        ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot'
    return ws


def member(ws, role):
    return M.create({'workspace_id': ws.id, 'user_id': puser().id, 'role': role})


ws = panel('education')
owner, counselor = member(ws, 'owner'), member(ws, 'counselor')
inst = owner.allowed_instruments()[:1]
check('setup: an instrument is allowed', bool(inst))


def client(name, **kw):
    vals = {'workspace_id': ws.id, 'name': name}
    vals.update(kw)
    return C.create(vals)


c1, c2, c3, c4 = client('الف'), client('ب'), client('ج'), client('د')
c5 = client('ه', source='import')
check('setup: the imported client is locked', c5.contact_locked)
grp = G.create({'workspace_id': ws.id, 'name': 'کلاس هفتم'})
grp.client_ids = [(6, 0, (c1 | c2 | c3 | c4 | c5).ids)]
c4.write({'state': 'archived', 'archived_on': fields.Datetime.now()})
busy = A.create({'workspace_id': ws.id, 'instrument_id': inst.id, 'client_id': c3.id, 'invitee_name': c3.name})

# ---- list campaign
camp = K.create({'workspace_id': ws.id, 'name': 'دعوت هفتم', 'instrument_id': inst.id, 'kind': 'list',
                 'created_by_id': owner.id, 'group_ids': [(6, 0, grp.ids)], 'deadline': fields.Date.today() + timedelta(days=10)})
to_invite, skipped = K.ts_targets(grp.client_ids, ws.id, inst.id)
check('INV-5: targets exclude an open invitation, a locked and an archived client',
      to_invite == c1 | c2 and skipped['busy'] == c3 and skipped['locked'] == c5 and skipped['archived'] == c4,
      str([len(v) for v in skipped.values()]))
created, sk = camp.ts_launch(grp.client_ids)
check('INV-5: one invitation per eligible client, tied to the campaign', len(created) == 2 and set(created.client_id.ids) == {c1.id, c2.id}
      and all(a.campaign_id == camp for a in created))
check('INV-5: the deadline and the expiry follow the campaign', all(a.deadline == camp.deadline and a.expires_at for a in created))
check('INV-5: no SMS without the attestation', not created.filtered(lambda a: a.sms_consent))
created2, _ = camp.ts_launch(grp.client_ids)
check('INV-5: launching again creates no duplicate open invitation', not created2 and A.search_count([('campaign_id', '=', camp.id)]) == 2)
check('INV-9: counts per state', camp.counts()['invited'] == 2 and sum(camp.counts().values()) == 2)
check('INV-9: a visibility domain narrows the counts', sum(camp.counts([('id', '=', 0)]).values()) == 0)

# ---- locked clients cannot be invited even directly
check('P20: a locked client cannot be put in a campaign by the model', not K.ts_targets(c5, ws.id, inst.id)[0])

# ---- sms
phone_client = client('تلفن', phone='09125557701')
sms_camp = K.create({'workspace_id': ws.id, 'name': 'پیامکی', 'instrument_id': inst.id, 'kind': 'list', 'created_by_id': owner.id,
                     'send_sms': True, 'remind': True})
check('the SMS tick is stored with the attestation', sms_camp.sms_consent_attested)
sent = []
with patch.object(type(A), '_ts_send_invite_sms', autospec=True, side_effect=lambda self: sent.append(self.id) if (self.sms_consent and self.invitee_phone) else None):
    made, _ = sms_camp.ts_launch(phone_client | client('بی‌تلفن'))
check('SMS is tried only for the client with a phone and carries both consents',
      len(made) == 2 and len(sent) == 1 and made.filtered(lambda a: a.sms_consent).client_id == phone_client
      and made.filtered(lambda a: a.sms_consent).remind_ok, 'made=%d sent=%d consent=%s' % (len(made), len(sent), made.mapped('sms_consent')))
check('the invitation without a phone has no consent flag', not made.filtered(lambda a: not a.client_id.phone and a.sms_consent))
check('a campaign cannot ask for SMS without the attestation', raises(lambda: sms_camp.write({'sms_consent_attested': False})))

# ---- constraints
check('instrument outside the panel kind is refused', raises(lambda: K.create({
    'workspace_id': ws.id, 'name': 'خارج', 'instrument_id': env['ts.instrument'].search([('id', 'not in', owner.allowed_instruments().ids)], limit=1).id,
    'kind': 'list', 'created_by_id': owner.id})))
check('title length is checked', raises(lambda: K.create({'workspace_id': ws.id, 'name': 'x', 'instrument_id': inst.id, 'kind': 'list'})))

# ---- open link
op = K.create({'workspace_id': ws.id, 'name': 'پیوند باز', 'instrument_id': inst.id, 'kind': 'open_link', 'created_by_id': owner.id,
               'open_max': 2})
check('INV-6: the open link has a 32-hex token and a default expiry', len(op.open_token or '') == 32 and op.open_expires_at > fields.Datetime.now())
check('INV-6: the URL carries the token', op.invite_url().endswith('/c/' + op.open_token))
u1, u2, u3 = puser(), puser(), puser()
a1 = op.ts_join(u1, 'نخست')
check('INV-6: joining creates a client of the open_link source and an invitation', a1.campaign_id == op and a1.channel == 'open_link'
      and a1.client_id.source == 'open_link' and a1.client_id.user_id == u1 and a1.client_id.name == 'نخست')
check('INV-6: joining again returns the same invitation', op.ts_join(u1, 'نخست') == a1 and op.joined_count() == 1)
a2 = op.ts_join(u2, 'دوم')
check('INV-6: the second joins', op.joined_count() == 2)
check('INV-6: at the cap a third is told the link is full', raises(lambda: op.ts_join(u3, 'سوم')) and op.open_state() == 'full')
check('INV-6: someone who already joined can still reopen their invitation when full', op.ts_join(u2, 'دوم') == a2)
op.write({'open_max': 5})
op.open_expires_at = fields.Datetime.now() - timedelta(minutes=1)
check('INV-6: an expired link refuses and says so', op.open_state() == 'expired' and raises(lambda: op.ts_join(u3, 'سوم')))
op.open_expires_at = fields.Datetime.now() + timedelta(days=1)
op.ts_close(owner)
check('INV-6: a closed link refuses', op.state == 'closed' and op.open_state() == 'closed' and raises(lambda: op.ts_join(u3, 'سوم')))
check('closing withdraws nothing', a1.state == 'invited' and not a1.withdrawn)
check('closing is audited', env['ts.audit.event'].search_count([('event_type', '=', 'campaign.close'), ('res_id', '=', op.id)]) == 1)
op.ts_close(owner)
check('closing twice is harmless', env['ts.audit.event'].search_count([('event_type', '=', 'campaign.close'), ('res_id', '=', op.id)]) == 1)
check('the cap is limited', raises(lambda: K.create({'workspace_id': ws.id, 'name': 'سقف', 'instrument_id': inst.id, 'kind': 'open_link',
                                                      'created_by_id': owner.id, 'open_max': 501})))
check('names with one character are refused on join', raises(lambda: K.create({
    'workspace_id': ws.id, 'name': 'نام', 'instrument_id': inst.id, 'kind': 'open_link', 'created_by_id': owner.id, 'open_max': 3}).ts_join(puser(), 'x')))

# ---- an account that already has a client reuses it; a second open invitation is not created
op2 = K.create({'workspace_id': ws.id, 'name': 'دوباره', 'instrument_id': inst.id, 'kind': 'open_link', 'created_by_id': owner.id, 'open_max': 5})
u4 = puser()
own_client = client('حساب‌دار', user_id=u4.id)
mine = A.create({'workspace_id': ws.id, 'instrument_id': inst.id, 'client_id': own_client.id, 'invitee_name': own_client.name})
got = op2.ts_join(u4, 'حساب‌دار')
check('INV-6: an account with an open invitation for the instrument gets that invitation, not a second one', got == mine and not mine.campaign_id
      and A.search_count([('client_id', '=', own_client.id)]) == 1)
u5 = puser()
l_client = client('قفل', user_id=u5.id, source='import')
check('P20: an account tied to a locked client cannot join', raises(lambda: op2.ts_join(u5, 'قفل')))

# ---- gated panel
gws = panel('employment', approved=False)
gowner = member(gws, 'hr_admin')
ginst = gowner.allowed_instruments()[:1]
gc = K.create({'workspace_id': gws.id, 'name': 'در انتظار', 'instrument_id': ginst.id, 'kind': 'open_link', 'created_by_id': gowner.id, 'open_max': 3})
check('a gated panel cannot take joins', raises(lambda: gc.ts_join(puser(), 'سازمانی')))
gl = K.create({'workspace_id': gws.id, 'name': 'گروهی', 'instrument_id': ginst.id, 'kind': 'list', 'created_by_id': gowner.id})
check('a gated panel cannot launch a list campaign', raises(lambda: gl.ts_launch(C.create({'workspace_id': gws.id, 'name': 'ز'}))))

# ---- other panel's clients are ignored
other = panel('education')
oc = C.create({'workspace_id': other.id, 'name': 'دیگری'})
camp3 = K.create({'workspace_id': ws.id, 'name': 'مرز', 'instrument_id': inst.id, 'kind': 'list', 'created_by_id': owner.id})
check('clients of another panel are never invited', not camp3.ts_launch(oc)[0])

# ---- permissions
check('invites:bulk is held by owner and counselor, not by the others', all(m.has_perm('invites:bulk') for m in (owner, counselor)))

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
