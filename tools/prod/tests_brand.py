# Clinic phase 5 (ts_brand): branding fields and permissions, report header values, PDF report values, SMS templates with
# their rules (docs/clinic/05_sms_texts.md «قواعد»), fallbacks, short codes, the cap notice, the title fallback.
# Clinic phase 6 (section 9): the counseling-center set-up checklist «راه‌اندازی مرکز» (each step's done rule, hide /
# restore per member) and the counselor first-run card.
# Run ONLY on an eot_ts* clone via odoo-bin shell. Never commits (rolls back at the end); savepoints inside.
import base64
import re

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.addons.ts_brand.hooks import backfill_short_codes
from odoo.addons.ts_brand.models.sms import PART2, jalali_month_key, sms_parts

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []
Command = fields.Command


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn, exc):
    try:
        with env.cr.savepoint():
            fn()
    except exc:
        return True
    except Exception as e:
        print('    unexpected', type(e).__name__, str(e)[:160])
        return False
    return False


portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
W, M, A, N, Audit = env['ts.workspace'], env['ts.workspace.member'], env['ts.assignment'], env['ts.notification'], env['ts.audit.event']
Brand = env['ts.brand']
# nothing is sent: no invitation carries a phone with consent and no test user opted in to staff SMS (no company write here:
# this suite runs beside the guard and must not lock res_company)
_n = [0]
SECRET = 'نام‌محرمانهٔ‌آزمون'                              # a participant name that must never reach an SMS
HEX32 = re.compile(r'[0-9a-f]{32}')
LATIN = re.compile(r'[0-9]')
FORBIDDEN = ('!', 'متأسفانه', 'درمان', 'بالینی', 'کلینیک', 'بیمار', 'مریض', 'نمره', 'بازه', SECRET)


def puser(tag='u'):
    _n[0] += 1
    login = 'ts.brand.%s%d@example.invalid' % (tag, _n[0])
    return U.create({'name': 'کاربر آزمون %s %d' % (tag, _n[0]), 'login': login, 'email': login,
                     'group_ids': [Command.set([portal.id])]})


def panel(purpose='clinical', name=None):
    _n[0] += 1
    org = env['res.partner'].create({'name': name or ('مرکز مشاوره آزمون %d' % _n[0]), 'is_company': True})
    vals = {'name': org.name, 'purpose': purpose, 'partner_id': org.id}
    if purpose == 'clinical':
        vals['escalation_contact_id'] = org.id
    ws = W.create(vals)
    ws.write({'approved_on': '2026-01-01 00:00:00'})
    ws.state = 'pilot' if purpose == 'clinical' else 'active'
    return ws


def member(ws, role, verified=True):
    m = M.create({'workspace_id': ws.id, 'user_id': puser(role).id, 'role': role})
    if role in ('clinician', 'clinic_director', 'counselor'):
        m.write({'license_number': 'LIC-%d' % m.id, 'verification_state': 'verified' if verified else 'pending'})
    return m


