# onb2 (release 2 of onboarding): one-tap invitations (delivery proof, scope, device binding, short codes, fairness at
# the end, minors on one screen) and test first for individuals (guest attempts, claim, 48-hour clean-up, funnel).
# Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits; never sends an SMS or an e-mail (every send path below
# is patched to report success without reaching a provider).
import importlib.util
import os
import re
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.modules.module import get_module_path

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc=Exception, text=None):
    try:
        with env.cr.savepoint():
            fn()
    except exc as e:
        return text is None or text in str(e.args[0] if e.args else e)
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, A, Att = env['ts.workspace'], env['ts.assignment'].sudo(), env['ts.attempt'].sudo()
_n = [0]
PH = {'a': '09126654381', 'b': '09126654382', 'c': '09126654383'}


def puser(phone=None):
    _n[0] += 1
    login = 'ts.onb2.orm.%d@example.invalid' % _n[0]
    u = U.create({'name': 'آزمون onb2 %d' % _n[0], 'login': login, 'email': login, 'group_ids': [(6, 0, [portal.id])]})
    if phone:
        u.partner_id.write({'ts_phone': phone, 'ts_phone_verified_at': fields.Datetime.now()})
    return u


def bo_panel(purpose, name):
    org = env['res.partner'].create({'name': name, 'is_company': True})
    ws = W.create({'name': name, 'purpose': purpose, 'partner_id': org.id,
                   **({'escalation_contact_id': org.id} if purpose == 'clinical' else {})})
    ws.state = 'active'
    return ws


def load(module, rel):
    spec = importlib.util.spec_from_file_location('onb2_mod_%d' % len(results), os.path.join(get_module_path(module), rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


Inst = env['ts.instrument'].sudo()
adult = Inst.search([('state', '=', 'published'), ('audience', '=', 'adult'), ('purpose', '!=', 'employment'),
                     ('code', '!=', 'TALENT-INV-15')], order='id', limit=1)
wcl = bo_panel('clinical', 'مرکز onb2 ORM')
for p in PH.values():
    env['res.partner'].with_context(active_test=False).search([('ts_phone', '=', p)]).write({'ts_phone': False})
    for u in U.with_context(active_test=False).search([('login', '=', p)]):
        u.write({'login': 'old.onb2.%d' % u.id})

# ================================================================ D. delivery proof (the send paths report it)
from odoo.addons.ts_sms.models.assignment import TsAssignment as SmsAsg
from odoo.addons.ts_hire.models.mail import TsAssignmentMail
a1 = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'مریم آزمایشی onb2'})
check('D01 a new invitation is «manual» until a message reports success', a1.delivered_via == 'manual' and not a1.delivered_phone)
a1.write({'invitee_phone': PH['a'], 'sms_consent': True})
with patch.object(SmsAsg, '_ts_send_invite_sms', lambda self: True):
    a1._ts_send_invite_sms()
check('D02 a successful invitation SMS marks the invitation «sms» with the number it reached',
      a1.delivered_via == 'sms' and a1.delivered_phone == PH['a'], (a1.delivered_via, a1.delivered_phone))
a2 = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'داوطلب ایمیلی onb2',
               'invitee_email': 'Cand.ONB2@Example.invalid'})
with patch.object(TsAssignmentMail, '_ts_send_invite_email', lambda self: True):
    a2._ts_send_invite_email()
    a1.invitee_email = 'other.onb2@example.invalid'
    a1._ts_send_invite_email()
check('D03 a successful e-mail marks «email» (address lower-cased); an SMS proof stays the stronger one',
      a2.delivered_via == 'email' and a2.delivered_email == 'cand.onb2@example.invalid'
      and a1.delivered_via == 'sms' and a1.delivered_email == 'other.onb2@example.invalid')
a3 = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'بی‌پیامک onb2', 'invitee_phone': PH['b']})
with patch.object(SmsAsg, '_ts_send_invite_sms', lambda self: False):
    a3.sms_consent = True
    a3._ts_send_invite_sms()
