"""Gateway-local ops for `ts` (loaded by ts_gw.py from the committed repo; not part of /usr/local/bin/ts).

  gw-install     install tools/gw/ts_gw.py (committed main) as /usr/local/bin/ts-gw      needs confirm=true
  infra-key      create the deploy key for akazemilab/infra once, print the PUBLIC key only
  infra-clone    clone (or fast-forward) /root/infra
  infra-refresh  copy un-versioned server files into /root/infra (secret-free, scanned); no commit, no push

Every function returns (ok, text) and never prints secret values.
"""
import os, subprocess, sys

REPO = '/root/talentsearch_odoo'
SRC = REPO + '/tools/gw/ts_gw.py'
DST = '/usr/local/bin/ts-gw'
INFRA = '/root/infra'
KEY = '/root/.ssh/infra_deploy'


def run(argv, timeout=50, env=None, cwd=None):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           env=dict(os.environ, HOME='/root', GIT_TERMINAL_PROMPT='0', **(env or {})))
        return p.returncode == 0, (p.stdout + (('\n' + p.stderr) if p.stderr.strip() else '')).strip() or '(no output)'
    except subprocess.TimeoutExpired:
        return False, '!! timed out after %s s' % timeout


def gw_install(args, req):
    if not req.get('confirm'):
        return False, 'gw-install replaces the gateway script itself: pass confirm=true'
    ok, br = run(['git', '-C', REPO, 'rev-parse', '--abbrev-ref', 'HEAD'])
    if not ok or br.strip() != 'main':
        return False, 'talentsearch_odoo must be on main (is: %s)' % br
    ok, dirty = run(['git', '-C', REPO, 'status', '--porcelain', '--', 'tools/gw'])
    if dirty.strip() not in ('', '(no output)'):
        return False, 'tools/gw has uncommitted changes: commit them first'
    ok, t = run([sys.executable, '-c', 'import ast,sys; ast.parse(open(sys.argv[1]).read())', SRC])
    if not ok:
        return False, 'syntax check failed:\n' + t
    run(['cp', '-p', DST, '/root/ts-gw.prev'])
    ok, t = run(['install', '-m', '755', SRC, DST + '.new'])
    if not ok:
        return False, t
    os.replace(DST + '.new', DST)
    ok, h = run(['md5sum', SRC, DST])
    return True, 'installed; previous copy kept as /root/ts-gw.prev\n' + h


def infra_key(args, req):
    os.makedirs('/root/.ssh', mode=0o700, exist_ok=True)
    if not os.path.exists(KEY):
        ok, t = run(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'infra-deploy@tools-vps', '-f', KEY])
        if not ok:
            return False, t
    cfg = '/root/.ssh/config'
    txt = open(cfg).read() if os.path.exists(cfg) else ''
    if 'Host github-infra' not in txt:
        with open(cfg, 'a') as f:
            f.write('\nHost github-infra\n  HostName github.com\n  User git\n  IdentityFile %s\n'
                    '  IdentitiesOnly yes\n  StrictHostKeyChecking accept-new\n' % KEY)
        os.chmod(cfg, 0o600)
    return True, ('PUBLIC key (add as a deploy key WITH write access on akazemilab/infra):\n' +
                  open(KEY + '.pub').read().strip())


def infra_clone(args, req):
    if os.path.isdir(INFRA + '/.git'):
        ok, t = run(['git', '-C', INFRA, 'pull', '--ff-only', 'origin', 'main'])
        return ok, 'already cloned\n' + t
    ok, t = run(['git', 'clone', 'git@github-infra:akazemilab/infra.git', INFRA])
    if ok:
        run(['git', '-C', INFRA, 'config', 'user.name', 'tools-vps'])
        run(['git', '-C', INFRA, 'config', 'user.email', 'noreply@anthropic.com'])
    return ok, t


def infra_refresh(args, req):
    script = INFRA + '/tools/infra_refresh.py'
    if not os.path.exists(script):
        return False, 'run ts infra-clone first (tools/infra_refresh.py must be on main)'
    return run([sys.executable, script], cwd=INFRA)


FN = {'gw-install': gw_install, 'infra-key': infra_key, 'infra-clone': infra_clone, 'infra-refresh': infra_refresh}


def dispatch(sub, args, req):
    return FN[sub](args, req)
