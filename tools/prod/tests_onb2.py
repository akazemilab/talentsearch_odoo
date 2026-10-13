# onb2 (release 2 of onboarding): one-tap invitations (delivery secret, accounts that may be signed in without a code,
# scope, device binding, short codes, fairness at the end, minors on one screen) and test first for individuals (guest
# attempts, claim, 48-hour clean-up, funnel). Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits; never sends
# an SMS or an e-mail (every send path below is patched to report success without reaching a provider).
import importlib.util
import logging
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
PH = {'a': '09126654381', 'b': '09126654382', 'c': '09126654383', 'k': '09126654384', 'n': '09126654385',
      'e': '09126654386', 's': '09126654387'}


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

# ================================================================ D. delivery (the send paths report it)
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
check('D03 a successful e-mail marks «email» (address lower-cased); an SMS stays the invitation\'s channel',
      a2.delivered_via == 'email' and a2.delivered_email == 'cand.onb2@example.invalid'
      and a1.delivered_via == 'sms' and a1.delivered_email == 'other.onb2@example.invalid')
a3 = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'بی‌پیامک onb2', 'invitee_phone': PH['b']})
with patch.object(SmsAsg, '_ts_send_invite_sms', lambda self: False):
    a3.sms_consent = True
    a3._ts_send_invite_sms()
check('D04 a failed SMS reaches nobody (still «manual»), the typed number stays the invitation\'s number',
      a3.delivered_via == 'manual' and a3.ts_invite_phone() == PH['b'] and a3.ts_proof() == (None, None))
from odoo.addons.ts_panel.models.notify import TsAssignmentNotify
with patch.object(TsAssignmentNotify, '_ts_do_reminder', lambda self: {'sms'}):
    a3._ts_do_reminder()
check('D05 a reminder SMS that went out counts as delivery too', a3.delivered_via == 'sms' and a3.delivered_phone == PH['b'])

# ================================================================ K. the delivery secret (risk review HIGH 1)
from odoo.addons.ts_onboard.models.common import dlv_digest
from odoo.addons.ts_onboard.models.ir_http import _RedactSecrets
k = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'راز onb2', 'invitee_phone': PH['k'],
              'invitee_email': 'k.onb2@example.invalid'})
k._ts_mark_delivered('sms', phone=PH['k'])
k._ts_mark_delivered('email', email='k.onb2@example.invalid')
plain_long, plain_short = k.invite_url(), k.ts_short_url()
with k._ts_dlv_window():
    long1, short1, short1b = k.invite_url(), k.ts_short_url(), k.with_context(ts_sms_short=True).invite_url()
raw_e = long1.split('?d=', 1)[1] if '?d=' in long1 else ''
raw_s = short1.rsplit('/', 1)[1]
check('K01 outside a send window every link is the plain one (panel pages, copy buttons, QR codes, exports)',
      '?d=' not in plain_long and plain_short.count('/') == 4 and k.invite_url() == plain_long and k.ts_short_url() == plain_short,
      (plain_long[-20:], plain_short[-20:]))
check('K02 inside a window: the e-mail link carries ?d=<secret>, the SMS short link /<secret>; 22+ url-safe characters, one '
      'per channel', re.fullmatch(r'[A-Za-z0-9_-]{22,}', raw_e) and re.fullmatch(r'[A-Za-z0-9_-]{22,}', raw_s) and raw_e != raw_s
      and short1b == short1, (len(raw_e), len(raw_s)))
env.flush_all()
env.cr.execute('SELECT count(*) FROM ts_assignment t WHERE t::text LIKE %s OR t::text LIKE %s', ['%' + raw_s + '%', '%' + raw_e + '%'])
check('K03 only digests are stored (no column of the invitation holds a secret)',
      env.cr.fetchone()[0] == 0 and k.dlv_sms_hash == dlv_digest(raw_s) and k.dlv_email_hash == dlv_digest(raw_e))