def instrument(purpose_ok='clinical'):
    dom = [('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '!=', 'TALENT-INV-15')]
    return env['ts.instrument'].search(dom).sorted(lambda i: (i.active_item_count, i.id))[:1]


def finish(at):
    if at.state == 'consent':
        at.give_consent(research=False, role='self')
    for it in at.active_items():
        at.save_answer(it.id, 1 + it.id % 5)
    return at.action_submit()


def rules(name, body, link_re=r'https://talentsearch\.ir/(i|j|n)/[a-z0-9]+', otp=False):
    """The «قواعد» on one rendered body."""
    lines = body.split('\n')
    bad = [w for w in FORBIDDEN if w in body]
    check('%s: no name, result word, «!», «متأسفانه» or therapy word' % name, not bad, str(bad))
    check('%s: at most 2 parts (%d characters, %d parts)' % (name, len(body), sms_parts(body)), len(body) <= PART2, body)
    if otp:
        check('%s: no link, the code on its own line' % name, 'http' not in body and re.search(r'\b\d{6}\b', lines[1] or ''), body)
        return
    check('%s: the link is last and alone, never a full token' % name,
          re.fullmatch(link_re, lines[-1]) and len(lines[-1]) <= 40 and not HEX32.search(body), lines[-1])
    check('%s: Persian digits outside the link' % name, not any(LATIN.search(ln) for ln in lines[:-1]), body)


# ================================================================ 1. fields and validation
ws = panel('clinical', name='مرکز مشاوره و خدمات روان‌شناختی آرامش پایدار شهر')
own = member(ws, 'owner')
own.write({'owner_practices': True, 'license_number': 'OWN-1', 'verification_state': 'verified'})
dr = member(ws, 'clinic_director')
c1 = member(ws, 'clinician')
c2 = member(ws, 'clinician', verified=False)
inst = c1.allowed_instruments().filtered(lambda i: i.audience == 'adult' and i.code != 'TALENT-INV-15')[:1] or instrument()
check('F01 public name defaults to the panel name', ws.ts_public_name() == ws.name)
check('F02 SMS name derived from the public name, cut at a word boundary, <= 18', len(ws.ts_sms_sender()) <= 18
      and ws.name.startswith(ws.ts_sms_sender()) and (len(ws.ts_sms_sender()) == len(ws.name) or ws.name[len(ws.ts_sms_sender())] == ' '),
      ws.ts_sms_sender())
check('F03 brand_color must be #rrggbb', raises(lambda: ws.write({'brand_color': 'red'}), ValidationError)
      and raises(lambda: ws.write({'brand_color': '#12345'}), ValidationError))
check('F04 sms_name over 18 characters is refused', raises(lambda: ws.write({'sms_name': 'ا' * 19}), ValidationError))
check('F05 contact line over 80 characters is refused', raises(lambda: ws.write({'contact_line': 'x' * 81}), ValidationError))
check('F06 member title over 40 and bio over 160 are refused', raises(lambda: c1.write({'title': 'ا' * 41}), ValidationError)
      and raises(lambda: c1.write({'report_bio': 'ا' * 161}), ValidationError))
check('F07 show_on_report defaults to True', c1.show_on_report is True)
n_audit = Audit.search_count([('event_type', '=', 'brand.change'), ('workspace_id', '=', ws.id)])
changed = ws.ts_brand_save(own, {'public_name': 'مرکز مشاوره آرامش', 'sms_name': 'مرکز آرامش', 'brand_color': '#5446A8',
                                 'contact_line': '۰۲۱-۱۲۳۴۵۶۷۸ · aramesh.ir'})
check('F08 the owner saves the panel identity (colour lower-cased) and it is audited',
      changed == ['brand_color', 'contact_line', 'public_name', 'sms_name'] and ws.brand_color == '#5446a8'
      and Audit.search_count([('event_type', '=', 'brand.change'), ('workspace_id', '=', ws.id)]) == n_audit + 1, str(changed))
check('F09 a clinician cannot save the panel identity', raises(lambda: ws.ts_brand_save(c1, {'public_name': 'x'}), UserError))
check('F10 a clinic director can (panel:profile + brand role)', ws.ts_brand_save(dr, {'public_name': 'مرکز مشاوره آرامش',
                                                                                    'sms_name': 'مرکز آرامش', 'brand_color': '#5446a8',
                                                                                    'contact_line': 'aramesh.ir'}) == ['contact_line'])
check('F11 server validation of the colour on save', raises(lambda: ws.ts_brand_save(own, {'brand_color': '#zzzzzz'}), UserError))
check('F12 a member edits own title and bio', sorted(c1.ts_brand_save(c1, {'title': 'روان‌شناس و مشاور', 'report_bio': 'مشاور نوجوان'}))
      == ['report_bio', 'title'])
check('F13 the director edits another member\'s title / show_on_report but not the bio',
      dr.id != c1.id and c1.ts_brand_save(dr, {'title': 'مشاور ارشد', 'show_on_report': True, 'report_bio': 'تغییر'}) == ['title']
      and c1.report_bio == 'مشاور نوجوان')
check('F14 a clinician cannot edit a colleague', raises(lambda: c2.ts_brand_save(c1, {'title': 'x'}), UserError))
png = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                    '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082')
check('F15 a signature must be PNG/JPG and under 300 KB', raises(lambda: c1.ts_brand_save(c1, {}, signature=b'GIF89a....'), UserError)
      and raises(lambda: c1.ts_brand_save(c1, {}, signature=b'\x89PNG' + b'0' * (301 * 1024)), UserError))
check('F16 only the member uploads their own photo / signature', raises(lambda: c1.ts_brand_save(dr, {}, photo=png), UserError))

# ================================================================ 2. report header values
pu = puser('part')
a1 = A.create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': SECRET, 'invited_by_id': c1.user_id.id,
               'responsible_id': c1.id})
at = a1.action_accept(pu, True)
finish(at)
h = at.ts_brand_header()
check('H01 a counseling-center attempt has the institution header', h and h['name'] == 'مرکز مشاوره آرامش' and h['color'] == '#5446a8'
      and h['contact'] == 'aramesh.ir', str(h and h['name']))
check('H02 the counselor block: responsible member, title, verified licence, no contact data',
      h['counselor'] and h['counselor']['title'] == 'مشاور ارشد' and h['counselor']['license'] == c1.license_number
      and not any(k in h['counselor'] for k in ('phone', 'email', 'mobile')), str(h['counselor'] and sorted(h['counselor'])))
