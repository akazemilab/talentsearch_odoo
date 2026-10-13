#!/usr/bin/env python3
"""Set clone-only passwords for every login in the UX matrix (ts_ux_seed.py output):  ts_ux_users.py DB PORT /tmp/ux_matrix.json
Same password files and upsert as ts_flowlib.ensure_user, but in ONE odoo shell for all logins (the participant matrix of
`ts shots DB take` has ~30 logins; one shell per login took minutes). Falls back to ensure_user per login if the batch fails.
The shell output is never printed (it could echo the code, which carries the passwords)."""
import importlib.util, json, os, sys
DB, PORT, F = sys.argv[1], sys.argv[2], sys.argv[3]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
logins = [k for k in json.load(open(F)) if k]
pws = {}
for login in logins:
    pw_file = '/root/.ts_flow_%s_%s' % (DB, login.split('@')[0])
    if not os.path.exists(pw_file):
        old = os.umask(0o077); open(pw_file, 'w').write(os.urandom(12).hex()); os.umask(old)
    pws[login] = open(pw_file).read().strip()
out = lib.shell(("U = env['res.users'].with_context(no_reset_password=True)\n"
                 "portal = env.ref('base.group_portal')\n"
                 "for login, pw in %r.items():\n"
                 "    u = U.search([('login', '=', login)]) or U.create({'name': 'آزمون جریان', 'login': login, 'group_ids': [(6, 0, [portal.id])]})\n"
                 "    u.password = pw\n"
                 "env.cr.commit()\n"
                 "print('UXPW-OK', %d)\n") % (pws, len(pws))) if pws else 'UXPW-OK 0'
if ('UXPW-OK %d' % len(pws)) not in out:
    for login in logins:
        lib.ensure_user(login)
print('UXUSERS', len(logins))
