# onb2 screens for the shots matrices (exec'd by ts_ui_seed.py and ts_ux_seed.py inside `odoo shell` on a CLONE, after
# ts_ui_matrix.sh switched SMS on with a dead endpoint and seeded a pending code for 09127770375). Fictional data only;
# upserts. Defines ONB2 = public matrix entries: the welcome screen (counseling center, employment), the minors' one
# screen, /start, «کمتر از ۱۸ سال», the guest player, the result gate (a browser cookie set with «COOKIE name value»)
# and, last, the masked-number code screen of an invitation opened on another browser.
from odoo import fields

ONB2 = []
assert env.cr.dbname.startswith('eot_ts'), 'clones only'
try:
    from odoo.addons.ts_onboard.models.common import digest, new_token
    from odoo.addons.ts_sms.controllers.signup import create_phone_user
    A, Att = env['ts.assignment'].sudo(), env['ts.attempt'].sudo()
    PHONE = '09127770375'                      # the number ts_ui_matrix.sh gave a pending code (cooldown never ends)

    def _panel(name, purpose):
        p = env['res.partner'].search([('name', '=', name), ('is_company', '=', True)], limit=1) or env['res.partner'].create(
            {'name': name, 'is_company': True})
        w = env['ts.workspace'].search([('partner_id', '=', p.id)], limit=1) or env['ts.workspace'].create(
            {'name': name, 'purpose': purpose, 'partner_id': p.id, **({'escalation_contact_id': p.id} if purpose == 'clinical' else {})})
        if w.state != 'active':
            w.state = 'active'
        return w

    def _open(ws, name, **vals):
        a = A.search([('workspace_id', '=', ws.id), ('invitee_name', '=', name), ('user_id', '=', False),
                      ('declined', '=', False), ('withdrawn', '=', False)], limit=1)
        return a if a and a.invite_state() == 'ok' else A.create(dict({'workspace_id': ws.id, 'invitee_name': name}, **vals))

    wcl = _panel('مرکز مشاورهٔ نمونهٔ مهر', 'clinical')
    inst = env['ts.instrument'].search([('state', '=', 'published'), ('audience', '=', 'adult'), ('purpose', '!=', 'employment'),
                                        ('code', 'not in', ('TALENT-INV-15', 'inventory_002'))], order='id', limit=1)
    clinic = _open(wcl, 'مریم نمونه', instrument_id=inst.id)
    clinic._ts_mark_delivered('sms', phone='09127770376')
    C = env['ts.panel.client'].sudo()
    kid = C.search([('workspace_id', '=', wcl.id), ('name', '=', 'آرش نمونه')], limit=1) or C.create(
        {'workspace_id': wcl.id, 'name': 'آرش نمونه', 'age_group': 'minor'})
    minor = _open(wcl, 'آرش نمونه', instrument_id=inst.id, client_id=kid.id)
    # employment: a company, an open position, a candidate invitation (the battery has a timed part)
    org = _panel('شرکت نمونهٔ آینده', 'employment')
    U = env['res.users'].with_context(no_reset_password=True)
    hr = U.search([('login', '=', 'ts.onb2.shot.hr@example.invalid')], limit=1) or U.create(
        {'name': 'مدیر منابع انسانی نمونه', 'login': 'ts.onb2.shot.hr@example.invalid',
         'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
    M = env['ts.workspace.member'].sudo().with_context(active_test=False)
    hrm = M.search([('workspace_id', '=', org.id), ('user_id', '=', hr.id)], limit=1) or M.create(
        {'workspace_id': org.id, 'user_id': hr.id, 'role': 'hr_admin'})
    hrm.write({'active': True})
    P = env['ts.hire.position'].sudo()
    pos = P.search([('workspace_id', '=', org.id), ('name', '=', 'کارشناس فروش'), ('state', '=', 'open')], limit=1)
    if not pos:
        pos = P.create({'name': 'کارشناس فروش', 'workspace_id': org.id, 'occupation_id': env['ts.onet.occupation'].search([], limit=1).id,
                        'battery_choice': 'short', 'created_by_id': hr.id})
        pos.state = 'open'
    emp = A.search([('position_id', '=', pos.id), ('invitee_name', '=', 'نگار نمونه'), ('user_id', '=', False)], limit=1) or \
        A.with_user(hr).sudo().create({'workspace_id': org.id, 'battery_id': pos.battery_id.id, 'position_id': pos.id,
                                       'instrument_id': pos.battery_id.ts_first_instrument().id, 'invitee_name': 'نگار نمونه',
                                       'invited_by_id': hr.id, 'note': 'ارزیابی برای موقعیت «%s»' % pos.name})
    # an invitation accepted on another browser: opening it here asks for a code to the invited number (masked)
    owner = env['res.users'].ts_phone_owner(PHONE).filtered('active')[:1] or create_phone_user(env, PHONE)
    bound = A.search([('workspace_id', '=', wcl.id), ('invitee_name', '=', 'سارا نمونه'), ('user_id', '=', owner.id)], limit=1)
    if not bound:
        bound = A.create({'workspace_id': wcl.id, 'invitee_name': 'سارا نمونه', 'instrument_id': inst.id})
        bound.action_accept(owner, share=True)
    bound._ts_mark_delivered('sms', phone=PHONE)
    bound.sudo().write({'device_hash': '0' * 64})
    # guest attempts: one finished (the result gate), one in progress (the guest player)
    starter = env['ts.instrument'].sudo().ts_starter()
    pub_user = env.ref('base.public_user')

    def _guest(done):
        raw, cookie = new_token(env, 'guest')
        at = Att.create({'user_id': pub_user.id, 'instrument_id': starter.id, 'version_id': starter.current_version_id.id,
                         'ts_guest': True, 'ts_guest_hash': digest(raw), 'ts_guest_seen': fields.Datetime.now()})
        at.ts_guest_consent()
        items = at.active_items()
        for it in (items if done else items[:5]):
            at.save_answer(it.id, 1 + it.id % 5)
        if done:
            at.action_submit()
        return cookie, at

    (gate_cookie, _g1), (play_cookie, _g2) = _guest(True), _guest(False)
    # the claimed report: a signed-in account whose name is still unknown (the optional name field shows). Its password
    # is the one of the matrix login ONB2_PW_FROM (ts_ui_seed.py sets it; clones only), so ts_shot.py can sign in.
    ONB2_USERS = {}
    src = globals().get('ONB2_PW_FROM')
    if src:
        CL = 'ts.onb2.shot.claim@example.invalid'
        cu = U.search([('login', '=', CL)], limit=1) or U.with_context(ts_name_placeholder=True).create(
            {'name': CL, 'login': CL, 'email': CL, 'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
        cu.partner_id.sudo().with_context(ts_name_placeholder=True).write({'name': CL, 'ts_name_unknown': True})
        env.flush_all()
        env.cr.execute('UPDATE res_users SET password = (SELECT password FROM res_users WHERE login = %s) WHERE id = %s',
                       [src, cu.id])
        env.invalidate_all()
        claimed = Att.search([('user_id', '=', cu.id), ('ts_guest_claimed_at', '!=', False), ('state', '=', 'done')], limit=1)
        if not claimed:
            _c, claimed = _guest(True)
            claimed.ts_guest_claim(cu)
        ONB2_USERS = {CL: ['/my/assessments/%s?claimed=1' % claimed.id]}
    env.cr.commit()
    ONB2 = ['/invite/%s' % clinic.token, '/invite/%s' % emp.token, '/invite/%s' % minor.token,
            '/start', '/start/under-18',
            'COOKIE ts_guest %s' % play_cookie, '/start/q',
            'COOKIE ts_guest %s' % gate_cookie, '/start/result',
            'POSTSHOT /invite/%s/accept welcome=1' % bound.token]
    print('ONB2SEED', len(ONB2), 'claimed report' if ONB2_USERS else 'no claimed report')
except Exception as e:      # noqa: BLE001 - the rest of the matrix still runs
    env.cr.rollback()
    print('SEED-SKIP onb2', type(e).__name__, str(e)[:160])
    ONB2 = []
    ONB2_USERS = {}