c1.verification_state = 'pending'
at.invalidate_recordset()
check('H03 an unverified licence is not shown', at.ts_brand_header()['counselor']['license'] is False)
c1.write({'verification_state': 'verified', 'show_on_report': False})
check('H04 show_on_report off: no counselor block', at.ts_brand_header()['counselor'] is None)
c1.show_on_report = True
a1.responsible_id = False
check('H05 no responsible member: the inviting member is shown', at.ts_brand_header()['counselor']['name'] == c1.user_id.name)
a1.responsible_id = c1
self_at = env['ts.attempt'].create({'user_id': pu.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
check('H06 a self-taken attempt outside a panel keeps the plain header', self_at.ts_brand_header() is False)
wemp = panel('employment')
check('H07 an employment panel has no institution header', wemp.ts_brand_header() is False)
# header images (UX audit G8-PT-1): the mime type comes from the bytes; stand-ins and non-images draw no <img> at all
from odoo.addons.ts_brand.models.brand import png_data_uri, has_image
b64png = base64.b64encode(png)
svg_logo = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="#2a6f97"/></svg>'
svg_avatar = (b"<?xml version='1.0' encoding='UTF-8' ?><svg height='180' width='180' xmlns='http://www.w3.org/2000/svg'>"
              b"<rect fill='hsl(210, 50%, 45%)' height='180' width='180'/><text fill='#ffffff' x='90' y='125'>S</text></svg>")
uri = png_data_uri(b64png)
check('H08 a PNG becomes a PNG data URI whose bytes really are PNG', uri and uri.startswith('data:image/png;base64,')
      and base64.b64decode(uri.split(',', 1)[1])[:4] == b'\x89PNG', str(uri)[:40])
check('H09 raw bytes (not base64) are read too', (png_data_uri(png) or '').startswith('data:image/png;base64,iVBOR'))
check('H10 an SVG logo is sent as image/svg+xml, never labelled PNG',
      (png_data_uri(base64.b64encode(svg_logo)) or '').startswith('data:image/svg+xml;base64,'))
check('H11 Odoo\'s letter avatar and non-image bytes give no image', png_data_uri(base64.b64encode(svg_avatar)) is False
      and png_data_uri(base64.b64encode(b'not an image')) is False and not has_image(base64.b64encode(svg_avatar)))
check('H12 no photo -> the counselor block carries a monogram letter, no photo URI',
      at.ts_brand_header()['counselor']['photo'] is False and at.ts_brand_header()['counselor']['initial'] != '')

# ================================================================ 3. PDF report values (level decides, never more)
vals_c = env['report.ts_brand.attempt_pdf']._get_report_values(at.ids, {'mode': 'panel', 'level': 'clinical'})
vals_s = env['report.ts_brand.attempt_pdf']._get_report_values(at.ids, {'mode': 'panel', 'level': 'summary'})
vals_p = env['report.ts_brand.attempt_pdf']._get_report_values(at.ids, {'mode': 'self'})
check('P01 the PDF values carry the header, the results and the panel level', vals_c['brand'] and vals_c['sections'][0]['results']
      and vals_c['sections'][0]['level'] == 'clinical' and vals_s['sections'][0]['level'] == 'summary')
check('P02 participant mode names the participant, panel mode the participant record', vals_p['who'] and vals_c['who'])
rep = env.ref('ts_brand.action_attempt_pdf')
check('P03 the PDF actions never store an attachment', not rep.attachment and not rep.attachment_use
      and not env.ref('ts_brand.action_battery_pdf').attachment and rep.report_type == 'qweb-pdf')

# ================================================================ 4. short codes
check('S01 a new invitation gets an 8-character [a-z0-9] short code', re.fullmatch(r'[a-z0-9]{8}', a1.short_code or ''), a1.short_code)
a2 = A.create({'workspace_id': ws.id, 'instrument_id': inst.id, 'invitee_name': 'دوم', 'invited_by_id': c1.user_id.id})
env.flush_all()
check('S02 short codes are unique', a1.short_code != a2.short_code and raises(
    lambda: env.cr.execute('UPDATE ts_assignment SET short_code = %s WHERE id = %s', [a1.short_code, a2.id]), Exception))
env.cr.execute('UPDATE ts_assignment SET short_code = NULL WHERE id = %s', [a2.id])
inv = env['ts.member.invite'].ts_create(own, 'clinician', phone_raw='09127770951')
env.flush_all()
env.cr.execute('UPDATE ts_member_invite SET short_code = NULL WHERE id = %s', [inv.id])
out = backfill_short_codes(env.cr)
env.invalidate_all()
check('S03 the install backfill fills every missing code', a2.short_code and inv.short_code and out['ts_assignment'] >= 1, str(out))
env.cr.execute('SELECT count(*) FROM ts_assignment WHERE short_code IS NULL')
nulls = env.cr.fetchone()[0]
env.cr.execute('SELECT count(*) - count(DISTINCT short_code) FROM ts_assignment')
dups = env.cr.fetchone()[0]
check('S04 no invitation without a code, no duplicate code', nulls == 0 and dups == 0, '%s %s' % (nulls, dups))
check('S05 short links are 34 characters or less', len(a1.ts_short_url()) <= 34 and len(inv.ts_short_url()) <= 34, a1.ts_short_url())
check('S06 invite_url is unchanged outside an SMS', '/invite/' in a1.invite_url() and '/i/' in a1.with_context(ts_sms_short=True).invite_url())

# ================================================================ 5. every template, rendered with real records
a1.deadline = fields.Date.today()
body = Brand.sms_render('ts_brand.sms_invite_single', a1)
rules('invite_single', body)
check('invite_single: line 1 = the SMS name, counselor named, deadline in Persian', body.split('\n')[0] == 'مرکز آرامش'
      and c1.user_id.name.split()[0] in body and 'مهلت تا' in body, body)
check('invite_single: the instrument name is never in the SMS', inst.name not in body and (inst.title or '@@') not in body)
long_ws = panel('clinical', name='مرکز مشاوره و خدمات روان‌شناختی آرامش پایدار')
lm = member(long_ws, 'clinician')
lm.user_id.name = 'دکتر سیدمحمدحسین میرعمادالدینی خراسانی‌نژاد'
la = A.create({'workspace_id': long_ws.id, 'instrument_id': inst.id, 'invitee_name': SECRET, 'invited_by_id': lm.user_id.id,
               'responsible_id': lm.id, 'deadline': '2099-03-01'})
body = Brand.sms_render('ts_brand.sms_invite_single', la)
rules('invite_single (long values)', body)
check('rule 6: a long counselor clause is dropped before the deadline', 'خراسانی' not in body and 'مهلت تا' in body
      and '۱۴۷۷' in body, body)
check('rule 8: a deadline outside this Jalali year carries the year', re.search('[۰-۹]{4}', body), body)
bat = c1.allowed_batteries().filtered(lambda b: b.audience == 'adult')[:1]
if bat:
    ab = A.create({'workspace_id': ws.id, 'battery_id': bat.id, 'invitee_name': SECRET, 'invited_by_id': c1.user_id.id,
                   'responsible_id': c1.id})
    body = Brand.sms_render('ts_brand.sms_invite_battery', ab)
    rules('invite_battery', body)
    check('invite_battery: count and minutes, no battery name', ('حدود' in body and 'دقیقه' in body and bat.name not in body), body)
    check('invite_battery: the battery picks its template', ab._ts_invite_template() == 'ts_brand.sms_invite_battery')
else:
    check('invite_battery: a published adult battery exists on this clone', False)
wedu = panel('education', name='دبیرستان فرزانگان آزمون')
eo = member(wedu, 'owner')
einst = eo.allowed_instruments().filtered(lambda i: i.audience in ('adult', 'adolescent') and i.code != 'TALENT-INV-15')[:1] or inst
ea = A.create({'workspace_id': wedu.id, 'instrument_id': einst.id, 'invitee_name': SECRET, 'invited_by_id': eo.user_id.id,
               'invitee_phone': '09127770952'})
check('invite_student: an education invitation to the student\'s own number uses «تو»',
      ea._ts_invite_template() == 'ts_brand.sms_invite_student' if ea.client_id else True, str(ea.client_id))
body = Brand.sms_render('ts_brand.sms_invite_student', ea)
rules('invite_student', body)
check('invite_student: «تو»', 'برای تو' in body or 'برایت' in body, body)
if ea.client_id:
    ea.client_id.sudo().write({'guardian_phone': '09127770952'})
    check('rule 9: the guardian\'s number gets the «شما» text', ea._ts_invite_template() == 'ts_brand.sms_invite_single')
body = Brand.sms_render('ts_brand.sms_reminder', a1)
rules('reminder', body)
check('reminder: 1 part with the sample institution', sms_parts(body) == 1, body)
body = Brand.sms_render('ts_brand.sms_result_ready_client', at)
rules('result_ready_client', body, link_re=r'https://talentsearch\.ir/my/assessments')
check('result_ready_client: «نتیجهٔ شما آماده است», 1 part', 'نتیجهٔ شما آماده است' in body and sms_parts(body) == 1, body)
row = N._notify(c1.user_id, 'result_ready_staff', '/my/workspaces/%s/clients/%s' % (ws.id, a1.client_id.id), ws)
body = row._ts_sms_body()
rules('result_ready_staff', body)
check('result_ready_staff: the notice\'s own /n/ link', body.endswith('/n/%s' % row.id) and 'نتیجهٔ تازه در پنل شما' in body, body)
check('result_ready_staff: new in-app title', row.title == 'نتیجهٔ تازه در پنل شما', row.title)
for t, word in (('panel_approved', 'تأیید شد'), ('panel_rejected', 'تأیید نشد'), ('panel_suspended', 'معلق شد')):
    r = N._notify(own.user_id, t, '/my/workspaces/%s' % ws.id, ws)
    body = r._ts_sms_body()
    rules(t, body)
    check('%s: one part, one fact' % t, sms_parts(body) == 1 and word in body, body)
wal = env['ts.wallet']._for_workspace(ws)
r = N._notify(own.user_id, 'low_balance', '/my/workspaces/%s/credits' % ws.id, ws)
body = r._ts_sms_body()
rules('low_balance', body)
check('low_balance: «شارژ اعتبار» wording, amount in toman', 'شارژ' in body and 'تومان' in body, body)
r2 = N._notify(lm.user_id, 'low_balance', '/my/workspaces/%s/credits' % long_ws.id, long_ws)
long_ws.name = 'مرکز مشاوره و خدمات روان‌شناختی آرامش پایدار شهر'
body = r2._ts_sms_body()
rules('low_balance (long panel name -> short sibling)', body)
check('low_balance: a long panel name uses «اعتبار پنل شما»', 'اعتبار پنل شما' in body, body)
c1.sudo().monthly_cap = 5000000
r = N._notify(c1.user_id, 'cap_reached', '/my/workspaces/%s/credits' % ws.id, ws)
body = r._ts_sms_body()
rules('cap_reached', body)
check('cap_reached: the cap in toman and the panel name', '۵۰۰٬۰۰۰ تومان' in body and 'پنل' in body, body)
body = inv.ts_member_invite_sms_body()
rules('member_invite', body)
check('member_invite: role label and /j/ link', 'مشاور مرکز' in body and '/j/' in body, body)
check('member_invite: the colleague flow still sends nothing', not inv.sms_sent)
po = env['ts.phone.otp'].sudo().create({'user_id': pu.id, 'phone': '09127770953', 'salt': 'x', 'code_hash': 'y',
                                        'expires_at': fields.Datetime.now()})
body = env['ts.phone.otp']._ts_otp_body('123456', '09127770953')
rules('otp_phone', body, otp=True)
check('otp_phone: the approved text', body == 'استعدادیاب\nکد تأیید: 123456 (۵ دقیقه)\nبه کسی ندهید.', body)
env['ts.signup.otp'].sudo().create({'phone': '09127770954', 'salt': 'x', 'code_hash': 'y', 'expires_at': fields.Datetime.now()})
body = env['ts.phone.otp'].with_context(ts_otp_kind='signup')._ts_otp_body('654321', '09127770954')
rules('otp_signup', body, otp=True)
check('otp_signup: from its own template', '654321' in body and body.startswith('استعدادیاب'), body)

# ================================================================ 6. fallbacks (missing, empty, broken template)
class _Undo(Exception):
    """Raised at the end of a block so its savepoint rolls the template edits back."""


def undo(fn):
    try:
        with env.cr.savepoint():
            fn()
            raise _Undo()
    except _Undo:
        pass
    env.invalidate_all()


check('B01 a missing template uses the fallback text', Brand.sms_render('ts_brand.no_such_template', a1, fallback='متن پشتیبان') == 'متن پشتیبان')
tpl = env.ref('ts_brand.sms_invite_single')


def b02():
    tpl.sudo().body = ' '
    body = a1._ts_invite_sms_body()
    check('B02 an empty template falls back to the old text, with the short link (never the token)',
          '/i/%s' % a1.short_code in body and a1.token not in body and 'استعدادیاب' in body, body)
    tpl.sudo().body = '{{ object.no_such_field_xyz }}\n{{ object.ts_sms_link }}'
    body = a1._ts_invite_sms_body()
    check('B03 a template that fails to render falls back too', '/i/%s' % a1.short_code in body and a1.token not in body, body)


def b04():
    env.ref('ts_brand.sms_reminder').sudo().body = ' '
    body = a1._ts_reminder_sms_body()
    check('B04 reminder fallback carries the short link', '/i/%s' % a1.short_code in body and a1.token not in body, body)


def b05():
    env.ref('ts_brand.sms_result_ready_staff').sudo().body = ' '
    body = row._ts_sms_body()
    check('B05 an empty staff template falls back to the old text with the /n/ link', body.endswith('/n/%s' % row.id), body)


def b06():
    env.ref('ts_brand.sms_otp_phone').sudo().body = ' '
    body = env['ts.phone.otp']._ts_otp_body('111222', '09127770953')
    check('B06 OTP fallback keeps the code', '111222' in body, body)


for fn in (b02, b04, b05, b06):
    undo(fn)
check('B07 the templates are back after the fallback checks', tpl.body.startswith('{{ object.ts_sms_org }}'), tpl.body[:40])

# ================================================================ 7. cap_reached notice
n0 = N.search_count([('user_id', '=', c1.user_id.id), ('type', '=', 'cap_reached')])
c1.cap_alert_month = False
c1._ts_cap_reached_notify()
c1._ts_cap_reached_notify()
check('K01 cap_reached: one in-app row per member per Jalali month', N.search_count(
    [('user_id', '=', c1.user_id.id), ('type', '=', 'cap_reached')]) == n0 + 1 and c1.cap_alert_month == jalali_month_key())
from odoo.addons.ts_billing.models.wallet import CreditRefused
CreditRefused('x', 'cap', ws, 10, c2).ts_log(env)
check('K02 a cap refusal schedules the notice for after the commit', c2.id in env.cr.postcommit.data.get('ts_brand.cap_reached', set()))
CreditRefused('x', 'insufficient', ws, 10, c1).ts_log(env)
check('K03 an insufficient-credit refusal does not', c1.id not in env.cr.postcommit.data.get('ts_brand.cap_reached', set()))
env.cr.postcommit.clear()

# ================================================================ 8. titles without duplication
site = env.ref('ts_website.website_ts')
paths = ['/my/workspaces/%s' % ws.id, '/my/workspaces/%s/members/3' % ws.id, '/my/workspaces/%s/clients/4/r/5' % ws.id,
         '/my/assessments/7', '/my/assessments/battery/8', '/signup', '/panel', '/i/abcd1234', '/j/abcd1234', '/help/panel',
         '/my/workspaces/new', '/take/x/next', '/my/workspaces', '/web/login']
miss = [p for p in paths if not site.ts_fallback_title(p) or site.ts_fallback_title(p) == site.name]
check('T01 every panel and account path has its own Persian title', not miss, str(miss))

# ================================================================ 9. set-up guide «راه‌اندازی مرکز» (clinic phase 6)
from odoo.addons.ts_brand.models.onboarding import HELP_URL, NOT_YOURS
ob = panel('clinical', name='مرکز مشاوره راه‌اندازی آزمون')
oo = member(ob, 'owner')
oa = member(ob, 'admin')


def ostep(m, key):
    return next((s for s in m.ts_onb_steps() if s['key'] == key), None)


keys = [s['key'] for s in oo.ts_onb_steps()]
check('O01 a free counseling-center panel has four steps (no caps, no credit)', keys == ['identity', 'counselors', 'catalog', 'invite'],
      str(keys))
ob.billing_mode = 'prepaid'            # the shell env is the superuser (billing_mode is a platform-manager field)
keys = [s['key'] for s in oo.ts_onb_steps()]
check('O02 a prepaid panel has the six steps in order; only the caps step is optional',
      keys == ['identity', 'counselors', 'credit', 'catalog', 'caps', 'invite']
      and [s['key'] for s in oo.ts_onb_steps() if s['optional']] == ['caps'], str(keys))
ck = oo.ts_onb_checklist()
check('O03 the owner sees «0 of 6» with the help link', ck and ck['done_n'] == 0 and ck['total'] == 6 and ck['help_url'] == HELP_URL
      and HELP_URL == '/help/panel#center-setup', str(ck and (ck['done_n'], ck['total'])))
check('O04 the admin sees it too; an education owner and an employment owner do not',
      oa.ts_onb_checklist() and eo.ts_onb_checklist() is None and member(panel('employment'), 'owner').ts_onb_checklist() is None)
check('O05 ts_panel\'s generic checklist gives way in a counseling-center panel only',
      oo.dash_checklist() == [] and eo.ts_onb_applies() is False)
check('O06 every open step carries a one-line why', all(s['why'] and '\n' not in s['why'] for s in oo.ts_onb_steps()))

# step 1: public name + logo (= the institution partner's image)
s1 = ostep(oo, 'identity')
check('O10 identity: open, the button goes to the identity section (name and logo live there)', not s1['done']
      and s1['url'].endswith('/settings#tsbr-org'), s1['url'])
check('O10b identity: the panel name counts as the name (the report falls back to it); only the logo is missing',
      'لوگو' in (s1['note'] or '') and 'نام مرکز' not in (s1['note'] or ''), str(s1['note']))
check('O10c the first open required step is the one current step', s1['current'] and s1['n'] == 1
      and sum(1 for s in oo.ts_onb_steps() if s['current']) == 1)
ob.ts_brand_save(oo, {'public_name': 'مرکز مشاوره راه‌اندازی'})
s1 = ostep(oo, 'identity')
check('O11 identity: a name without a logo is not enough; the button goes to the identity section', not s1['done']
      and s1['url'].endswith('/settings#tsbr-org') and 'لوگو' in (s1['note'] or ''), str(s1))
ob.partner_id.image_1920 = base64.b64encode(png).decode()
check('O12 identity: name and logo -> done (no button left)', ostep(oo, 'identity')['done'] and not ostep(oo, 'identity')['url'])
ob.partner_id.image_1920 = False         # the panel name counts as the name (O10b): only a missing logo leaves the step open
s1a = ostep(oa, 'identity')
check('O13 identity: the admin (no settings page) gets no button but who does it', not s1a['url'] and s1a['note'] == NOT_YOURS,
      str(s1a))
ob.partner_id.image_1920 = base64.b64encode(png).decode()

# step 2: an active clinician / clinic director; a pending colleague invitation is «در راه»
s2 = ostep(oo, 'counselors')
check('O20 counselors: open with a button to the colleague invitation form', s2['state'] == 'open' and s2['url'].endswith('/members#tsp-invite'))
env['ts.member.invite'].ts_create(oo, 'clinician', phone_raw='09127770955')
s2 = ostep(oo, 'counselors')
check('O21 counselors: a pending invitation is «در راه», not done', s2['state'] == 'way' and not s2['done'] and '۱' in (s2['note'] or ''), str(s2))
oc1 = member(ob, 'clinician')
check('O22 counselors: an active clinician -> done', ostep(oo, 'counselors')['done'])
oc1.active = False
check('O23 counselors: an inactive one does not count', not ostep(oo, 'counselors')['done'])
oc1.active = True

# step 3: the catalog of each counselor (rule in models/onboarding.py)
check('O30 catalog: one counselor -> done (nothing to divide)', ostep(oo, 'catalog')['done'])
oc2 = member(ob, 'clinician')
s3 = ostep(oo, 'catalog')
check('O31 catalog: two undecided counselors -> open, the button opens the first one\'s catalog section',
      not s3['done'] and s3['url'].endswith('/members/%d#tsp-catalog' % oc1.id) and '۰ از ۲' in s3['note'], str(s3))
changed = oc1.ts_set_catalog(oo, False)
s3 = ostep(oo, 'catalog')
check('O32 catalog: saving «همهٔ موارد پنل» unchanged counts as a decision; the button moves to the next counselor',
      changed is False and oc1.ts_catalog_seen_on and not s3['done'] and s3['url'].endswith('/members/%d#tsp-catalog' % oc2.id)
      and '۱ از ۲' in s3['note'], str(s3))
cinst = ob.ts_catalog_instruments()[:1]
oc2.ts_set_catalog(oo, True, cinst.ids)
check('O33 catalog: every counselor decided (one restricted) -> done', ostep(oo, 'catalog')['done'])
oc3 = member(ob, 'clinician')
oc3.write({'catalog_restricted': True, 'restrict_instrument_ids': [Command.set(cinst.ids)]})
check('O34 catalog: a restriction set elsewhere (back office) is a decision too', ostep(oo, 'catalog')['done'])
check('O35 catalog: a clinician cannot save a colleague\'s catalog, and a refused save marks nothing',
      raises(lambda: oc3.ts_set_catalog(oc1, False), UserError) and not oc3.ts_catalog_seen_on)

ck = oo.ts_onb_checklist()
check('O40 progress: identity, counselors and catalog done -> «3 of 6»', ck and ck['done_n'] == 3 and ck['total'] == 6,
      str(ck and ck['done_n']))

# step 4 (optional): any cap, or «بدون سقف بماند» once
s4 = ostep(oo, 'caps')
check('O41 caps: open, button to the caps table, the «بدون سقف» choice offered', not s4['done'] and s4['url'].endswith('/credits#tsb-caps')
      and s4['nocap'], str(s4))
oc1.ts_set_cap(oo, 10000000)
check('O42 caps: a cap on one counselor -> done', ostep(oo, 'caps')['done'] and not ostep(oo, 'caps')['nocap'])
oc1.ts_set_cap(oo, 0)
check('O43 caps: the cap removed -> open again', not ostep(oo, 'caps')['done'])
check('O44 caps: a counselor cannot record «بدون سقف»', raises(lambda: ob.ts_onb_mark_nocap(oc1), UserError))
n0 = Audit.search_count([('event_type', '=', 'onboarding.nocap'), ('workspace_id', '=', ob.id)])
check('O45 caps: «بدون سقف بماند» -> done, recorded once and audited', ob.ts_onb_mark_nocap(oa) is True and ob.ts_onb_mark_nocap(oo) is False
      and ostep(oo, 'caps')['done'] and Audit.search_count([('event_type', '=', 'onboarding.nocap'), ('workspace_id', '=', ob.id)]) == n0 + 1)

# step 5 (prepaid): available credit > 0, the balance is shown
s5 = ostep(oo, 'credit')
check('O50 credit: 0 -> open, the balance and the invoice rule shown, button asks the team for a top-up', not s5['done']
      and 'موجودی' in s5['note'] and 'فاکتور' in s5['note'] and ('/contact?topic=credit&panel=%s' % ob.code) in s5['url'], str(s5))
owal = env['ts.wallet']._for_workspace(ob)
owal.ts_grant(200000000, 'manual')
s5 = ostep(oo, 'credit')
check('O51 credit: a positive balance -> done, the balance still shown', s5['done'] and '۲۰٬۰۰۰٬۰۰۰ تومان' in s5['note'], str(s5))

# step 6: at least one invitation (a self-shared result is not one)
s6 = ostep(oo, 'invite')
check('O60 invite: open with «دعوت تازه»', not s6['done'] and s6['url'].endswith('/invites/new?fresh=1'))
oinst = oc1.allowed_instruments().filtered(lambda i: i.audience == 'adult' and i.code != 'TALENT-INV-15')[:1] or inst
A.create({'workspace_id': ob.id, 'instrument_id': oinst.id, 'invitee_name': 'مراجع آزمون راه‌اندازی', 'invited_by_id': oo.user_id.id})
check('O61 invite: one invitation -> done', ostep(oo, 'invite')['done'])
check('O62 every step done -> the checklist is gone', oo.ts_onb_checklist() is None and oa.ts_onb_checklist() is None)
og = panel('clinical', name='مرکز مشاوره در انتظار آزمون')
og.approved_on = False
ogo = member(og, 'owner')
s6g = ostep(ogo, 'invite')
check('O63 invite: a panel awaiting approval says so and offers no button', og.gated and not s6g['url'] and 'تأیید' in (s6g['note'] or ''),
      str(s6g))

ologo = base64.b64encode(png).decode()            # Odoo 20 binary values are lazy: keep a copy, not the attachment
ologo = ob.partner_id.image_1920
ob.partner_id.image_1920 = False                    # one step open again (no logo)
check('O70 an open step brings the checklist back', oo.ts_onb_checklist() and oo.ts_onb_checklist()['done_n'] == 5)
check('O71 a member cannot hide another member\'s checklist', raises(lambda: oo.ts_onb_set_hidden(oa, True), UserError))
oo.ts_onb_set_hidden(oo, True)
check('O72 «بعداً نشانم نده» hides it for that member only (the admin still sees it)',
      oo.ts_onb_checklist() is None and oo.ts_onb_hidden_on and oa.ts_onb_checklist() is not None)
check('O73 hidden: the generic checklist does not come back, and the help page still offers the restore',
      oo.dash_checklist() == [] and oo.ts_onb_applies(ignore_hidden=True))
oo.ts_onb_set_hidden(oo, False)
check('O74 «نمایش دوباره» restores it', oo.ts_onb_checklist() is not None and not oo.ts_onb_hidden_on)
st_ = {x['key']: x for x in oo.ts_onb_checklist()['status']}
check('O75 the two EOT-team conditions are status lines with a support link when waiting',
      st_['approval']['ok'] and st_['licences']['value'].endswith('تأییدشده') and oo.ts_onb_checklist()['total'] == 6
      and all(x['url'] is None or x['url'].startswith('/contact?topic=support&panel=') for x in st_.values()), str(st_))
ob.partner_id.image_1920 = ologo

# counselor first-run card
check('O80 card: a counselor without a title gets it; the owner and the admin never', oc2.ts_onb_card() and not oo.ts_onb_card()
      and not oa.ts_onb_card())
oc2.ts_brand_save(oc2, {'title': 'مشاور خانواده'})
check('O81 card: gone once a title is saved', not oc2.ts_onb_card())
ocu = member(ob, 'clinician', verified=False)
check('O82 card: a counselor waiting for verification gets it too (shown on the state page)', ocu.ts_onb_card())
check('O83 card: only the counselor closes it', raises(lambda: ocu.ts_onb_card_hide(oc1), UserError))
ocu.ts_onb_card_hide(ocu)
check('O84 card: closed -> gone', not ocu.ts_onb_card() and ocu.ts_onb_card_hidden_on)
check('O85 card: never in an education panel', member(wedu, 'counselor').ts_onb_card() is False)

print('SUMMARY %d/%d passed' % (sum(ok for _, ok in results), len(results)))
env.cr.rollback()