check('D04 a failed SMS proves nothing (still «manual»), the typed number stays the invitation\'s number',
      a3.delivered_via == 'manual' and a3.ts_invite_phone() == PH['b'] and a3.ts_proof() == (None, None))
from odoo.addons.ts_panel.models.notify import TsAssignmentNotify
with patch.object(TsAssignmentNotify, '_ts_do_reminder', lambda self: {'sms'}):
    a3._ts_do_reminder()
check('D05 a reminder SMS that went out is a proof too', a3.delivered_via == 'sms' and a3.delivered_phone == PH['b'])

# ================================================================ M. who matches the invitation
ua, ub = puser(PH['a']), puser()
ue = U.create({'name': 'ایمیلی onb2', 'login': 'cand.onb2@example.invalid', 'email': 'cand.onb2@example.invalid',
               'group_ids': [(6, 0, [portal.id])]})
a4 = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'پیوند onb2'})
check('M01 the SMS number: its holder matches, another account does not',
      a1.ts_contact_matches(ua) is True and a1.ts_contact_matches(ub) is False)
check('M02 the e-mail address: its account matches (any letter case), another does not',
      a2.ts_contact_matches(ue) is True and a2.ts_contact_matches(ub) is False)
check('M03 a link without a number or address checks nothing (None)', a4.ts_contact_matches(ub) is None)

# ================================================================ S. short codes
from odoo.addons.ts_brand.models.short import CODE_RE
check('S01 new invitations get a 12-character [a-z0-9] short code', re.fullmatch(r'[a-z0-9]{12}', a4.short_code or ''), a4.short_code)
check('S02 the lookup accepts the old 8 characters and the new 12, nothing else',
      CODE_RE.match('abcd1234') and CODE_RE.match('abcd1234efgh') and not CODE_RE.match('abcd1234ef') and not CODE_RE.match('ABCD1234'))
inv = env['ts.member.invite'].sudo().search([], limit=1)
check('S03 colleague invitations get 12 characters too (new codes)', len(env['ts.member.invite']._ts_new_short_code()) == 12)

# ================================================================ R. rate limits
R = env['ts.rate.hit']
key = 'test:onb2:%d' % a4.id
oks = [R.ts_hit(key, 3, 60) for _ in range(5)]
check('R01 a key is let through up to the limit, then refused', oks == [True, True, True, False, False], oks)
with env.registry.cursor() as c2:       # hits live in their own committed transaction (a 404 must still count)
    c2.execute('UPDATE ts_rate_hit SET at = at - interval %s WHERE key = %s', ['2 minutes', key])
check('R02 after the window the key is let through again', R.ts_hit(key, 3, 60))
key2 = 'test:onb2:rb:%d' % a4.id
try:
    with env.cr.savepoint():
        R.ts_hit(key2, 1, 60)
        raise ValueError('the request fails after the lookup (an unknown code answers 404)')
except ValueError:
    pass
check('R03 a hit counts even when the request itself is rolled back (guessing unknown codes is slowed down too)',
      not R.ts_hit(key2, 1, 60))
with env.registry.cursor() as c2:
    c2.execute("DELETE FROM ts_rate_hit WHERE key LIKE 'test:onb2:%%'")
camp = None
try:
    with env.cr.savepoint():
        camp = env['ts.campaign'].sudo().create({'workspace_id': wcl.id, 'name': 'onb2 پیوند باز', 'instrument_id': adult.id,
                                                 'kind': 'open_link'})
        a_c = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'کلاس onb2', 'campaign_id': camp.id})
except Exception as e:      # noqa: BLE001 - reported by the check below
    camp, a_c = None, str(e)[:120]
