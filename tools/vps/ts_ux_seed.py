# UX audit matrix (2026-10-11): every page route of website 4 in its main states, per role. Runs in `odoo shell` on a CLONE,
# after tools/prod/pv2_fixtures.py. Fictional data only; upserts. Writes /tmp/ux_matrix.json = {login: [paths]} for ts_shot.py.
# TS_UX_ONLY=take (`ts shots DB take`): only the participant (test-taker) journey, every page and state, see the block below.
import json, os, traceback
assert env.cr.dbname.startswith('eot_ts'), 'clones only'
portal = env.ref('base.group_portal')
U = env['res.users'].with_context(no_reset_password=True)
A, Att, M = env['ts.assignment'].sudo(), env['ts.attempt'].sudo(), env['ts.workspace.member'].sudo()
L = lambda k: 'ts.pv2.%s@example.invalid' % k
def user(k, name):
    return U.search([('login', '=', L(k))], limit=1) or U.create({'name': name, 'login': L(k), 'email': L(k), 'group_ids': [(6, 0, [portal.id])]})
def ws_of(name):
    return env['ts.workspace'].search([('name', '=', name)], limit=1)
EDU, CLIN, EMP = ws_of('پنل آزمایشی آموزشی'), ws_of('پنل آزمایشی بالینی'), ws_of('پنل آزمایشی استخدامی')
W = '/my/workspaces/%s' % EDU.id
inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')], limit=1)
oth = env['ts.instrument'].search([('state', '=', 'published'), ('code', '!=', 'TALENT-INV-15')], limit=1)
own = M.search([('workspace_id', '=', EDU.id), ('role', '=', 'owner')], limit=1)
cns = M.search([('workspace_id', '=', EDU.id), ('role', '=', 'counselor')], limit=1)
stu = user('edu.student', 'دانش‌آموز آزمایشی')
R = {}
def step(name, fn):
    try:
        R[name] = fn()
        env.cr.commit()
    except Exception as e:
        env.cr.rollback()
        print('SEED-SKIP', name, type(e).__name__, str(e)[:120])