check('K04 the secret proves its own channel only; anything else proves nothing',
      k.ts_dlv_channel(raw_s) == 'sms' and k.ts_dlv_channel(raw_e) == 'email' and k.ts_dlv_channel('x' * 22) is None
      and k.ts_dlv_channel('') is None and k.ts_dlv_channel(raw_s + '/') is None and a1.ts_dlv_channel(raw_s) is None)


def _render_sms(self):
    return bool(self.ts_short_url())


with patch.object(SmsAsg, '_ts_send_invite_sms', lambda self: _render_sms(self) and False):
    k._ts_send_invite_sms()
check('K05 a message that did not go out keeps the previous secret valid', k.ts_dlv_channel(raw_s) == 'sms')
with patch.object(SmsAsg, '_ts_send_invite_sms', lambda self: _render_sms(self)):
    k._ts_send_invite_sms()
check('K06 a new message replaces the secret of its channel (the older SMS link then gets a code); e-mail unchanged',
      k.ts_dlv_channel(raw_s) is None and k.ts_dlv_channel(raw_e) == 'email')
with k._ts_dlv_window():
    s_in = env['sms.sms'].sudo().create({'number': PH['k'], 'body': 'x'})
s_out = env['sms.sms'].sudo().create({'number': PH['k'], 'body': 'y'})
check('K07 an SMS written inside a send window is masked in the Kavenegar log (kv_secret); others are not',
      s_in.kv_secret and not s_out.kv_secret)
(s_in | s_out).unlink()
rec = logging.LogRecord('werkzeug', logging.INFO, '', 0, '%s - - "%s" 302 -', (
    '1.2.3.4', 'GET /i/abcdabcdabcd/%s HTTP/1.1 GET /invite/tok?d=%s' % (raw_s, raw_e)), None)
_RedactSecrets().filter(rec)
check('K08 the access log line never keeps a secret (/i/<code>/*** and d=***)',
      raw_s not in rec.getMessage() and raw_e not in rec.getMessage() and '/i/abcdabcdabcd/***' in rec.getMessage()
      and 'd=***' in rec.getMessage(), rec.getMessage()[-60:])

# ================================================================ N. who may be signed in without a code
from odoo.addons.ts_onboard.controllers.flow import link_user, phone_only, made_here, only_this_invitation, eot_activity
un, made = link_user(env, 'sms', PH['n'])
check('N01 an SMS secret for a number nobody holds: a new phone-only account (made)', un and made and phone_only(un, PH['n']))
un2, made2 = link_user(env, 'sms', PH['n'])
check('N02 ...the same number again: that phone-only account, not made again', un2 == un and not made2)
ue_ph = puser(PH['e'])
check('N03 an e-mail account that holds the number is never signed in without a code',
      link_user(env, 'sms', PH['e']) == (None, False) and not phone_only(ue_ph, PH['e']))
from odoo.addons.ts_sms.controllers.signup import create_phone_user
us = create_phone_user(env, PH['s'])
check('N04 a phone-only account without eot.ir activity qualifies', phone_only(us, PH['s']) and not eot_activity(us))
eot_site = env['website'].sudo().search([('id', '!=', env.ref('ts_website.website_ts').id)], order='id', limit=1)   # eot.ir
assert eot_site, 'no other website'
fx = False
try:
    with env.cr.savepoint():
        visitor = env['website.visitor'].sudo().create({'access_token': '%d' % us.partner_id.id, 'website_id': eot_site.id})
        env.flush_all()          # the visitor of this account (a signed-in visitor's token is its partner id)
        env.cr.execute('UPDATE website_visitor SET partner_id = %s WHERE id = %s', [us.partner_id.id, visitor.id])
        env.invalidate_all()
        fx = bool(visitor.partner_id == us.partner_id)
        check('N05 ...but not once it has eot.ir activity (a visit of eot.ir as this account): then a code',
              fx and eot_activity(us) and not phone_only(us, PH['s']) and link_user(env, 'sms', PH['s']) == (None, False),
              (fx, visitor.partner_id.id))
        raise UserError('roll back the visit')
except UserError:
    pass
