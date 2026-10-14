# onb3 screens for the shots matrix (exec'd by ts_ui_seed.py inside `odoo shell` on a CLONE, after ts_ui_matrix.sh switched
# SMS on with a dead endpoint). Fictional data only; upserts. The matrix owner (L['owner']) gets six self-service panels in
# the states the shots need: a new counseling center (start card, sample, one-screen invitation, the permanent-link form),
# one whose owner finished the try-out (the report with the coach line, the permanent link with its QR), one with its first
# real result opened (the second card, recent invitations with the stepper), a new school, a new hiring panel (the sample
# position) and a solo practitioner. Defines ONB3_PUB (public routes) and ONB3_OWN (the owner's routes).
ONB3_PUB, ONB3_OWN = [], []
assert env.cr.dbname.startswith('eot_ts'), 'clones only'
try:
    _W = env['ts.workspace'].sudo()
    _M = env['ts.workspace.member'].sudo().with_context(active_test=False)
    _A = env['ts.assignment'].sudo()
    _ou = env['res.users'].search([('login', '=', L['owner'])], limit=1)
    assert _ou, 'no matrix owner'
    if not _ou.partner_id.ts_known_name():
        _ou.sudo().write({'name': 'فرزانه نمونه'})

    def _mk(name, kind):
        w = _W.search([('name', '=', name), ('member_ids.user_id', '=', _ou.id)], limit=1)
        if not w:
            own = _M.search([('user_id', '=', _ou.id), ('role', '=', 'owner')])
            if own:          # the three-panels-a-day limit: earlier panels of this fixture owner count as older
                env.flush_all()
                env.cr.execute("UPDATE ts_workspace_member SET create_date = now() - interval '3 days' WHERE id IN %s",
                               [tuple(own.ids)])
                env.invalidate_all()
            w = _W.ts_panel_create(_ou, name, kind, terms=True)
        if w.state != 'active':
            w.state = 'active'
        m = w.member_ids.filtered(lambda x: x.user_id == _ou)[:1]
        m.write({'ts_start_hidden_on': False, 'ts_more_hidden_on': False, 'ts_guide_sms': True})
        return w, m

    def _finish(a):
        for _i in range(12):
            a.invalidate_recordset()
            left = a.ts_battery_attempts().filtered(lambda t: t.state != 'done')
            if not left:
                break
            t = left[0].sudo()
            if t.state == 'consent':
                t.give_consent(research=False, role='self')
            for it in t.active_items():
                t.save_answer(it.id, 1 + it.id % 4)
            t.action_submit()
        a.invalidate_recordset()
        return a

    wa, ma = _mk('مرکز مشاورهٔ نمونهٔ آغاز', 'clinic')
    wb, mb = _mk('مرکز مشاورهٔ نمونهٔ پیش‌نمایش', 'clinic')
    pvb = _finish(mb.ts_onb_try())
    if not wb.escalation_contact_id:
        wb.ts_set_escalation(mb)
    wb.ts_onb_permanent_link(mb)
    wc, mc = _mk('مرکز مشاورهٔ نمونهٔ کامل', 'clinic')
    _finish(mc.ts_onb_try())
    if not wc.escalation_contact_id:
        wc.ts_set_escalation(mc)
    inst = mc.allowed_instruments().filtered(lambda i: i.audience == 'adult' and i.code != 'TALENT-INV-15') \
        .sorted(lambda i: (i.active_item_count, i.id))[:1]
    p1 = env['res.users'].search([('login', '=', 'ts.onb3.shot.p1@example.invalid')], limit=1) or \
        env['res.users'].with_context(no_reset_password=True).create(
            {'name': 'مریم نمونه', 'login': 'ts.onb3.shot.p1@example.invalid', 'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
    done = _A.search([('workspace_id', '=', wc.id), ('user_id', '=', p1.id), ('state', '=', 'done')], limit=1)
    if not done:
        done = _A.with_user(_ou).sudo().create({'workspace_id': wc.id, 'instrument_id': inst.id, 'invitee_name': 'مریم نمونه',
                                               'invited_by_id': _ou.id})
        done.action_accept(p1, share=True)
        _finish(done)
    if not _A.search_count([('workspace_id', '=', wc.id), ('invitee_name', '=', 'کیان نمونه'), ('state', '=', 'invited')]):
        _A.with_user(_ou).sudo().create({'workspace_id': wc.id, 'instrument_id': inst.id, 'invitee_name': 'کیان نمونه',
                                        'invited_by_id': _ou.id})
    env['ts.audit.event'].sudo().log('result.view', done.attempt_id, workspace=wc, member=mc)
    wsch, msch = _mk('دبیرستان نمونهٔ آغاز', 'school')
    whr, mhr = _mk('شرکت نمونهٔ آغاز', 'org')
    wso, mso = _mk('مطب مشاورهٔ نمونه', 'solo')
    env.cr.commit()
    WA, WB, WC = ('/my/workspaces/%d' % w.id for w in (wa, wb, wc))
    WSC, WHR, WSO = ('/my/workspaces/%d' % w.id for w in (wsch, whr, wso))
    ONB3_OWN = ['/my/workspaces/new?kind=clinic', WA, WA + '/sample', WA + '/invites/new', WA + '/invites/new?mode=link',
                WA + '/members/%d' % ma.id, WB, mb.ts_onb_preview_url(pvb), WB + '/invites/new?mode=link', WC, WC + '/invites',
                WSC, WSC + '/sample', WSC + '/invites/new?mode=link', WHR, WHR + '/positions', WHR + '/sample', WSO,
                '/help/panel#getting-started']
    if wb.ts_perm_campaign_id.open_token:      # the join screen of a counseling panel's permanent link (the age question)
        ONB3_OWN.append('/c/%s' % wb.ts_perm_campaign_id.open_token)
    ONB3_PUB = ['/sample/clinic', '/sample/school', '/sample/hr']
    print('ONB3SEED', len(ONB3_OWN), len(ONB3_PUB))
except Exception as e:      # noqa: BLE001 - the rest of the matrix still runs
    env.cr.rollback()
    print('SEED-SKIP onb3', type(e).__name__, str(e)[:200])
    ONB3_PUB, ONB3_OWN = [], []