check('D06 an invitation made by joining an open link or class code is «campaign» (no proof, the ordinary sign-in)',
      camp and a_c.delivered_via == 'campaign' and a_c.ts_proof() == (None, None), a_c if not camp else a_c.delivered_via)

# ================================================================ C. minors on one screen
from odoo.addons.ts_onboard.controllers.flow import minor_needs, consent_from
C = env['ts.panel.client'].sudo()
minor = C.create({'workspace_id': wcl.id, 'name': 'کودک onb2', 'age_group': 'minor'})
bchild = env['ts.battery'].sudo().search([('code', '=', 'BAT-CHILD-1')], limit=1)
n_adult = minor_needs(A.new({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'x'}))
n_minor = minor_needs(A.new({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'x', 'client_id': minor.id}))
check('C01 an adult instrument for an adult: no tick, the ordinary button', not n_adult['guardian'] and not n_adult['assent'])
check('C02 a minor client answering himself: the guardian tick and the child\'s own button «من هم موافقم»',
      n_minor['guardian'] and n_minor['text'] == 'minor' and n_minor['assent'] and n_minor['minor'])
if bchild:
    first = bchild.ts_first_instrument()
    n_child = minor_needs(A.new({'workspace_id': wcl.id, 'instrument_id': first.id, 'battery_id': bchild.id,
                                 'invitee_name': 'x', 'client_id': minor.id}))
    check('C03 BAT-CHILD-1 for a minor client: the parent answers, one guardian tick, no second assent',
          n_child['guardian'] and n_child['text'] == 'child' and not n_child['assent'] and n_child['role'] == 'guardian')
check('C04 the POST without the required tick is refused; with it, the consent carries the minor flags',
      consent_from({}, A.new({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'x', 'client_id': minor.id})) == 'guardian'
      and consent_from({'guardian_confirm': '1', 'share': '1'},
                       A.new({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'x', 'client_id': minor.id}))['assent'])

# ================================================================ Q. the scope of a session for one invitation
from odoo.addons.ts_onboard.models.ir_http import scope_allows
uq = puser(PH['c'])
aq = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'اسکوپ onb2'})
tq = aq.action_accept(uq, share=True)
other = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'دیگری onb2'})
sc = {'aid': aq.id, 'uid': uq.id, 'phone': PH['c']}
ok_paths = ['/invite/%s' % aq.token, '/invite/%s/accept' % aq.token, '/take/%s' % tq.access_token,
            '/take/%s/answer' % tq.access_token, '/take/%s/task/start' % tq.access_token, '/my/assessments/%s' % tq.id,
            '/my/assessments/%s/pdf' % tq.id, '/i/%s' % aq.short_code, '/web/assets/1/web.assets_frontend.min.css',
            '/web/session/logout', '/signup', '/signup/verify']
bad_paths = ['/my', '/my/assessments', '/my/account', '/my/workspaces', '/my/workspaces/%s' % wcl.id,
             '/invite/%s' % other.token, '/i/%s' % other.short_code, '/take/x%s' % tq.access_token[1:],
             '/my/assessments/%s/share' % tq.id, '/my/assessments/%s' % (tq.id + 100000), '/web', '/odoo', '/assessments',
             '/start', '/', '/my/assessments/battery/%s' % other.id, '/web/login']
check('Q01 a scoped session reaches its invitation, its player, its own result, assets, sign-in and sign-out',
      all(scope_allows(env, sc, p) for p in ok_paths), [p for p in ok_paths if not scope_allows(env, sc, p)])
check('Q02 ...and nothing else: /my, other invitations, panels, the back office, the catalog',
      not any(scope_allows(env, sc, p) for p in bad_paths), [p for p in bad_paths if scope_allows(env, sc, p)])
check('Q03 a scope whose invitation went to another account allows only the open pages',
      not scope_allows(env, dict(sc, uid=ub.id), '/take/%s' % tq.access_token) and scope_allows(env, dict(sc, uid=ub.id), '/signup'))

