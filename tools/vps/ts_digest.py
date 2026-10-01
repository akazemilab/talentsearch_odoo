#!/usr/bin/env python3
"""ts_digest.py LOG [SECS] - compact status of a ts job log, optionally waiting for news.

Prints one block: state (running/done rc), current phase (last '=== ' line), suite totals
(SUMMARY lines), every FAIL line once (known failures marked), guard/portal verdicts, '!!' lines.
With SECS (cap 50, the bridge limit is 60) it blocks until the job finishes or something
new and meaningful appears (FAIL, '!!', a verdict, the end), then prints the digest.
"""
import os, re, sys, time

KNOWN = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'known_failures.txt')
# `wait` returns early only for things that need attention or end a stage, not for every phase line
EVENT = re.compile(r'^(FAIL|!!|\[rc=|pages compared|portal: |REHEARSAL|SHIP |Traceback|.*verdict)')


def known():
    try:
        return [l.strip() for l in open(KNOWN, encoding='utf-8') if l.strip() and not l.startswith('#')]
    except OSError:
        return []


def read(path):
    try:
        return open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return None


def events(lines):
    return [l for l in lines if EVENT.match(l)]


def digest(path, lines):
    name = os.path.basename(path)[:-4]
    rc = [l for l in lines if l.startswith('[rc=')]
    state = 'done ' + rc[-1].strip('[]') if rc else 'running'
    phases = [l for l in lines if l.startswith('=== ')]
    sums = [l for l in lines if l.startswith('SUMMARY')]
    ok = tot = 0
    for s in sums:
        m = re.search(r'(\d+)/(\d+)', s)
        if m:
            ok += int(m.group(1)); tot += int(m.group(2))
    kn = known()
    fails, seen = [], set()
    for l in lines:
        if l.startswith('FAIL') or l.startswith('Traceback') or l.startswith('!!'):
            key = l[:90]
            if key in seen:
                continue
            seen.add(key)
            mark = ' (known)' if any(k in l for k in kn) else ''
            fails.append(l[:160] + mark)
    verdicts = [l[:120] for l in lines if 'verdict' in l or l.startswith('portal: ') or l.startswith('REHEARSAL')]
    out = [f'[{name}] {state} | phase: {phases[-1][4:][:90] if phases else "-"}',
           f'suites: {len(sums)} | checks {ok}/{tot}' + (f' | failing {tot - ok}' if tot - ok else '')]
    out += verdicts[-3:]
    unknown = [f for f in fails if not f.endswith('(known)')]
    out += fails[:12] if fails else []
    if fails and not unknown:
        out.append('only known failures')
    if not rc and lines:
        out.append('last: ' + lines[-1][:140])
    return '\n'.join(out)


def main():
    path, secs = sys.argv[1], min(int(sys.argv[2]) if len(sys.argv) > 2 else 0, 50)
    lines = read(path)
    if lines is None:
        print(f'no log {path}')
        return 1
    if secs:
        start, base = time.time(), len(events(lines))
        while time.time() - start < secs:
            if any(l.startswith('[rc=') for l in lines) or len(events(lines)) > base:
                break
            time.sleep(3)
            lines = read(path) or lines
    print(digest(path, lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
