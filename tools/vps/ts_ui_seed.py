import json
L = {'owner': 'ts.pv2s19.owner.http@example.invalid', 'cns': 'ts.pv2s19.cns.http@example.invalid'}
U = {k: env['res.users'].search([('login', '=', v)]) for k, v in L.items()}
ws = env['ts.workspace'].search([('name', '=', 'S19 http')], limit=1)
W = '/my/workspaces/%s' % ws.id
I = env['ts.instrument'].sudo().search([('state', '=', 'published')])
tal = I.filtered(lambda i: i.code == 'TALENT-INV-15')[:1] or I[:1]
oth = (I - tal)[:1] or tal
A = env['ts.attempt'].sudo()
def attempt(user, inst, consent):
    a = A.search([('user_id', '=', user.id), ('instrument_id', '=', inst.id), ('state', 'in', ('consent', 'in_progress'))], limit=1)
    if not a:
        a = A.create({'user_id': user.id, 'instrument_id': inst.id, 'version_id': inst.current_version_id.id})
    if consent and a.state == 'consent':
        try:
            a.give_consent()
        except Exception as e:
            print('consent skipped', type(e).__name__)
    return a
a1 = attempt(U['owner'], tal, False)
a2 = attempt(U['owner'], oth, True)
done = A.search([('user_id', '=', U['owner'].id), ('state', '=', 'done')], limit=1)
env.cr.commit()
pub = ['/', '/schools', '/assessments', '/assessments?all=1', '/assessments/%s' % tal.slug, '/panel', '/pricing', '/contact',
       '/privacy', '/contact/thanks', '/help/panel', '/web/login', '/signup',
       'POSTSHOT /signup/send phone=09127770375&next=/my',     # the code step (pending code seeded by ts_ui_matrix.sh)
       '/nist-404']
own = [W, W + '/clients', W + '/clients/new', W + '/invites', W + '/invites/new', W + '/campaigns', W + '/groups', W + '/members',
       W + '/reports', W + '/reports/group', W + '/credits', W + '/notifications', W + '/audit', W + '/settings', W + '/exports',
       W + '/import', '/my/workspaces', '/my', '/my/account', '/my/sharing', '/my/privacy', '/my/sessions', '/my/assessments',
       '/take/%s' % a1.access_token, '/take/%s' % a2.access_token, '/help/roles']
if done:
    own.append('/my/assessments/%s' % done.id)
cns = [W, W + '/clients', W + '/reports', '/my']
# onb2: the welcome screens, the minors' screen, /start, the guest player, the result gate, the masked-number code screen,
# and the claimed report (its own login, the owner's password: ONB2_PW_FROM)
ONB2 = []
ONB2_USERS = {}
ONB2_PW_FROM = L['owner']
import os as _os
if _os.path.exists('/tmp/ts_onb2_seed.py'):
    exec(open('/tmp/ts_onb2_seed.py').read())
pub += ONB2
# onb3: six self-service panels of the matrix owner in their first-session states, the audience pages, the public samples
ONB3_PUB, ONB3_OWN = [], []
if _os.path.exists('/tmp/ts_onb3_seed.py'):
    exec(open('/tmp/ts_onb3_seed.py').read())
pub += ONB3_PUB
own += ONB3_OWN
json.dump(dict({'': pub, L['owner']: own, L['cns']: cns}, **ONB2_USERS), open('/tmp/ui_matrix.json', 'w'))
print('MATRIX', len(pub), len(own), len(cns), W)