check('N05b an account bound to another website (eot.ir) is never signed in without a code',
      not eot_activity(us) and (us.sudo().write({'website_id': eot_site.id}) or True) and eot_activity(us) and not phone_only(us, PH['s']))
uxb = U.create({'name': 'onb2 uxb', 'login': 'onb2.uxb.k@example.invalid', 'email': 'onb2.uxb.k@example.invalid',
                'group_ids': [(6, 0, [portal.id])]})
uu, made_u = link_user(env, 'email', 'onb2.u_b.k@example.invalid')
check('N06 e-mail: «_» is not a wildcard (onb2.u_b… never finds onb2.uxb…); an address without an account gets a new one',
      uu and made_u and uu != uxb and uu.login == 'onb2.u_b.k@example.invalid', uu.login if uu else None)
check('N07 an address that already has an account (any letter case) is never signed in without a code',
      link_user(env, 'email', 'ONB2.UXB.K@example.invalid') == (None, False)
      and link_user(env, 'email', 'onb2.u_b.k@example.invalid') == (None, False))
am = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'ساخته onb2'})
am.action_accept(uu, share=True)
am.write({'ts_account_made': True})
check('N08 the account the flow made for this invitation, holding nothing else, counts as «made here» (moments ago too)',
      only_this_invitation(uu, am) and made_here(uu, am) and made_here(uu, am, minutes=60))
env.flush_all()
env.cr.execute("UPDATE res_users SET create_date = now() - interval '2 hours' WHERE id = %s", [uu.id])
env.invalidate_all()
check('N09 ...not «moments ago» after an hour', made_here(uu, am) and not made_here(uu, am, minutes=60))
am2 = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'دومی onb2'})
am2.action_accept(uu, share=True)
check('N10 ...and not once it holds another invitation', not only_this_invitation(uu, am) and not made_here(uu, am))

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
from odoo.addons.ts_sms.controllers.signup import mask_mobile
check('M04 a known number is shown by its last four digits only («*** ۴۳۸۱»: asterisks, bullets read as Persian zeros)',
      mask_mobile(PH['a']) == '*** ۴۳۸۱', mask_mobile(PH['a']))

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
env.cr.execute('UPDATE ts_rate_hit SET at = at - interval %s WHERE key = %s', ['2 minutes', key])
check('R02 after the window the key is let through again', R.ts_hit(key, 3, 60))
key2 = 'test:onb2:rb:%d' % a4.id
second = []


def _no_second_cursor(*a, **kw):
    second.append(1)
    raise AssertionError('a second cursor')


with patch.object(type(env.registry), 'cursor', _no_second_cursor):
    R.ts_hit(key2, 1, 60)
check('R03 a hit is written in the request\'s own transaction (no second cursor; a miss answers its 404 inside the request '
      'and is committed with the hit)', not second and R.search_count([('key', '=', key2)]) == 1 and not R.ts_hit(key2, 1, 60))
env.cr.execute("DELETE FROM ts_rate_hit WHERE key LIKE 'test:onb2:%%'")
camp = None
try:
    with env.cr.savepoint():
        camp = env['ts.campaign'].sudo().create({'workspace_id': wcl.id, 'name': 'onb2 پیوند باز', 'instrument_id': adult.id,
                                                 'kind': 'open_link'})
        a_c = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'کلاس onb2', 'campaign_id': camp.id})
except Exception as e:      # noqa: BLE001 - reported by the check below
    camp, a_c = None, str(e)[:120]
