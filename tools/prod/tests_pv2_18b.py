# Panel v2 S18b (password length on the TS site only). Run ONLY on an eot_ts* clone via odoo-bin shell.
from odoo.exceptions import ValidationError

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
import odoo.addons.ts_panel.models.security as S
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


def raises(fn):
    try:
        with env.cr.savepoint():
            fn()
    except ValidationError:
        return True
    return False


U = env['res.users'].with_context(no_reset_password=True)
u = U.create({'name': 'p18b', 'login': 'ts.pv2s18b.p@example.invalid', 'email': 'ts.pv2s18b.p@example.invalid'})
orig = S.on_ts_site
try:
    S.on_ts_site = lambda: False
    check('off the TS site a short password is accepted', not raises(lambda: u.write({'password': 'short'})))
    S.on_ts_site = lambda: True
    check('on the TS site a 14-character password is refused', raises(lambda: u.write({'password': 'a' * 14})))
    check('on the TS site a 15-character password is accepted', not raises(lambda: u.write({'password': 'a' * 15 + 'Zq9'})))
    S.on_ts_site = orig
    check('with no request the check is a no-op (shell)', orig() is False)
finally:
    S.on_ts_site = orig
env.cr.rollback()
bad = [n for n, ok in results if not ok]
print('SUMMARY %d/%d' % (len(results) - len(bad), len(results)))
