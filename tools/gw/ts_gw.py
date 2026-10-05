#!/usr/bin/env python3
"""ts-gw - forced command for the eot.innerquest.me gateway's key on the tools VPS (no Mac in the path).

Installed as /usr/local/bin/ts-gw. root's authorized_keys on the tools VPS carries the gateway key as
    command="/usr/local/bin/ts-gw",restrict,from="95.38.235.225" ssh-ed25519 ...
so that key can run nothing but this file. The request is one JSON object on stdin, the reply one JSON object on
stdout: {"ok": bool, "text": str} or {"ok": true, "image": base64, "mime": "image/png", "text": caption}.

Ops (each finishes in < 55 s; long work goes through `ts`/`eot` background jobs):
  ts       {"args": [...], "slot": 0|1|2}   allow-listed `ts` subcommands (no `bg`, `domain`, `guard`)
  eot      {"args": [...]}                  allow-listed `eot` subcommands (no `ssh`, `bg`, `update`, `mcp-update`)
  read     {"path", "start", "end"}         numbered slice of a text file, or a directory listing, under ROOTS
  write    {"path", "content"}              create/replace a file under WRITE_ROOTS
  patch    {"root", "diff"}                 `git apply --check` then `git apply` in a repo root; returns git status
  git      {"root", "args"}                 allow-listed git subcommands in a repo root (push: origin + branch, no force)
  image    {"path"}                         a png/jpg/webp under IMAGE_ROOTS (<= 3 MB) as base64
  inspect  {"argv": [...]}                  read-only diagnostics (ls, grep, tail, df, ss, ps, systemctl status, ...)
Arguments never pass through a shell. Only the op name and the outcome are logged (/var/log/ts-gw.log).
"""
import base64, json, os, re, subprocess, sys, time

REPOS = ['/root/talentsearch_odoo', '/root/ts_wt_s1', '/root/ts_wt_s2', '/root/eot-tools/repo']
ROOTS = REPOS + ['/root/ts-jobs', '/root/eot-jobs', '/root/share']
WRITE_ROOTS = REPOS + ['/root/share/in']
IMAGE_ROOTS = ['/root/share/out', '/root/ts-jobs', '/root/eot-jobs']
TS_OK = {'help', 'check', 'sync', 'slots', 'live', 'status', 'wait', 'job', 'test', 'db', 'dump', 'rehearse', 'keep',
         'shots', 'sql', 'get', 'wt', 'clean', 'push', 'ship'}
TS_DB_OK = {'clone', 'apply', 'install', 'upgrade', 'serve', 'halt', 'reload', 'stop', 'errors', 'modules'}
EOT_OK = {'help', 'check', 'placeholders', 'links', 'verify', 'text', 'find', 'view', 'sql', 'deploy', 'rehearse-stop',
          'log', 'status', 'job', 'jobs', 'wait', 'backup', 'rehearse', 'rehearse-log', 'clone-user', 'ship', 'render',
          'routes', 'audit'}
GIT_OK = {'status', 'diff', 'log', 'show', 'add', 'commit', 'restore', 'rev-parse', 'branch', 'fetch', 'pull', 'push',
          'switch', 'checkout', 'stash', 'reset', 'ls-files', 'blame', 'grep'}
INSPECT_OK = {'ls', 'grep', 'head', 'tail', 'wc', 'df', 'du', 'free', 'uptime', 'ps', 'ss', 'find', 'stat', 'md5sum',
              'date', 'systemctl', 'journalctl', 'cat', 'file', 'nginx', 'dig', 'getent', 'curl'}
FILE_CMDS = {'ls', 'grep', 'head', 'tail', 'wc', 'du', 'find', 'stat', 'md5sum', 'cat', 'file'}
INSPECT_ROOTS = ROOTS + ['/etc/nginx', '/etc/systemd/system', '/var/log', '/usr/local/bin', '/tmp']
MAX_OUT = 24000
LOG = '/var/log/ts-gw.log'


def out(ok, text='', **extra):
    if len(text) > MAX_OUT:
        text = '[... %d chars cut, showing the end]\n' % (len(text) - MAX_OUT) + text[-MAX_OUT:]
    sys.stdout.write(json.dumps(dict(ok=ok, text=text, **extra)))
    return ok


def under(path, roots):
    real = os.path.realpath(path)
    return real if any(real == r or real.startswith(r + '/') for r in roots) else None