check('D06 an invitation made by joining an open link or class code is «campaign» (no message, the ordinary sign-in)',
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
check('C05 «این دستگاه شخصی من است» travels with the consent (binding for 30 days only when ticked)',
      consent_from({'personal': '1'}, a4)['personal'] and not consent_from({}, a4)['personal'])

# ================================================================ Q. the scope of a session for one invitation
from odoo.addons.ts_onboard.models.ir_http import scope_allows
uq = puser(PH['c'])
aq = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'اسکوپ onb2'})
tq = aq.action_accept(uq, share=True)
other = A.create({'workspace_id': wcl.id, 'instrument_id': adult.id, 'invitee_name': 'دیگری onb2'})
sc = {'aid': aq.id, 'uid': uq.id, 'phone': PH['c']}
ok_paths = ['/invite/%s' % aq.token, '/invite/%s/accept' % aq.token, '/take/%s' % tq.access_token,
            '/take/%s/answer' % tq.access_token, '/take/%s/task/start' % tq.access_token, '/my/assessments/%s' % tq.id,
            '/my/assessments/%s/pdf' % tq.id, '/i/%s' % aq.short_code, '/i/%s/%s' % (aq.short_code, 'x' * 22),
            '/web/assets/1/web.assets_frontend.min.css', '/web/session/logout', '/signup', '/signup/verify']
bad_paths = ['/my', '/my/assessments', '/my/account', '/my/workspaces', '/my/workspaces/%s' % wcl.id,
             '/invite/%s' % other.token, '/i/%s' % other.short_code, '/take/x%s' % tq.access_token[1:],
             '/my/assessments/%s/share' % tq.id, '/my/assessments/%s' % (tq.id + 100000), '/web', '/odoo', '/assessments',
             '/start', '/', '/my/assessments/battery/%s' % other.id, '/web/login', '/websocket',
             '/web/image/res.partner/%s/avatar_128' % uq.partner_id.id, '/web/dataset/call_kw', '/web/session/get_session_info',
             '/json/2/res.partner/search_read', '/mail/data', '/web/content/1', '/contactus']
check('Q01 a scoped session reaches its invitation, its player, its own result, assets, sign-in and sign-out',
      all(scope_allows(env, sc, p) for p in ok_paths), [p for p in ok_paths if not scope_allows(env, sc, p)])