ONLY = os.environ.get('TS_UX_ONLY', '')
if ONLY == 'take':
    # ================================================================ participant (test-taker) journey only (2026-10-13)
    # `ts shots DB take`: every page and state a participant sees, signed out and signed in, on phone widths. One clone-only
    # user per state (ts.take.<state>@example.invalid, fictional Persian names), upserted; panels from pv2_fixtures.py
    # (EDU, CLIN), an employment panel of its own for the HR invitation. Nothing is sent: mail servers are off on clones and
    # the SMS feature is switched on with the Kavenegar API pointed at a closed local port (FAKEKEY), so a send can only
    # fail. The sign-up code step is reached without any send: a sign-in code for the fictional mobile is stored with a
    # create_date in the future (the «wait a minute» cooldown answers before anything is sent) and a known code.
    from datetime import timedelta
    from urllib.parse import quote, urlencode
    from odoo import fields
    from odoo.exceptions import UserError
    TK = lambda k: 'ts.take.%s@example.invalid' % k
    NOW = fields.Datetime.now()
    PAGE = 10                                   # ts_assessment.controllers.main.PAGE_SIZE
    PHONE, CODE = '09127775101', '123456'       # sign-up flow (no account has this number)
    JOIN_PHONE = '09127775102'                  # colleague invitation bound to a mobile
    DEAD_API = 'http://127.0.0.1:9/v1/%s/%s.json'   # nothing listens on port 9: any SMS send fails, nothing leaves
    Inst, C = env['ts.instrument'].sudo(), env['ts.panel.client'].sudo()
    post_ = lambda path, **kw: 'POST %s %s' % (path, urlencode(kw))

    def vmode(inst_):
        v = inst_.current_version_id
        return v['mode'] if 'mode' in v._fields else 'single'

    def tuser(k, name):
        u = U.search([('login', '=', TK(k))], limit=1) or U.create(
            {'name': name, 'login': TK(k), 'email': TK(k), 'group_ids': [(6, 0, [portal.id])]})
        if u.name != name:
            u.name = name
        return u

    def likert_pick():
        cands = Inst.search([('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '=like', 'inventory_%')]) \
            .filtered(lambda i: vmode(i) == 'single' and not ('invite_only' in i._fields and i.invite_only))
        big = cands.filtered(lambda i: i.active_item_count > 2 * PAGE).sorted(lambda i: (i.active_item_count, i.id))
        return big[:1] or cands.sorted(lambda i: (-i.active_item_count, i.id))[:1]
    lik = likert_pick()
    if not lik:
        print('SEED-SKIP likert: no published adult inventory on this clone')

    def answer(a, items, n=0):
        have = a.answers_map()
        for i, it in enumerate(items):
            if it.id not in have:
                a.save_answer(it.id, 1 + (3 * i + it.id + n) % 5)

    # ------------------------------------------------------------ SMS feature on (fake, nothing can be sent) + sign-in code
    def sms_on():
        co = env.ref('ts_website.website_ts').company_id.sudo()
        if 'kv_enabled' not in co._fields or 'ts_sms_otp' not in co._fields or 'ts.signup.otp' not in env:
            raise UserError('ts_kavenegar / ts_sms are not installed')
        from odoo.addons.ts_sms.models.phone_otp import iran_mobile
        from odoo.addons.ts_sms.models.signup_otp import _h
        env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', DEAD_API)
        co.write({'kv_lines': '10004346'})
        co.write({'kv_enabled': True, 'kv_api_key': 'FAKEKEY', 'kv_sender': '10004346', 'ts_sms_otp': True,
                  'ts_sms_otp_template_id': False})
        phone = iran_mobile(PHONE)
        S = env['ts.signup.otp'].sudo()
        S.search([('phone', '=', phone)]).unlink()
        for u in U.search([('login', '=', phone)]):     # a name step posted by hand on an earlier run: free the number
            u.write({'active': False, 'login': 'old.take.%s' % u.id})
        env['res.partner'].sudo().search([('ts_phone', '=', phone)]).write({'ts_phone': False})
        rec = S.create({'phone': phone, 'salt': 'ts-take', 'code_hash': _h('ts-take', CODE),
                        'expires_at': NOW + timedelta(hours=6)})
        env.cr.execute("UPDATE ts_signup_otp SET create_date = (now() at time zone 'utc') + interval '6 hours' WHERE id = %s",
                       [rec.id])
        return co.id
    step('sms', sms_on)

    # ------------------------------------------------------------ invitations in every state (education panel, talent inventory)
    by = own.user_id

    def keep_open(a):
        """An open invitation stays open on a clone that is shot again weeks later (30-day expiry, cron flag)."""
        if not (a.user_id or a.withdrawn or a.declined) and (a.expired or (a.expires_at and a.expires_at < NOW + timedelta(days=2))):
            a.write({'expired': False, 'expires_at': NOW + timedelta(days=30)})
        return a

    def invite(name, ws=EDU, inst_=None, by_=None, unused=False):
        dom = [('workspace_id', '=', ws.id), ('invitee_name', '=', name)]
        if unused:      # an invitation that must still be open: one accepted, declined or withdrawn by hand is replaced
            dom += [('user_id', '=', False), ('withdrawn', '=', False), ('declined', '=', False)]
        a = A.search(dom, order='id desc', limit=1)
        if not a:
            a = A.create({'workspace_id': ws.id, 'instrument_id': (inst_ or inst).id, 'invitee_name': name,
                          'invited_by_id': (by_ or by).id})
        return a

    def inv_pending():
        return keep_open(invite('مهمان آزمایشی شرکت‌کننده', unused=True))
    step('inv_pending', inv_pending)

    def inv_expired():
        a = invite('بردیا آزمایشی')
        if not a.expired:
            a.write({'expired': True, 'expires_at': NOW - timedelta(days=2)})
        return a
    step('inv_expired', inv_expired)

    def inv_declined():
        a = invite('ترانه آزمایشی')
        if not a.declined:
            a.action_decline(tuser('declined', 'ترانه آزمایشی'))
        return a
    step('inv_declined', inv_declined)

    def inv_withdrawn():
        a = invite('هومن آزمایشی')
        if not a.withdrawn:
            a.action_withdraw()
        return a
    step('inv_withdrawn', inv_withdrawn)

    def inv_mine():
        """An open invitation linked to a signed-in account through its panel client (the «invite» next action of /my)."""
        u = tuser('inv', 'الهام آزمایشی')
        c = C.search([('workspace_id', '=', EDU.id), ('user_id', '=', u.id)], limit=1) or C.create(
            {'workspace_id': EDU.id, 'name': u.name, 'user_id': u.id, 'age_group': 'adult', 'source': 'invite'})
        a = A.search([('workspace_id', '=', EDU.id), ('client_id', '=', c.id), ('withdrawn', '=', False)], order='id desc', limit=1)
        return keep_open(a or A.create({'workspace_id': EDU.id, 'instrument_id': inst.id, 'invitee_name': u.name, 'client_id': c.id,
                                        'invited_by_id': by.id, 'note': 'لطفاً تا پایان هفته پاسخ بده.'}))
    step('inv_mine', inv_mine)

    def inv_other():
        tuser('other', 'پرهام آزمایشی')               # signed in with a name that differs from the invitee (G2-P12-1)
        return keep_open(invite('کیان آزمایشی', unused=True))
    step('inv_other', inv_other)

    def join_inv():
        from odoo.addons.ts_org.models.panel import norm_phone
        I = env['ts.member.invite'].sudo()
        x = I.search([('workspace_id', '=', EDU.id), ('phone', '=', norm_phone(JOIN_PHONE)), ('state', '=', 'pending'),
                      ('expires_at', '>', NOW)], limit=1)
        return x or I.ts_create(own, 'counselor', phone_raw=JOIN_PHONE)
    step('join', join_inv)

    def campaign(name, state, **vals):
        Cm = env['ts.campaign'].sudo()
        c = Cm.search([('workspace_id', '=', EDU.id), ('name', '=', name)], limit=1) or Cm.create(dict(
            {'workspace_id': EDU.id, 'name': name, 'instrument_id': inst.id, 'kind': 'open_link', 'created_by_id': own.id,
             'note': 'برای دانش‌آموزان پایهٔ دهم'}, **vals))
        if state != 'closed' and c.open_expires_at and c.open_expires_at < NOW + timedelta(days=1):
            c.open_expires_at = NOW + timedelta(days=14)    # a clone shot again weeks later
        if state == 'closed':
            c.ts_close()
        elif state == 'full' and c.joined_count() < c.open_max:
            c.ts_join(tuser('joiner', 'سینا آزمایشی'), 'سینا آزمایشی')
        if c.open_state() != state:
            raise UserError('open link is %s, not %s' % (c.open_state(), state))
        return c
    step('camp_ok', lambda: campaign('پیوند باز روز انتخاب رشته', 'ok'))
    step('camp_closed', lambda: campaign('پیوند باز بسته‌شدهٔ آزمایشی', 'closed'))
    step('camp_full', lambda: campaign('پیوند باز تکمیل‌ظرفیت آزمایشی', 'full', open_max=1))

    def minor():
        """A minor client of the education panel (guardian consent attested by the school): the consent page asks the
        child's own assent (S16, GRD-5)."""
        u = tuser('minor', 'آیدا آزمایشی')
        c = C.search([('workspace_id', '=', EDU.id), ('user_id', '=', u.id)], limit=1) or C.create(
            {'workspace_id': EDU.id, 'name': u.name, 'user_id': u.id, 'age_group': 'minor', 'source': 'manual',
             'guardian_name': 'مادر آیدا', 'guardian_relation': 'mother'})
        if c.guardian_consent == 'none':
            c.ts_attest_guardian(own)
        a = A.search([('workspace_id', '=', EDU.id), ('client_id', '=', c.id), ('withdrawn', '=', False)], order='id desc', limit=1) \
            or A.create({'workspace_id': EDU.id, 'instrument_id': inst.id, 'invitee_name': u.name, 'client_id': c.id,
                         'invited_by_id': by.id})
        if not a.user_id:
            a.action_accept(u, True)
        if a.attempt_id.state != 'consent':
            raise UserError('the minor attempt is past consent (state %s)' % a.attempt_id.state)
        return a.attempt_id
    step('minor', minor)

    # ------------------------------------------------------------ Likert player (self-taken, adult inventory)
    def likert(k, name, state):
        """consent | going (page 2 partly answered) | full (all answered, not sent) | done | hold (done, not released) | error"""
        u = tuser(k, name)
        if state in ('done', 'hold', 'error'):
            d = Att.search([('user_id', '=', u.id), ('instrument_id', '=', lik.id),
                            ('state', '=', 'error' if state == 'error' else 'done')], order='id desc', limit=1)
            if d:
                if state == 'hold' and d.released:
                    d.write({'released': False, 'released_at': False})
                if state == 'done' and d.submitted_at and d.submitted_at < NOW - timedelta(days=7):
                    d.submitted_at = NOW      # /my offers a result only for 14 days: keep the «result» next action
                return d
        a = Att.search([('user_id', '=', u.id), ('instrument_id', '=', lik.id), ('state', 'in', ('consent', 'in_progress'))],
                       order='id desc', limit=1) or Att.create(
            {'user_id': u.id, 'instrument_id': lik.id, 'version_id': lik.current_version_id.id})
        if state == 'consent':
            return a
        if a.state == 'consent':
            a.give_consent()
        items = a.active_items()
        answer(a, items[PAGE:PAGE + 6] if state == 'going' else items)
        if state in ('going', 'full'):
            return a
        if state == 'error':
            a.write({'state': 'error', 'error_message': 'خطای آزمایشی نمره‌گذاری (دادهٔ آزمایشی)'})
            return a
        a.action_submit()
        if a.state != 'done':
            raise UserError('scoring failed: %s' % (a.error_message or a.state))
        if state == 'hold':
            a.write({'released': False, 'released_at': False})
        return a
    if lik:
        for k, name, s in (('lik.consent', 'نرگس آزمایشی', 'consent'), ('lik.going', 'بهرام آزمایشی', 'going'),
                           ('lik.full', 'شیوا آزمایشی', 'full'), ('lik.done', 'مانی آزمایشی', 'done'),
                           ('lik.hold', 'رویا آزمایشی', 'hold'), ('lik.error', 'فرهاد آزمایشی', 'error')):
            step(k, lambda k=k, name=name, s=s: likert(k, name, s))

    # ------------------------------------------------------------ talent inventory (TALENT-INV-15, self-taken)
    PLANS = {'consent': None, 'name': [], 'stmt': [('ریاضی', 'all'), ('نقاشی', 4)],
             'straight': [('ریاضی', 'all'), ('فوتبال', 'same')], 'one': [('ریاضی', 'all')],
             'two': [('ریاضی', 'all'), ('نقاشی', 'all')], 'done': [('ریاضی', 'all'), ('نقاشی', 'all'), ('برنامه‌نویسی', 'all')]}

    def talent(k, name, state):
        u = tuser(k, name)
        if state == 'done':
            d = Att.search([('user_id', '=', u.id), ('instrument_id', '=', inst.id), ('state', '=', 'done')], order='id desc', limit=1)
            if d:
                return d
        a = Att.search([('user_id', '=', u.id), ('instrument_id', '=', inst.id), ('state', 'in', ('consent', 'in_progress'))],
                       order='id desc', limit=1) or Att.create(
            {'user_id': u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
        plan = PLANS[state]
        if plan is None:
            return a
        if a.state == 'consent':
            a.give_consent()
        if not a.field_ids:
            items = a.active_items()
            for n, (label, how) in enumerate(plan):
                f = a.ts_add_field(label)
                rows = items if how in ('all', 'same') else items[:how]
                for i, it in enumerate(rows):
                    a.ts_save_cell(f, it.id, 3 if how == 'same' else (i + 2 * n + i // 5) % 5 + 1)
                cells = f.cell_ids.sorted('id')
                for i, cell in enumerate(cells):          # about two minutes per field: not flagged as too fast
                    cell.answered_at = NOW - timedelta(seconds=8 * (len(cells) - i))
                if how == 'all' and a.ts_finish_field(f) != 'ok':
                    raise UserError('field %s not finished' % label)
        if state == 'done':
            a.action_submit()
            if a.state != 'done':
                raise UserError('talent scoring failed')
        return a
    for k, name, s in (('tal.consent', 'سپیده آزمایشی', 'consent'), ('tal.name', 'یاسمن آزمایشی', 'name'),
                       ('tal.stmt', 'امید آزمایشی', 'stmt'), ('tal.straight', 'مهرداد آزمایشی', 'straight'),
                       ('tal.one', 'نیلوفر آزمایشی', 'one'), ('tal.two', 'کامران آزمایشی', 'two'),
                       ('tal.done', 'هستی آزمایشی', 'done')):
        step(k, lambda k=k, name=name, s=s: talent(k, name, s))

    # ------------------------------------------------------------ battery (clinical panel of pv2_fixtures.py)
    def pick_battery():
        B = env['ts.battery'].sudo()
        cands = B.search([('state', '=', 'published'), ('for_clinical', '=', True), ('audience', '=', 'adult'),
                          ('has_retired', '=', False)]).filtered(
            lambda b: len(b.line_ids) >= 2 and all(vmode(l.instrument_id) == 'single' for l in b.line_ids))
        if cands:
            return cands.sorted(lambda b: (b.item_count, b.id))[:1]
        small = Inst.search([('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '=like', 'inventory_%')]) \
            .filtered(lambda i: vmode(i) == 'single').sorted(lambda i: (i.active_item_count, i.id))[:2]
        b = B.search([('code', '=', 'BAT-TS-TAKE')], limit=1) or B.create(
            {'code': 'BAT-TS-TAKE', 'name': 'مجموعهٔ آزمایشی آغاز مشاوره', 'audience': 'adult', 'for_clinical': True,
             'description': 'دو فهرست کوتاه برای آغاز گفت‌وگوی مشاوره (دادهٔ آزمایشی).',
             'line_ids': [fields.Command.create({'sequence': 10 * (n + 1), 'instrument_id': i.id}) for n, i in enumerate(small)]})
        if b.state != 'published':
            b.action_publish()
        return b
    bat = env['ts.battery']
    binv = M.browse()
    if 'ts.battery' in env and CLIN:
        try:
            bat = pick_battery()
            binv = M.search([('workspace_id', '=', CLIN.id), ('active', '=', True), ('role', 'in', ('clinician', 'clinic_director', 'owner'))],
                            order='role').filtered(lambda x: bat in x.allowed_batteries())[:1]
            env.cr.commit()
        except Exception as e:
            env.cr.rollback()
            print('SEED-SKIP battery', type(e).__name__, str(e)[:120])
    if not (bat and binv):
        print('SEED-SKIP battery: no published clinical battery or no clinical-panel member allowed to invite to it')

    def battery(k, name, state):
        """invited | consent | going (instrument 1 sent, instrument 2 half answered) | done"""
        u = tuser(k, name)
        a = A.search([('workspace_id', '=', CLIN.id), ('battery_id', '=', bat.id), ('invitee_name', '=', name)],
                     order='id desc', limit=1) or A.create(
            {'workspace_id': CLIN.id, 'battery_id': bat.id, 'instrument_id': bat.ts_first_instrument().id,
             'invited_by_id': binv.user_id.id, 'invitee_name': name})
        if a.withdrawn:
            a.withdrawn = False
        keep_open(a)
        if state == 'invited':
            return a
        if not a.user_id:
            a.action_accept(u, True)
        rows = a.ts_battery_attempts()
        if state == 'consent':
            return a
        if rows[0].state == 'consent':
            rows[0].give_consent()
        for n, t in enumerate(a.ts_battery_attempts()):
            if t.state == 'consent':
                t.give_consent()
            items = t.active_items()
            if state == 'going' and n >= 1:
                if n == 1 and t.state == 'in_progress':
                    answer(t, items[:max(1, len(items) // 2)])
                break
            if t.state == 'in_progress':
                answer(t, items, n)
                t.action_submit()
        return a
    if bat and binv:
        for k, name, s in (('bat.inv', 'مریم آزمایشی شرکت‌کننده', 'invited'), ('bat.consent', 'رضا آزمایشی شرکت‌کننده', 'consent'),
                           ('bat.going', 'نیما آزمایشی شرکت‌کننده', 'going'), ('bat.done', 'ژاله آزمایشی شرکت‌کننده', 'done')):
            step(k, lambda k=k, name=name, s=s: battery(k, name, s))

    # ------------------------------------------------------------ HR: a position invitation and its timed task (own panel)
    def hire_panel():
        if 'ts.hire.position' not in env:
            raise UserError('ts_hire is not installed')
        name = 'شرکت آزمایشی استخدام شرکت‌کننده'
        org = env['res.partner'].search([('name', '=', name), ('is_company', '=', True)], limit=1) or env['res.partner'].create(
            {'name': name, 'is_company': True})
        ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
            {'name': name, 'purpose': 'employment', 'partner_id': org.id})
        if not ws.approved_on:
            ws.write({'approved_on': '2026-01-01 00:00:00'})
        if ws.state != 'pilot':
            ws.state = 'pilot'
        hr = tuser('hr', 'مدیر منابع انسانی آزمایشی')
        mm = M.with_context(active_test=False).search([('workspace_id', '=', ws.id), ('user_id', '=', hr.id)], limit=1) or M.create(
            {'workspace_id': ws.id, 'user_id': hr.id, 'role': 'hr_admin'})
        mm.write({'active': True, 'role': 'hr_admin'})
        Occ = env['ts.onet.occupation'].sudo()
        occ = Occ.search([('code', 'in', ('13-2011.00', '15-1252.00'))], order='code', limit=1) or Occ.search(
            [('has_styles', '=', True), ('has_abilities', '=', True)], limit=1)
        P = env['ts.hire.position'].sudo()
        pos = P.search([('workspace_id', '=', ws.id), ('name', '=', 'کارشناس حسابداری (آزمایشی)')], limit=1) or P.create(
            {'name': 'کارشناس حسابداری (آزمایشی)', 'workspace_id': ws.id, 'occupation_id': occ.id, 'battery_choice': 'short'})
        if pos.state != 'open':
            pos.state = 'open'
        if not pos.battery_id:
            raise UserError('battery BAT-HR-SHORT is missing')
        return {'ws': ws, 'hr': hr, 'pos': pos}
    step('hire', hire_panel)

    def hire_inv(k, name, state):
        h = R['hire']
        u = tuser(k, name)
        a = A.search([('position_id', '=', h['pos'].id), ('invitee_name', '=', name)], limit=1) or A.create(
            {'workspace_id': h['ws'].id, 'battery_id': h['pos'].battery_id.id, 'position_id': h['pos'].id,
             'instrument_id': h['pos'].battery_id.ts_first_instrument().id, 'invitee_name': name, 'invited_by_id': h['hr'].id})
        keep_open(a)
        if state == 'invited':
            return a
        if not a.user_id:
            a.action_accept(u, share=True)
        q = a.ts_battery_attempts()[0]
        if q.state == 'consent':
            q.give_consent()
        if q.state == 'in_progress':
            for it in q.active_items():
                q.save_answer(it.id, 3 if it.factor_id.code != 'ATTN' else 1)   # the attention items answered as asked
            q.action_submit()
        for t in a.ts_battery_attempts()[1:2].filtered(lambda x: x.state == 'consent'):
            if hasattr(t, 'ts_battery_copy_consent'):
                t.ts_battery_copy_consent()            # what the player does when the task opens
        return a
    if 'hire' in R:
        step('hire.inv', lambda: hire_inv('hire.inv', 'داوطلب آزمایشی حسابداری', 'invited'))
        step('hire.task', lambda: hire_inv('hire.task', 'داوطلب دوم آزمایشی حسابداری', 'task'))

    # ------------------------------------------------------------ timed task player (ts_tasks, self-standing attempts)
    tinst = Inst.search([('code', '=', 'TASK-REASON')], limit=1) if 'ts.task.norm' in env else Inst

    def task(k, name, state):
        u = tuser(k, name)
        a = Att.search([('user_id', '=', u.id), ('instrument_id', '=', tinst.id), ('state', 'in', ('consent', 'in_progress'))],
                       order='id desc', limit=1) or Att.create(
            {'user_id': u.id, 'instrument_id': tinst.id, 'version_id': tinst.current_version_id.id})
        if a.state == 'consent':
            a.give_consent()
        if state == 'mid':                         # block 1 closed, block 2 started (the page offers «ادامهٔ بخش»)
            st = a._ts_state()
            if not st['blocks'][0]['done']:
                if not st['blocks'][0]['started']:
                    a.ts_task_start(0)
                a.ts_task_finish(0)
            if not a._ts_state()['blocks'][1]['started']:
                a.ts_task_start(1)
        return a
    if tinst:
        step('task.new', lambda: task('task.new', 'آرمان آزمایشی', 'new'))
        step('task.mid', lambda: task('task.mid', 'سحر آزمایشی', 'mid'))
    else:
        print('SEED-SKIP task: ts_tasks (TASK-REASON) is not installed')
    step('fresh', lambda: tuser('fresh', 'پریسا آزمایشی'))   # an account with nothing yet (empty /my and /my/assessments)

    # ------------------------------------------------------------ the matrix
    tok = lambda k: R[k].access_token
    pub = ['/assessments']
    nxt = '/invite/%s' % R['inv_pending'].token if 'inv_pending' in R else '/my'
    pub += ['/signup', '/signup?next=%s' % quote(nxt, safe='/')]
    if 'sms' in R:
        # the code step and the name step of the mobile sign-up, reached without any SMS (see sms_on)
        pub += [post_('/signup/send', phone=PHONE, next=nxt), '/signup?step=code&msg=sent&next=%s' % quote(nxt, safe='/'),
                post_('/signup/verify', code=CODE, next=nxt), '/signup?step=name&next=%s' % quote(nxt, safe='/')]
    for key in ('inv_pending', 'inv_expired', 'inv_declined', 'inv_withdrawn'):
        if key in R:
            pub.append('/invite/%s' % R[key].token)
    if 'inv_pending' in R and hasattr(R['inv_pending'], 'ts_short_code'):
        pub.append('/i/%s' % R['inv_pending'].ts_short_code())      # SMS short link: 302 to the invitation page
    if 'join' in R:
        pub.append('/join/%s' % R['join'].token)
    for key in ('camp_ok', 'camp_closed', 'camp_full'):
        if key in R:
            pub.append('/c/%s' % R[key].open_token)
    if lik:
        pub.append('/assessments/%s' % quote(lik.slug))
    pub.append('/assessments/%s' % quote(inst.slug))
    if 'lik.consent' in R:
        pub.append('/take/%s' % tok('lik.consent'))                 # an old player link while signed out -> sign-in page
    m = {'': pub}
    if 'fresh' in R:
        m[TK('fresh')] = ['/my', '/my/assessments']
    if 'inv_mine' in R:
        t = R['inv_mine'].token
        m[TK('inv')] = ['/my', '/invite/%s' % t, '/invite/%s?decline=1' % t] + (
            ['/c/%s' % R['camp_ok'].open_token] if 'camp_ok' in R else [])
    if 'inv_other' in R:
        m[TK('other')] = ['/invite/%s' % R['inv_other'].token]
    if 'minor' in R:
        m[TK('minor')] = ['/take/%s' % tok('minor'), '/take/%s?error=assent' % tok('minor')]
    if 'lik.consent' in R:
        t = tok('lik.consent')
        m[TK('lik.consent')] = ['/take/%s' % t, '/take/%s?error=consent' % t, '/take/%s?error=age' % t,
                                '/take/%s?error=guardian_ok' % t]
    if 'lik.going' in R:
        t, n_pages = tok('lik.going'), -(-len(R['lik.going'].active_items()) // PAGE)
        m[TK('lik.going')] = ['/my', '/take/%s?page=1' % t, '/take/%s?page=2' % t] + (
            ['/take/%s?page=%d' % (t, n_pages)] if n_pages > 2 else []) + [
            '/take/%s/review' % t, '/my/assessments', '/assessments/%s' % quote(lik.slug)]
    if 'lik.full' in R:
        m[TK('lik.full')] = ['/take/%s/review' % tok('lik.full')]
    if 'lik.done' in R:
        i = R['lik.done'].id
        m[TK('lik.done')] = ['/my/assessments/%s?submitted=1' % i, '/my/assessments/%s' % i, '/my', '/my/assessments']
    if 'lik.hold' in R:
        m[TK('lik.hold')] = ['/my/assessments/%s' % R['lik.hold'].id]
    if 'lik.error' in R:
        m[TK('lik.error')] = ['/take/%s' % tok('lik.error')]
    for k in ('tal.consent', 'tal.name', 'tal.one'):
        if k in R:
            m[TK(k)] = ['/take/%s' % tok(k)]
    if 'tal.stmt' in R:
        t = tok('tal.stmt')
        m[TK('tal.stmt')] = ['/take/%s' % t, '/take/%s?p=1&error=missing' % t, '/take/%s?p=2' % t]
    if 'tal.straight' in R:
        m[TK('tal.straight')] = ['/take/%s?v=straight' % tok('tal.straight')]
    if 'tal.two' in R:
        t = tok('tal.two')
        m[TK('tal.two')] = ['/take/%s' % t, '/take/%s?v=name' % t, '/take/%s?error=finish' % t]
    if 'tal.done' in R:
        i = R['tal.done'].id
        m[TK('tal.done')] = ['/my/assessments/%s?submitted=1' % i, '/my/assessments/%s' % i]
    if 'bat.inv' in R:
        m[TK('bat.inv')] = ['/invite/%s' % R['bat.inv'].token]
    if 'bat.consent' in R:
        m[TK('bat.consent')] = ['/take/%s' % R['bat.consent'].ts_battery_attempts()[0].access_token]
    if 'bat.going' in R:
        ra = R['bat.going'].ts_battery_attempts()
        m[TK('bat.going')] = ['/take/%s' % ra[1].access_token, '/take/%s/next' % ra[0].access_token,
                              '/my/assessments/battery/%s' % R['bat.going'].id, '/my', '/my/assessments']
    if 'bat.done' in R:
        m[TK('bat.done')] = ['/my/assessments/battery/%s?submitted=1' % R['bat.done'].id]
    if 'hire.inv' in R:
        m[TK('hire.inv')] = ['/invite/%s' % R['hire.inv'].token]
    if 'hire.task' in R:
        rest = R['hire.task'].ts_battery_attempts()[1:2]
        if rest:
            m[TK('hire.task')] = ['/take/%s' % rest.access_token]
    for k in ('task.new', 'task.mid'):
        if k in R:
            m[TK(k)] = ['/take/%s' % tok(k)]
    env.cr.commit()                                # ts_short_code() may have written a short code
    json.dump(m, open('/tmp/ux_matrix.json', 'w'))
    shots = sum(1 for v in m.values() for p in v if not p.startswith('POST '))
    print('UXMATRIX take', ' '.join('%s=%d' % ((k or 'public').split('@')[0].replace('ts.take.', ''), len(v)) for k, v in m.items()),
          'users', len(m) - 1, 'pages', shots, 'posts', sum(len(v) for v in m.values()) - shots)
else:
    done_as = A.search([('workspace_id', '=', EDU.id), ('invitee_name', '=', 'دانش‌آموز آزمایشی'), ('withdrawn', '=', False)], limit=1)
    done_at = done_as.attempt_id if 'attempt_id' in done_as._fields else Att.search([('user_id', '=', stu.id), ('state', '=', 'done')], limit=1)
    client = done_as.client_id if 'client_id' in done_as._fields else env['ts.panel.client']
    def mk_client():
        C = env['ts.panel.client'].sudo()
        return C.search([('workspace_id', '=', EDU.id), ('name', '=', 'نگار آزمایشی')], limit=1) or C.create(
            {'workspace_id': EDU.id, 'name': 'نگار آزمایشی', 'email': 'negar@example.invalid'})
    step('client2', mk_client)
    def mk_group():
        G = env['ts.panel.group'].sudo()
        return G.search([('workspace_id', '=', EDU.id), ('name', '=', 'کلاس دهم الف')], limit=1) or G.create(
            {'workspace_id': EDU.id, 'name': 'کلاس دهم الف', 'kind': 'class'})
    step('group', mk_group)
    def mk_camp(kind, name):
        C = env['ts.campaign'].sudo()
        return C.search([('workspace_id', '=', EDU.id), ('name', '=', name)], limit=1) or C.create(
            {'workspace_id': EDU.id, 'name': name, 'instrument_id': inst.id, 'kind': kind, 'created_by_id': own.id})
    step('camp_list', lambda: mk_camp('list', 'دعوت کلاس دهم'))
    step('camp_open', lambda: mk_camp('open_link', 'پیوند باز نمایشگاه'))
    def mk_pending():
        return A.search([('workspace_id', '=', EDU.id), ('invitee_name', '=', 'مهمان آزمایشی')], limit=1) or A.create(
            {'workspace_id': EDU.id, 'instrument_id': inst.id, 'invitee_name': 'مهمان آزمایشی', 'invited_by_id': own.user_id.id})
    step('pending', mk_pending)
    def mk_minv():
        I = env['ts.member.invite'].sudo()
        return I.search([('workspace_id', '=', EDU.id), ('state', '=', 'pending')], limit=1) if 'state' in I._fields and I.search_count(
            [('workspace_id', '=', EDU.id)]) else I.ts_create(own, 'counselor', email_raw='colleague.ux@example.invalid')
    step('minv', mk_minv)
    step('import', lambda: env['ts.job'].sudo().ts_import_prepare(own, 'ux.csv', 'نام,موبایل\nعلی آزمایشی,09120000099\n'.encode()))
    step('export', lambda: env['ts.job'].sudo().ts_export_create(own, 'export_clients', 'csv'))
    # participant attempts in every player state (one user per state: one open talent attempt per user)
    def talent_state(k, state):
        u = user(k, 'شرکت‌کنندهٔ آزمایشی %s' % k[-1])
        a = Att.search([('user_id', '=', u.id), ('instrument_id', '=', inst.id), ('state', '!=', 'done')], limit=1) or Att.create(
            {'user_id': u.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
        if state != 'consent' and a.state == 'consent':
            a.give_consent()
        if state in ('matrix', 'review') and not a.field_ids:
            items = a.active_items()
            for n, label in enumerate(['ریاضی', 'نقاشی']):
                f = a.ts_add_field(label)
                for i, it in enumerate(items if state == 'review' or n == 0 else items[:4]):
                    a.ts_save_cell(f, it.id, (i + n) % 5 + 1)
                if state == 'review' or n == 0:
                    a.ts_finish_field(f)
        return a
    for k, s in (('ux.p1', 'consent'), ('ux.p2', 'fields'), ('ux.p3', 'matrix'), ('ux.p4', 'review')):
        step(k, lambda k=k, s=s: talent_state(k, s))
    def likert(state):
        a = Att.search([('user_id', '=', stu.id), ('instrument_id', '=', oth.id), ('state', '!=', 'done')], limit=1) or Att.create(
            {'user_id': stu.id, 'instrument_id': oth.id, 'version_id': oth.current_version_id.id})
        if state == 'progress' and a.state == 'consent':
            a.give_consent()
        return a
    step('likert', lambda: likert('progress'))

    tok = lambda k: R[k].access_token if k in R else None
    pub = ['/panel', '/panel/terms', '/signup', '/web/login', '/web/reset_password', '/help/panel', '/assessments/%s' % inst.slug,
           '/my/workspaces/new', '/contact?topic=credit']     # «درخواست شارژ اعتبار» without a panel (signed out)
    if 'pending' in R: pub.append('/invite/%s' % R['pending'].token)
    if 'minv' in R and R['minv']: pub.append('/join/%s' % R['minv'].token)
    if 'camp_open' in R and R['camp_open'].open_token: pub.append('/c/%s' % R['camp_open'].open_token)
    o = [W + x for x in ('', '/home', '/clients', '/clients/new', '/groups', '/invites', '/invites/new', '/campaigns', '/campaigns/new',
                         '/members', '/reports', '/reports/group', '/credits', '/exports', '/audit', '/settings', '/settings/transfer',
                         '/settings/close', '/import', '/legacy')]
    o += ['/my/workspaces', '/my/workspaces/new', '/help/roles', '/my/notifications', '/my/notifications/prefs', '/my/reauth',
          '/my/sessions', '/my/privacy', '/my/sharing', '/my', '/my/account', '/my/phone']
    if client:
        o += [W + '/clients/%s' % client.id, W + '/clients/%s/edit' % client.id]
        if done_at: o.append(W + '/clients/%s/r/%s' % (client.id, done_at.id))
    if done_at: o.append(W + '/p/%s' % done_at.id)
    if 'group' in R: o.append(W + '/groups/%s' % R['group'].id)
    for k in ('camp_list', 'camp_open'):
        if k in R: o += [W + '/campaigns/%s' % R[k].id]
    if 'camp_list' in R: o.append(W + '/campaigns/%s/sheet' % R['camp_list'].id)
    if 'pending' in R: o += [W + '/invites/%s' % R['pending'].id, W + '/a/%s' % R['pending'].id]
    if cns: o += [W + '/members/%s' % cns.id, W + '/members/%s/deactivate' % cns.id]
    if 'import' in R: o += [W + '/import/%s/map' % R['import'].id, W + '/import/%s/review' % R['import'].id]
    if 'export' in R: o.append(W + '/jobs/%s' % R['export'].id)
    c = [W + x for x in ('', '/clients', '/reports', '/invites', '/groups')] + ['/my/workspaces', '/my']
    if client:
        c.append(W + '/clients/%s' % client.id)
        if done_at: c.append(W + '/clients/%s/r/%s' % (client.id, done_at.id))
    s = ['/my', '/my/assessments', '/my/sharing', '/my/privacy', '/my/notifications', '/my/sessions', '/my/phone', '/my/account']
    if done_at: s += ['/my/assessments/%s' % done_at.id, '/my/assessments/%s/share' % done_at.id]
    if 'likert' in R: s.append('/take/%s' % tok('likert'))
    if 'pending' in R: s.append('/invite/%s' % R['pending'].token)
    m = {'': pub, L('edu.owner'): o, L('edu.counselor'): c, L('edu.student'): s}
    for k in ('ux.p1', 'ux.p2', 'ux.p3', 'ux.p4'):
        if k in R:
            m[L(k)] = ['/take/%s' % tok(k)] + (['/take/%s/review' % tok(k)] if k == 'ux.p4' else [])
    for key, ws in (('clin.clinician', CLIN), ('emp.reviewer', EMP)):
        if ws: m[L(key)] = ['/my/workspaces/%s' % ws.id, '/my/workspaces/%s/clients' % ws.id, '/my/workspaces/%s/reports' % ws.id]

    # ---------------------------------------------------------------- battery pages (clinic phase 3, 2026-10-11)
    # On the fixtures of tools/prod/ts_http_battery.py (counseling-center panel in granted mode, battery BAT-TEST-HTTP, owner /
    # counselor c1 / participant p1 with a finished battery). Adds: a battery invitation not accepted (uxb1), accepted but no
    # consent yet (uxb2), instrument 1 submitted + instrument 2 half answered (uxb3), a battery campaign. Upserts; the HTTP
    # suite withdraws open invitations of its panel on every run, so the seed reopens its own.
    BL = lambda n: 'ts.bat.%s.http@example.invalid' % n
    BU = lambda n: 'ts.bat.%s@example.invalid' % n
    bat = env['ts.battery'].sudo().search([('code', '=', 'BAT-TEST-HTTP')], limit=1)
    borg = env['res.partner'].search([('name', '=', 'پنل آزمون مجموعه وب')], limit=1)
    BWS = env['ts.workspace'].search([('partner_id', '=', borg.id)], limit=1) if borg else env['ts.workspace']
    busr = {n: U.search([('login', '=', BL(n))], limit=1) for n in ('owner', 'c1', 'p1')}
    if not (bat and BWS and all(busr.values())):
        print('SEED-SKIP battery: run tools/prod/ts_http_battery.py on this clone first')
    else:
        BW = '/my/workspaces/%s' % BWS.id
        bmo = M.search([('workspace_id', '=', BWS.id), ('user_id', '=', busr['owner'].id)], limit=1)
        bm1 = M.search([('workspace_id', '=', BWS.id), ('user_id', '=', busr['c1'].id)], limit=1)
        for n, fake in (('p1', 'سارا آزمایشی'), ('owner', 'لیلا آزمایشی'), ('c1', 'سمیرا آزمایشی'), ('c2', 'کاوه آزمایشی')):
            u = busr.get(n) or U.search([('login', '=', BL(n))], limit=1)
            if u and u.name == 'آزمون جریان':      # ensure_user's default name; a realistic name for the screenshots
                u.name = fake
        env.cr.commit()
        bdone = A.search([('workspace_id', '=', BWS.id), ('battery_id', '=', bat.id), ('user_id', '=', busr['p1'].id),
                          ('state', '=', 'done')], order='id desc', limit=1)

        def bat_user(k, name):
            return U.search([('login', '=', BU(k))], limit=1) or U.create(
                {'name': name, 'login': BU(k), 'email': BU(k), 'group_ids': [(6, 0, [portal.id])]})

        def bat_inv(k, name, state):
            """state: invited | consent | going (instrument 1 done, instrument 2 half answered)."""
            u = bat_user(k, name)
            a = A.search([('workspace_id', '=', BWS.id), ('battery_id', '=', bat.id), ('invitee_name', '=', name)],
                         order='id desc', limit=1) or A.create(
                {'workspace_id': BWS.id, 'instrument_id': bat.ts_first_instrument().id, 'battery_id': bat.id,
                 'invited_by_id': busr['c1'].id, 'invitee_name': name})
            if a.withdrawn:                 # ts_http_battery.py withdraws the open invitations of its panel on every run
                a.withdrawn = False
            if state == 'invited':
                return a
            if not a.user_id:
                a.action_accept(u, True)
            rows = a.ts_battery_attempts()
            if state == 'going':
                first, second = rows[0], rows[1]
                if first.state == 'consent':
                    first.give_consent()
                if first.state == 'in_progress':
                    for it in first.active_items():
                        first.save_answer(it.id, 1 + it.id % 5)
                    first.action_submit()
                if second.state == 'in_progress' and not second.answer_ids:
                    items = second.active_items()
                    for it in items[:max(1, len(items) // 2)]:
                        second.save_answer(it.id, 1 + it.id % 5)
            return a
        step('bat_inv', lambda: bat_inv('uxb1', 'مریم آزمایشی', 'invited'))
        step('bat_consent', lambda: bat_inv('uxb2', 'رضا آزمایشی', 'consent'))
        step('bat_going', lambda: bat_inv('uxb3', 'نیما آزمایشی', 'going'))

        def bat_camp():
            C = env['ts.campaign'].sudo()
            return C.search([('workspace_id', '=', BWS.id), ('name', '=', 'ارزیابی آغاز مشاوره پاییز')], limit=1) or C.create(
                {'workspace_id': BWS.id, 'name': 'ارزیابی آغاز مشاوره پاییز', 'battery_id': bat.id, 'kind': 'open_link',
                 'created_by_id': bmo.id})
        step('bat_camp', bat_camp)

        bo = ([BW + '/members/%s' % bm1.id] if bm1 else []) + [BW + '/campaigns/new']
        if 'bat_camp' in R: bo.append(BW + '/campaigns/%s' % R['bat_camp'].id)
        m[BL('owner')] = bo
        if 'bat_camp' in R and R['bat_camp'].open_token: pub.append('/c/%s' % R['bat_camp'].open_token)
        b1 = [BW + '/invites/new?fresh=1']
        if bdone and bdone.client_id:
            b1 += [BW + '/invites/new?fresh=1&client=%s' % bdone.client_id.id, BW + '/clients/%s' % bdone.client_id.id,
                   BW + '/clients/%s/b/%s' % (bdone.client_id.id, bdone.id)]
        if 'bat_going' in R: b1.append(BW + '/invites/%s' % R['bat_going'].id)
        m[BL('c1')] = b1
        if bdone: m[BL('p1')] = ['/my/assessments/battery/%s' % bdone.id, '/my/assessments']
        if 'bat_inv' in R: m[BU('uxb1')] = ['/invite/%s' % R['bat_inv'].token]
        if 'bat_consent' in R: m[BU('uxb2')] = ['/take/%s' % R['bat_consent'].ts_battery_attempts()[0].access_token]
        if 'bat_going' in R:
            ra = R['bat_going'].ts_battery_attempts()
            m[BU('uxb3')] = ['/take/%s' % ra[1].access_token, '/take/%s/next' % ra[0].access_token, '/my/assessments', '/my']

    # ---------------------------------------------------------------- prepaid billing pages (clinic phase 4, 2026-10-11)
    # On the fixtures of tools/prod/ts_http_billing.py (prepaid counseling-center panel «پنل آزمون شارژ وب», owner / capped
    # counselor c1 / participant p1, prices on two instruments). Adds: a price on BAT-TEST-HTTP, a paid top-up invoice, enough
    # credit, one open invitation (hold), one completed invitation (debit) when the suite left none, and a cap with room for
    # the cheap items only. Matrix entries «POST path body» are form posts ts_shot.py makes (no screenshot) to reach the wizard
    # steps 2/4 and the open-link campaign form. Back office (/odoo) is out of scope.
    from urllib.parse import urlencode
    from odoo import fields
    QL = lambda n: 'ts.bill.%s.http@example.invalid' % n
    qorg = env['res.partner'].search([('name', '=', 'پنل آزمون شارژ وب')], limit=1)
    QWS = env['ts.workspace'].search([('partner_id', '=', qorg.id)], limit=1) if qorg else env['ts.workspace']
    qusr = {n: U.search([('login', '=', QL(n))], limit=1) for n in ('owner', 'c1', 'p1')}
    if not (QWS and QWS.billing_mode == 'prepaid' and all(qusr.values())):
        print('SEED-SKIP billing: run tools/prod/ts_http_billing.py on this clone first')
    else:
        QW = '/my/workspaces/%s' % QWS.id
        for n, fake in (('owner', 'مهسا آزمایشی'), ('c1', 'بهاره آزمایشی'), ('p1', 'آرش آزمایشی')):
            if qusr[n].name == 'آزمون جریان':
                qusr[n].name = fake
        env.cr.commit()
        qmo = M.search([('workspace_id', '=', QWS.id), ('user_id', '=', qusr['owner'].id)], limit=1)
        qm1 = M.search([('workspace_id', '=', QWS.id), ('user_id', '=', qusr['c1'].id)], limit=1)
        qinst = env['ts.instrument'].search([('state', '=', 'published'), ('audience', '=', 'adult'), ('code', '=like', 'inventory_%')]) \
            .sorted(lambda i: (i.active_item_count, i.id))[:2]
        qi1, qi2 = qinst[0], qinst[1]
        wal = env['ts.wallet']._for_workspace(QWS)
        Txn = env['ts.wallet.txn'].sudo()

        def bill_battery_price():
            b = env['ts.battery'].sudo().search([('code', '=', 'BAT-TEST-HTTP'), ('state', '=', 'published')], limit=1)
            if b:
                b._ts_ensure_product()
                if not b.ts_list_price:
                    b.ts_list_price = 1800000       # Rial (۱۸۰٬۰۰۰ تومان); live batteries cost 70% of their parts
            return b
        step('bill_bat', bill_battery_price)

        def bill_invoice():
            Mv = env['account.move'].sudo()
            inv = Mv.search([('ts_workspace_id', '=', QWS.id), ('ref', '=', 'TS-UX-PAID')], limit=1)
            if not inv:
                inv = Mv.create({'move_type': 'out_invoice', 'partner_id': qorg.id, 'ts_workspace_id': QWS.id, 'ref': 'TS-UX-PAID',
                                 'invoice_line_ids': [fields.Command.create({'product_id': env.ref('ts_billing.product_topup').id,
                                                                             'quantity': 1, 'price_unit': 20000000,
                                                                             'tax_ids': [fields.Command.clear()]})]})
                inv.action_post()
            if inv.payment_state not in ('paid', 'in_payment'):
                env['account.payment.register'].with_context(active_model='account.move', active_ids=inv.ids).create({}) \
                    .action_create_payments()
            return inv
        step('bill_invoice', bill_invoice)

        def bill_credit():
            avail = wal.ts_available()
            if avail < 20000000:
                wal.ts_grant(20000000 - avail, 'manual')
            return wal
        step('bill_credit', bill_credit)

        def bill_done():
            """One completed invitation of c1 this month (the HTTP suite leaves one; recreate it on a clone where it has not run)."""
            if Txn.search_count([('wallet_id', '=', wal.id), ('type', '=', 'debit_usage'), ('amount', '<', 0)]):
                return True
            a = A.create({'workspace_id': QWS.id, 'instrument_id': qi1.id, 'invitee_name': 'آرش آزمایشی',
                          'invited_by_id': qusr['c1'].id})
            a.action_accept(qusr['p1'], True)
            at = a.attempt_id
            if at.state == 'consent':
                at.give_consent()
            for it in at.active_items():
                at.save_answer(it.id, 1 + it.id % 5)
            at.action_submit()
            return a
        step('bill_done', bill_done)

        def bill_hold():
            a = A.search([('workspace_id', '=', QWS.id), ('invitee_name', '=', 'پریا آزمایشی'), ('withdrawn', '=', False)],
                         order='id desc', limit=1)
            if a and a.price_held and a.state not in ('done', 'withdrawn', 'declined'):
                return a
            if qm1.monthly_cap:
                qm1.sudo().write({'monthly_cap': 0})     # a full cap from the suite would refuse the hold
            return A.create({'workspace_id': QWS.id, 'instrument_id': qi1.id, 'invitee_name': 'پریا آزمایشی',
                             'invited_by_id': qusr['c1'].id})
        step('bill_hold', bill_hold)

        def bill_cap():
            spent = wal.ts_month_spend(qm1)
            # room (2,000,000-2,099,999 Rial) for the instrument (1,200,000) and the battery (1,800,000), not for the dear one
            # (2,500,000, ts_http_billing.py P2)
            cap = -(-(spent + 2000000) // 100000) * 100000
            if int(qm1.monthly_cap) != cap:
                qm1.sudo().write({'monthly_cap': cap})
            return cap
        step('bill_cap', bill_cap)

        post_ = lambda path, **kw: 'POST %s %s' % (path, urlencode(kw))
        shot_ = lambda path, **kw: 'POSTSHOT %s %s' % (path, urlencode(kw))     # the answer of the post is captured (G7-P4-3)
        m[QL('owner')] = [QW, QW + '/credits', QW + '/members/%s' % qm1.id,
                          shot_(QW + '/campaigns/new', step='review', kind='open_link', name='پیوند باز پذیرش پاییز',
                                item_kind='single', instrument_id=qi1.id, open_max=20, open_days=14),
                          QW + '/campaigns/new?keep=1',
                          QWS.ts_topup_request_url()]          # «درخواست شارژ اعتبار»: /contact?topic=credit&panel=<code>
        m[QL('c1')] = [QW, QW + '/credits', QW + '/invites/new?fresh=1',
                       post_(QW + '/invites/new', step=1, new_name='نسترن آزمایشی', new_phone='', new_email='', new_age='adult'),
                       QW + '/invites/new?step=2',
                       post_(QW + '/invites/new', step=2, item_kind='single', instrument_id=qi1.id),
                       QW + '/invites/new?step=3',
                       post_(QW + '/invites/new', step=3, deadline='', note=''),
                       QW + '/invites/new?step=4']

    # ---------------------------------------------------------------- HR hiring pages (ts_hire, 2026-10-12)
    # On the fixtures of tools/prod/ts_http_hire.py (employment panel «شرکت آزمون استخدام وب», hr_admin hr, candidates).
    # Adds one open invitation for cand2 with the questionnaire done, so the task player and the invitation page are shot.
    HL = lambda n: 'ts.hire.%s.http@example.invalid' % n
    horg = env['res.partner'].search([('name', '=', 'شرکت آزمون استخدام وب')], limit=1)
    HWS = env['ts.workspace'].search([('partner_id', '=', horg.id)], limit=1) if horg else env['ts.workspace']
    if not HWS or 'ts.hire.position' not in env:
        print('SEED-SKIP hire: run tools/prod/ts_http_hire.py on this clone first')
    else:
        HW = '/my/workspaces/%s' % HWS.id
        hp = env['ts.hire.position'].sudo().search([('workspace_id', '=', HWS.id), ('state', '=', 'open')], limit=1)
        ha = hp.assignment_ids.filtered(lambda x: x.ts_hire_complete)[:1] if hp else env['ts.assignment']
        c2 = U.search([('login', '=', HL('cand2'))], limit=1)

        def hire_pending():
            old = hp.assignment_ids.filtered(lambda x: x.invitee_name == 'داوطلب دوم آزمایشی')[:1]
            if old:
                return old
            return A.create({'workspace_id': HWS.id, 'battery_id': hp.battery_id.id, 'position_id': hp.id,
                             'instrument_id': hp.battery_id.ts_first_instrument().id, 'invitee_name': 'داوطلب دوم آزمایشی'})
        def hire_task():
            x = A.search([('workspace_id', '=', HWS.id), ('invitee_name', '=', 'داوطلب سوم آزمایشی')], limit=1) or A.create(
                {'workspace_id': HWS.id, 'battery_id': hp.battery_id.id, 'position_id': hp.id,
                 'instrument_id': hp.battery_id.ts_first_instrument().id, 'invitee_name': 'داوطلب سوم آزمایشی'})
            if not x.user_id:
                x.action_accept(c2, share=True)
            q = x.ts_battery_attempts()[0]
            if q.state == 'consent':
                q.give_consent()
            if q.state == 'in_progress':
                for it in q.active_items():
                    q.save_answer(it.id, 3 if it.factor_id.code != 'ATTN' else 1)
                q.action_submit()
            return x
        if hp:
            step('hire_pending', hire_pending)
            if c2:
                step('hire_task', hire_task)
            P = HW + '/positions/%s' % hp.id
            m[HL('hr')] = [HW + '/positions', HW + '/positions/new?q=حسابدار', P, P + '/profile', P + '/fairness'] + \
                ([P + '/c/%s' % ha.id] if ha else []) + ([P + '/c/%s' % R['hire_pending'].id] if R.get('hire_pending') else [])
            if ha and ha.user_id:
                m[HL('cand')] = ['/my/assessments/battery/%s' % ha.id]
            if R.get('hire_task') and c2:
                t = R['hire_task'].ts_battery_attempts()[1:2]
                m[HL('cand2')] = ['/invite/%s' % R['hire_pending'].token] + (['/take/%s' % t.access_token] if t else [])
    # ---------------------------------------------------------------- counseling-center set-up guide (clinic phase 6, 2026-10-12)
    # A dedicated prepaid counseling-center panel «مرکز مشاورهٔ نمونهٔ آرامش» (fictional): owner, counselor c1 with a title, a
    # photo and a verified licence, counselor c2 verified without a title (first-run card), participant p1 with a finished
    # attempt (responsible c1) taken while the panel was still free, a PNG logo. Every run puts the checklist back in the same
    # partly-done state «۳ از ۶ انجام شده»: identity, counselors and first invitation done; each counselor's catalog, the caps
    # (optional) and the credit (balance 0) open. Upserts only.
    import base64 as _b64, io as _io


    def ux_png(kind):
        from PIL import Image, ImageDraw
        im = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if kind == 'logo':
            try:
                d.rounded_rectangle((16, 16, 240, 240), radius=48, fill=(42, 111, 151, 255))
            except AttributeError:
                d.rectangle((16, 16, 240, 240), fill=(42, 111, 151, 255))
            d.ellipse((76, 76, 180, 180), outline=(253, 253, 255, 255), width=14)
        else:
            d.ellipse((0, 0, 255, 255), fill=(201, 205, 221, 255))
            d.ellipse((88, 44, 168, 124), fill=(117, 121, 140, 255))
            d.pieslice((40, 140, 216, 316), 180, 360, fill=(117, 121, 140, 255))
        buf = _io.BytesIO()
        im.save(buf, 'PNG')
        return _b64.b64encode(buf.getvalue()).decode()


    CK = lambda k: L('center.%s' % k)
    CNAME = 'مرکز مشاورهٔ نمونهٔ آرامش'


    def center_panel():
        org = env['res.partner'].search([('name', '=', CNAME), ('is_company', '=', True)], limit=1) or env['res.partner'].create(
            {'name': CNAME, 'is_company': True})
        ws = env['ts.workspace'].search([('partner_id', '=', org.id)], limit=1) or env['ts.workspace'].create(
            {'name': CNAME, 'purpose': 'clinical', 'partner_id': org.id, 'escalation_contact_id': org.id})
        if not ws.approved_on:
            ws.write({'approved_on': '2026-01-01 00:00:00'})
        if ws.state != 'pilot':
            ws.state = 'pilot'
        ws.write({'public_name': 'مرکز مشاورهٔ آرامش', 'contact_line': '۰۲۱-۸۸۰۰۰۰۰۰ · aramesh.example', 'brand_color': '#2a6f97',
                  'ts_onb_nocap_on': False})
        if not org.image_1920:
            org.image_1920 = ux_png('logo')
        return ws


    def center_member(ws, k, name, role, **vals):
        u = user('center.%s' % k, name)
        mm = M.with_context(active_test=False).search([('workspace_id', '=', ws.id), ('user_id', '=', u.id)], limit=1) or M.create(
            {'workspace_id': ws.id, 'user_id': u.id, 'role': role})
        base = {'active': True, 'ts_onb_hidden_on': False, 'ts_onb_card_hidden_on': False, 'ts_catalog_seen_on': False}
        if role == 'clinician':
            base['monthly_cap'] = 0
        mm.write(dict(base, **vals))
        if mm.catalog_restricted or mm.restrict_instrument_ids or mm.restrict_battery_ids:
            mm.write({'catalog_restricted': False, 'restrict_instrument_ids': [(5, 0, 0)], 'restrict_battery_ids': [(5, 0, 0)]})
        return mm


    def center_seed():
        ws = center_panel()
        mo = center_member(ws, 'owner', 'فرزانه آزمایشی', 'owner')
        c1 = center_member(ws, 'c1', 'سارا آزمایشی', 'clinician', title='روان‌شناس و مشاور',
                           report_bio='مشاور نوجوان و خانواده', license_number='LIC-UX-1001', verification_state='verified')
        c2 = center_member(ws, 'c2', 'کاوه آزمایشی', 'clinician', title=False, license_number='LIC-UX-1002',
                           verification_state='verified')
        if not c1.user_id.partner_id.image_1920:
            c1.user_id.partner_id.image_1920 = ux_png('photo')
        p1 = user('center.p1', 'مراجع آزمایشی آرامش')
        a = A.search([('workspace_id', '=', ws.id), ('user_id', '=', p1.id), ('state', '=', 'done')], order='id desc', limit=1)
        if not a:
            if ws.billing_mode != 'free':
                ws.billing_mode = 'free'          # the sample invitation is taken while the panel is free (no credit needed)
            cinst = c1.allowed_instruments().filtered(lambda i: i.audience == 'adult' and i.code != 'TALENT-INV-15') \
                .sorted(lambda i: (i.active_item_count, i.id))[:1]
            a = A.create({'workspace_id': ws.id, 'instrument_id': cinst.id, 'invitee_name': p1.name, 'invited_by_id': c1.user_id.id,
                          'responsible_id': c1.id})
            at = a.action_accept(p1, True)
            if at.state == 'consent':
                at.give_consent(research=False, role='self')
            for it in at.active_items():
                at.save_answer(it.id, 1 + it.id % 5)
            at.action_submit()
        if a.responsible_id != c1:
            a.responsible_id = c1
        if ws.billing_mode != 'prepaid':
            ws.billing_mode = 'prepaid'           # steps 4 and 5 appear; the balance stays 0 (step 5 open)
        return {'ws': ws, 'mo': mo, 'c1': c1, 'c2': c2, 'a': a}
    step('center', center_seed)
    if 'center' in R:
        cs = R['center']
        CW = '/my/workspaces/%s' % cs['ws'].id
        cat, ccl = cs['a'].attempt_id, cs['a'].client_id
        m[CK('owner')] = [CW, CW + '/settings', CW + '/members/%s' % cs['c1'].id, CW + '/credits', '/help/panel#center-setup']
        m[CK('c1')] = [CW + '/members/%s' % cs['c1'].id] + ([CW + '/clients/%s/r/%s' % (ccl.id, cat.id)] if ccl and cat else [])
        m[CK('c2')] = [CW, CW + '/members/%s' % cs['c2'].id]
        if cat:
            # the branded report and its print mode (the PDF route's fallback; ts_shot.py also writes a _print.png, G8-P10-7)
            m[CK('p1')] = ['/my/assessments/%s' % cat.id, '/my/assessments/%s?print=1' % cat.id]
        pub.append('/help/panel#center-setup')
    json.dump(m, open('/tmp/ux_matrix.json', 'w'))
    print('UXMATRIX', ' '.join('%s=%d' % ((k or 'public').split('@')[0], len(v)) for k, v in m.items()), 'total', sum(len(v) for v in m.values()))