def run(argv, timeout=55, env=None, cwd=None, stdin=None):
    try:
        p = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           env=dict(os.environ, **(env or {})))
        return p.returncode == 0, (p.stdout + (('\n' + p.stderr) if p.stderr.strip() else '')).strip() or '(no output)'
    except subprocess.TimeoutExpired:
        return False, '!! timed out after %s s - run it as a background job (ts rehearse/keep/shots, eot bg is not exposed)' % timeout


def strs(xs):
    if not isinstance(xs, list) or not all(isinstance(x, str) for x in xs):
        raise ValueError('args must be a list of strings')
    if any('\n' in x or '\0' in x for x in xs):
        raise ValueError('newlines are not allowed in arguments')
    return xs


def op_ts(req):
    args = strs(req.get('args') or ['help'])
    slot = str(req.get('slot', 0))
    if slot not in ('0', '1', '2'):
        return out(False, 'slot must be 0, 1 or 2')
    sub = args[0]
    if sub not in TS_OK:
        return out(False, 'ts %s is not exposed through the gateway (allowed: %s)' % (sub, ', '.join(sorted(TS_OK))))
    if sub == 'db':
        if len(args) < 3 or args[1] not in TS_DB_OK or not args[2].startswith('eot_ts'):
            return out(False, 'ts db SUB DB: SUB in %s, DB must start with eot_ts' % sorted(TS_DB_OK))
    if sub in ('wait',) and len(args) > 2:
        args[2] = str(min(int(args[2]), 40))
    if sub in ('wait',) and len(args) == 2:
        args.append('40')
    if sub == 'clean' and '--yes' in args and not req.get('confirm'):
        return out(False, 'ts clean --yes deletes clones and old code dirs: pass confirm=true')
    if sub == 'ship' and not req.get('confirm'):
        return out(False, 'ts ship changes the live site: pass confirm=true (after a green rehearsal of the same commit)')
    ok, text = run(['/usr/local/bin/ts'] + args, env={'TS_SLOT': slot, 'HOME': '/root'}, cwd='/root')
    return out(ok, text)


def op_eot(req):
    args = strs(req.get('args') or ['help'])
    if args[0] not in EOT_OK:
        return out(False, 'eot %s is not exposed through the gateway (allowed: %s)' % (args[0], ', '.join(sorted(EOT_OK))))
    if args[0] in ('deploy', 'ship') and not req.get('confirm'):
        return out(False, 'eot %s changes the live eot.ir: pass confirm=true' % args[0])
    ok, text = run(['/usr/local/bin/eot'] + args, env={'HOME': '/root'}, cwd='/root')
    return out(ok, text)


def op_read(req):
    path = under(req.get('path', ''), ROOTS)
    if not path:
        return out(False, 'path outside the readable roots: %s' % ROOTS)
    if os.path.isdir(path):
        rows = []
        for n in sorted(os.listdir(path))[:500]:
            q = os.path.join(path, n)
            rows.append('%s%s\t%s' % (n, '/' if os.path.isdir(q) else '', '' if os.path.isdir(q) else os.path.getsize(q)))
        return out(True, '\n'.join(rows) or '(empty)')
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
    except OSError as e:
        return out(False, str(e))
    start = max(1, int(req.get('start') or 1))
    end = min(len(lines), int(req.get('end') or start + 399), start + 399)
    body = '\n'.join('%d\t%s' % (i, lines[i - 1]) for i in range(start, end + 1))
    return out(True, '%s (%d lines total)\n%s' % (path, len(lines), body))