check('Q02 ...and nothing else: /my, other invitations, panels, the back office, JSON, images, the websocket, pages',
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
from odoo.addons.ts_onboard.models.funnel import is_bot
F = env['ts.funnel.event']
MAGIC = {'id', 'display_name'}
fields_f = set(F._fields) - MAGIC
check('F01 a funnel row holds only the step, the channel, the instrument, a salted hash, the day and the hour (and, onb3, the '
      'kind of panel); no invitation, account, website, address or create/write user',
      fields_f == {'step', 'entry', 'instrument_id', 'session_hash', 'day', 'hour', 'panel_kind'}, sorted(fields_f))
check('F05 the channels: guest, signed in, and how the invitation came (sms, email, manual, campaign)',
      set(dict(F._fields['entry'].selection)) == {'guest', 'user', 'sms', 'email', 'manual', 'campaign'})
check('F02 the steps are the nine of the plan (and the four panel activation steps of onb3)', set(dict(F._fields['step'].selection)) == {
    'start_view', 'start', 'q1', 'finish', 'gate_view', 'gate_signed_in', 'report_view', 'invite_view', 'invite_accept',
    'panel_created', 'self_test_done', 'first_invite', 'first_result_opened'})
f_old = F.sudo().create({'step': 'start', 'session_hash': 'onb2old'})
f_new = F.sudo().create({'step': 'start', 'session_hash': 'onb2new'})
f_old.write({'day': fields.Date.today() - timedelta(days=181)})
F._cron_retention()
check('F03 the retention cron removes rows older than 180 days only', not f_old.exists() and f_new.exists())
act = env.ref('ts_onboard.ts_funnel_event_action')
check('F04 the back office pivot/list is for platform managers only',
      'pivot' in act.view_mode and env.ref('ts_core.group_ts_manager') in env.ref('ts_onboard.menu_ts_funnel').group_ids)


class _Req:
    def __init__(self, ua):
        self.headers = {'User-Agent': ua} if ua is not None else {}


check('F06 obvious robots are not counted (empty agent, crawlers, link previews, command-line clients); browsers are',
      is_bot(_Req('')) and is_bot(_Req(None)) and is_bot(_Req('Mozilla/5.0 (compatible; Googlebot/2.1)'))
      and is_bot(_Req('TelegramBot (like TwitterBot)')) and is_bot(_Req('WhatsApp/2.23')) and is_bot(_Req('curl/8.0'))
      and not is_bot(_Req('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36')))

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

# ================================================================ Z. closing items of the re-review
from odoo.addons.ts_onboard.controllers import flow as _flow
check('Z01 eot.ir activity also covers leads, helpdesk tickets, survey answers and forum posts (each only when installed)',
      {'crm.lead', 'helpdesk.ticket', 'survey.user_input', 'forum.post'} <= {m for m, _f in _flow.EOT_ACTIVITY}
      and not eot_activity(un), [m for m in ('crm.lead', 'helpdesk.ticket', 'survey.user_input', 'forum.post') if m in env])


def _activity_after(make):
    """eot_activity(un) after `make()` inside a savepoint that is rolled back."""
    seen = []
    try:
        with env.cr.savepoint():
            make()
            env.flush_all()
            seen.append(eot_activity(un))
            raise UserError('roll back')
    except UserError:
        pass
    return seen[0] if seen else None


msg_out = _activity_after(lambda: env['mail.message'].sudo().create({
    'model': 'res.partner', 'res_id': un.partner_id.id, 'body': 'onb2', 'message_type': 'comment', 'author_id': un.partner_id.id}))
msg_ts = _activity_after(lambda: env['mail.message'].sudo().create({
    'model': 'ts.assignment', 'res_id': a1.id, 'body': 'onb2', 'message_type': 'comment', 'author_id': un.partner_id.id}))
msg_note = _activity_after(lambda: env['mail.message'].sudo().create({
    'model': 'res.partner', 'res_id': un.partner_id.id, 'body': 'onb2', 'message_type': 'notification', 'author_id': un.partner_id.id}))
check('Z02 a message the person wrote on a record outside Talent Search is eot.ir activity; one on a Talent Search record '
      'or a system note is not', msg_out is True and msg_ts is False and msg_note is False, (msg_out, msg_ts, msg_note))
if 'crm.lead' in env:
    lead = _activity_after(lambda: env['crm.lead'].sudo().create({'name': 'onb2 lead', 'partner_id': un.partner_id.id}))
    check('Z03 an eot.ir lead of the account is activity', lead is True, lead)
with patch.object(type(env['mail.message']), 'search', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('db'))):
    failed = eot_activity(un)
check('Z04 a check that cannot run counts as activity (fail closed)', failed is True)
R.ts_hit('test:onb2:lock', 5, 60)
env.cr.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid() AND granted")
check('Z05 a rate hit holds a transaction-scoped advisory lock on its key (no overshoot under concurrency, no second cursor)',
      env.cr.fetchone()[0] >= 1)
env.cr.execute("DELETE FROM ts_rate_hit WHERE key = 'test:onb2:lock'")
KM = env['kavenegar.message'].sudo()
mid1, mid2 = 'onb2-import-%d-1' % a1.id, 'onb2-import-%d-2' % a1.id
KM._kv_import_outbox(env.company, [
    {'messageid': mid1, 'status': 10, 'receptor': PH['k'], 'message': 'دعوت\nhttps://talentsearch.ir/i/abcdabcdabcd/' + 'Zq_-' * 6},
    {'messageid': mid2, 'status': 10, 'receptor': PH['k'], 'message': 'دعوت https://talentsearch.ir/invite/%s?d=%s' % ('f' * 32, 'Yq_-' * 6)}])
b1, b2 = KM.search([('messageid', '=', mid1)]).body or '', KM.search([('messageid', '=', mid2)]).body or ''
check('Z06 an outbox row imported without a sent-log row never keeps an invitation link secret (/i/<code>/*** and d=***)',
      'Zq_-' not in b1 and '/i/abcdabcdabcd/***' in b1 and 'Yq_-' not in b2 and '?d=***' in b2, (b1[-30:], b2[-30:]))

print('SUMMARY %d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