# ================================================================ G. guest attempts (O3)
starter = Inst.ts_starter()
check('G01 the starter is inventory_002 «فهرست ارجمندی» (17 statements, adult, general, guest-ok)',
      starter.code == 'inventory_002' and starter.ts_guest_ok and starter.active_item_count <= 40 and starter.audience == 'adult',
      (starter.code, starter.active_item_count))
child_inst = Inst.search([('state', '=', 'published'), ('audience', '=', 'child')], limit=1)
emp = Inst.search([('state', '=', 'published'), ('purpose', '=', 'employment')], limit=1)
talent = Inst.search([('code', '=', 'TALENT-INV-15')], limit=1)
check('G02 a child, employment or talent-inventory instrument cannot be guest-ok',
      raises(lambda: child_inst.write({'ts_guest_ok': True}), ValidationError) and raises(lambda: emp.write({'ts_guest_ok': True}), ValidationError)
      and raises(lambda: talent.write({'ts_guest_ok': True}), ValidationError))
pub = env.ref('base.public_user')
g = Att.create({'user_id': pub.id, 'instrument_id': starter.id, 'version_id': starter.current_version_id.id, 'ts_guest': True,
                'ts_guest_hash': 'h' * 64, 'ts_guest_seen': fields.Datetime.now()})
rec_before = env['ts.consent.record'].sudo().search_count([('attempt_id', '=', g.id)])
g.ts_guest_consent(research=True)
check('G03 the start button is the consent: in progress, service + research + version on the attempt, no ledger row yet',
      g.state == 'in_progress' and g.consent_service and g.consent_research and g.consent_version and rec_before == 0
      and env['ts.consent.record'].sudo().search_count([('attempt_id', '=', g.id)]) == 0)
check('G04 a guest attempt has no panel and no invitation (no panel can see it, nothing is billed)',
      not g.workspace_id and not A.search_count([('attempt_id', '=', g.id)]))
for it in g.active_items():
    g.save_answer(it.id, 1 + it.id % 5)
N = env['ts.notification'].sudo()
n_before = N.search_count([('user_id', '=', pub.id)])
assert g.action_submit()
check('G05 finishing a guest attempt scores it and sends nothing (no notice to the public user)',
      g.state == 'done' and g.result_ids and N.search_count([('user_id', '=', pub.id)]) == n_before)
uc = puser()
check('G06 the claim moves the attempt into the account and clears the browser token digest',
      g.ts_guest_claim(uc) and g.user_id == uc and not g.ts_guest and not g.ts_guest_hash and g.ts_guest_claimed_at)
kinds = env['ts.consent.record'].sudo().search([('attempt_id', '=', g.id)]).mapped('kind')
check('G07 the ledger gets the start consent at the claim (service + research), for the person',
      sorted(kinds) == ['research', 'service'], kinds)
check('G08 a second claim does nothing', not g.ts_guest_claim(puser()) and g.user_id == uc)

# clean-up: 48 hours after the last activity, guest rows only
def mk_guest(hours_ago):
    at = Att.create({'user_id': pub.id, 'instrument_id': starter.id, 'version_id': starter.current_version_id.id,
                     'ts_guest': True, 'ts_guest_hash': 'x%d' % hours_ago})
    at.ts_guest_consent()
    at.save_answer(at.active_items()[0].id, 3)
    env.flush_all()      # raw SQL below: the ORM's pending writes first (they would overwrite it later)
    env.cr.execute('UPDATE ts_attempt SET ts_guest_seen = %s WHERE id = %s', [fields.Datetime.now() - timedelta(hours=hours_ago), at.id])
    return at
old, young = mk_guest(49), mk_guest(47)
normal = Att.create({'user_id': uc.id, 'instrument_id': starter.id, 'version_id': starter.current_version_id.id})
env.flush_all()
env.cr.execute("UPDATE ts_attempt SET create_date = now() - interval '30 days', write_date = now() - interval '30 days' WHERE id IN %s",
               [(normal.id, g.id)])