def op_write(req):
    path = req.get('path', '')
    parent = under(os.path.dirname(path) or '/', WRITE_ROOTS)
    if not parent or os.path.islink(path):
        return out(False, 'path outside the writable roots: %s' % WRITE_ROOTS)
    content = req.get('content')
    if not isinstance(content, str):
        return out(False, 'content must be a string')
    os.makedirs(parent, exist_ok=True)
    full = os.path.join(parent, os.path.basename(path))
    with open(full + '.gwtmp', 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(full + '.gwtmp', full)
    return out(True, 'wrote %s (%d bytes)' % (full, len(content.encode())))


def repo_root(req):
    root = req.get('root', '/root/talentsearch_odoo')
    return root if root in REPOS and os.path.isdir(root) else None


def op_patch(req):
    root = repo_root(req)
    if not root:
        return out(False, 'root must be one of %s' % REPOS)
    diff = req.get('diff') or ''
    ok, text = run(['git', 'apply', '--check', '--whitespace=nowarn', '-'], cwd=root, stdin=diff)
    if not ok:
        return out(False, 'patch does not apply:\n' + text)
    ok, text = run(['git', 'apply', '--whitespace=nowarn', '-'], cwd=root, stdin=diff)
    _, st = run(['git', 'status', '--short'], cwd=root)
    return out(ok, (text if not ok else 'applied') + '\n' + st)


def op_git(req):
    root = repo_root(req)
    if not root:
        return out(False, 'root must be one of %s' % REPOS)
    args = strs(req.get('args') or ['status', '--short'])
    if args[0] not in GIT_OK:
        return out(False, 'git %s is not exposed (allowed: %s)' % (args[0], ', '.join(sorted(GIT_OK))))
    bad = [a for a in args if a.startswith(('-c', '--exec', '--upload-pack', '--receive-pack', '--config', '--git-dir',
                                            '--work-tree')) or a in ('--force', '-f', '--force-with-lease', '--mirror',
                                                                     '--delete', '-D', '--hard')]
    if args[0] == 'push' and (bad or len(args) != 3 or args[1] != 'origin' or args[2].startswith(('+', ':'))):
        return out(False, 'push only as: push origin BRANCH (no force, no delete)')
    if bad and not req.get('confirm'):
        return out(False, 'flags %s need confirm=true' % bad)
    ok, text = run(['git', '-c', 'core.pager=cat'] + args, cwd=root, env={'GIT_TERMINAL_PROMPT': '0'})
    return out(ok, text)


def op_image(req):
    path = under(req.get('path', ''), IMAGE_ROOTS)
    if not path or not re.search(r'\.(png|jpe?g|webp)$', path, re.I) or not os.path.isfile(path):
        return out(False, 'image must be a png/jpg/webp file under %s' % IMAGE_ROOTS)
    if os.path.getsize(path) > 3 * 1024 * 1024:
        return out(False, 'image larger than 3 MB')
    mime = 'image/png' if path.lower().endswith('.png') else ('image/webp' if path.lower().endswith('.webp') else 'image/jpeg')
    data = base64.b64encode(open(path, 'rb').read()).decode()
    sys.stdout.write(json.dumps({'ok': True, 'text': path, 'image': data, 'mime': mime}))
    return True


def op_inspect(req):
    argv = strs(req.get('argv') or [])
    if not argv or argv[0] not in INSPECT_OK:
        return out(False, 'inspect commands: %s' % ', '.join(sorted(INSPECT_OK)))
    a = argv[0]
    if a == 'find' and any(x in ('-exec', '-execdir', '-delete', '-ok', '-fprint', '-fls') for x in argv):
        return out(False, 'find: read-only flags only')
    if a == 'systemctl' and (len(argv) < 2 or argv[1] not in ('status', 'is-active', 'list-units', 'show', 'cat')):
        return out(False, 'systemctl: status | is-active | list-units | show | cat')
    if a == 'nginx' and argv[1:] != ['-t']:
        return out(False, 'nginx: -t only')
    if a == 'curl' and any(x.startswith(('-o', '--output', '-T', '--upload', '-d', '--data', '-F', '-X', '--config', '-K')) for x in argv):
        return out(False, 'curl: GET/HEAD only, no output files')
    if a == 'grep' and any(x.startswith(('-f', '--file', '--exclude-from')) for x in argv):
        return out(False, 'grep: no pattern files')
    if a in FILE_CMDS:
        operands = [x for x in argv[1:] if not x.startswith('-')]
        if a == 'grep' and operands:
            operands = operands[1:]          # the pattern
        if a == 'find':
            operands = operands[:1]          # the start dir; tests follow
        for x in operands:
            if not under(os.path.join('/root/ts-jobs', x), INSPECT_ROOTS):
                return out(False, '%s: paths must be under %s' % (a, INSPECT_ROOTS))
    ok, text = run(['/usr/bin/env', '--'] + argv, timeout=40, cwd='/root/ts-jobs')
    return out(ok, text)


OPS = {'ts': op_ts, 'eot': op_eot, 'read': op_read, 'write': op_write, 'patch': op_patch, 'git': op_git,
       'image': op_image, 'inspect': op_inspect}


def main():
    t = time.time()
    try:
        req = json.loads(sys.stdin.read() or '{}')
        op = req.get('op')
        ok = OPS[op](req) if op in OPS else out(False, 'unknown op %r (ops: %s)' % (op, ', '.join(sorted(OPS))))
    except Exception as e:  # never echo the request
        op, ok = 'error', out(False, '%s: %s' % (type(e).__name__, e))
    try:
        with open(LOG, 'a') as f:
            f.write('%s op=%s ok=%s %.1fs\n' % (time.strftime('%F %T'), op, ok, time.time() - t))
    except OSError:
        pass


if __name__ == '__main__':
    main()