old_ans = old.answer_ids.ids
env.invalidate_all()
n = Att._cron_guest_cleanup()
check('G09 the clean-up deletes an unclaimed guest attempt 48 h after its last activity, with its answers',
      not old.exists() and not env['ts.attempt.answer'].browse(old_ans).exists() and n >= 1)
check('G10 ...and keeps a younger guest attempt, a claimed one and every ordinary attempt',
      young.exists() and g.exists() and normal.exists())

# ================================================================ F. funnel events (no personal data)
F = env['ts.funnel.event']
MAGIC = {'id', 'create_date', 'create_uid', 'write_date', 'write_uid', 'display_name'}
fields_f = set(F._fields) - MAGIC
check('F01 a funnel row holds the step, the kind of entry, instrument / invitation, a salted hash, the website and the time; '
      'no phone, IP or name', fields_f == {'step', 'entry', 'instrument_id', 'assignment_id', 'session_hash', 'website_id'},
      sorted(fields_f))
check('F05 the kinds of entry: guest, signed in, and how the invitation came (sms, email, manual, campaign)',
      set(dict(F._fields['entry'].selection)) == {'guest', 'user', 'sms', 'email', 'manual', 'campaign'})
check('F02 the steps are the nine of the plan', set(dict(F._fields['step'].selection)) == {
    'start_view', 'start', 'q1', 'finish', 'gate_view', 'gate_signed_in', 'report_view', 'invite_view', 'invite_accept'})
f_old = F.sudo().create({'step': 'start', 'session_hash': 'onb2old'})
f_new = F.sudo().create({'step': 'start', 'session_hash': 'onb2new'})
env.flush_all()
env.cr.execute("UPDATE ts_funnel_event SET create_date = now() - interval '181 days' WHERE id = %s", [f_old.id])
env.invalidate_all()
F._cron_retention()
check('F03 the retention cron removes rows older than 180 days only', not f_old.exists() and f_new.exists())
act = env.ref('ts_onboard.ts_funnel_event_action')
check('F04 the back office pivot/list is for platform managers only',
      'pivot' in act.view_mode and env.ref('ts_core.group_ts_manager') in env.ref('ts_onboard.menu_ts_funnel').group_ids)

# ================================================================ H. fairness questions at the end
from odoo.addons.ts_hire.controllers.public import fair_due
pos_a = A.search([('position_id', '!=', False)], limit=1)
if pos_a:
    check('H01 the fairness questions are due only after the last part, once', fair_due(pos_a) == (
        pos_a.state == 'done' and not pos_a.ts_fair_asked and not (pos_a.ts_gender or pos_a.ts_age_band)))
mig = load('ts_hire', 'migrations/20.0.1.1.0/post-migrate.py')
env.flush_all()
env.cr.execute("UPDATE ts_assignment SET ts_fair_asked = FALSE WHERE id = %s", [aq.id])
mig.migrate(env.cr, '20.0.1.0.0')
env.cr.execute("SELECT count(*) FROM ts_assignment WHERE position_id IS NOT NULL AND user_id IS NOT NULL AND ts_fair_asked IS NOT TRUE")
check('H02 migration: candidates who accepted before (and saw the questions on the invitation page) are not asked again',
      env.cr.fetchone()[0] == 0)
check('H03 the invitation page no longer carries the fairness fields',
      'ts_gender' not in (env.ref('ts_hire.invite_position').arch_db or ''))

# ================================================================ L. an anonymous «no»
ad = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'رد بی‌حساب onb2'})
ad.action_decline(pub)
check('L01 a visitor who is not signed in declines without tying the invitation to any account',
      ad.declined and ad.state == 'declined' and not ad.user_id)
check('L02 an accepted invitation cannot be declined anonymously', raises(lambda: aq.action_decline(pub), UserError))

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
