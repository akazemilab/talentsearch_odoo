#!/usr/bin/env python3
"""patch_gateway.py THEME_REPO - idempotently wire mcp_ts into the eot gateway (mcp_server.py) and `eot mcp-update`."""
import re, sys
repo = sys.argv[1]
p = repo + '/tools/prod/mcp_server.py'
s = open(p, encoding='utf-8').read()
if 'import mcp_ts' not in s:
    s = s.replace('from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n',
                  'from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n\n'
                  'import mcp_ts  # tools-VPS tools (ts, eot_vps, vps_*) over a forced-command ssh key - see mcp_ts.py\n', 1)
    s = s.replace('{"tools": TOOLS}}', '{"tools": TOOLS + mcp_ts.TOOLS}}', 1)
    s = s.replace('if name not in {t["name"] for t in TOOLS}:', 'if name not in {t["name"] for t in TOOLS} | mcp_ts.NAMES:', 1)
    old = '            try:\n                ok, text = call_tool(name, args)'
    new = ('            if name in mcp_ts.NAMES:\n'
           '                try:\n'
           '                    ok, content = mcp_ts.call(name, args)\n'
           '                except Exception as e:\n'
           '                    log.exception("tool %s failed", name)\n'
           '                    ok, content = False, [{"type": "text", "text": f"internal error: {e}"}]\n'
           '                self._send(200, {"jsonrpc": "2.0", "id": rid, "result": {"content": content, "isError": not ok}})\n'
           '                return\n' + old)
    assert s.count(old) == 1, 'call site not found'
    s = s.replace(old, new, 1)
    assert s.count('mcp_ts.') == 5, s.count('mcp_ts.')
    open(p, 'w', encoding='utf-8').write(s)
e = repo + '/tools/vps/eot'
t = open(e, encoding='utf-8').read()
if 'mcp_ts.py' not in t:
    t = t.replace('for f in mcp_server.py mcp_scss_check.sh', 'for f in mcp_server.py mcp_ts.py mcp_scss_check.sh', 1)
    t = t.replace('python3 -m py_compile /opt/eot-mcp/.new-mcp_server.py ', 'python3 -m py_compile /opt/eot-mcp/.new-mcp_server.py /opt/eot-mcp/.new-mcp_ts.py ', 1)
    t = t.replace('      mv /opt/eot-mcp/.new-mcp_server.py       /opt/eot-mcp/mcp_server.py\n',
                  '      mv /opt/eot-mcp/.new-mcp_server.py       /opt/eot-mcp/mcp_server.py\n'
                  '      mv /opt/eot-mcp/.new-mcp_ts.py           /opt/eot-mcp/mcp_ts.py\n', 1)
    t = t.replace('chown eotmcp:eotmcp /opt/eot-mcp/mcp_server.py\n', 'chown eotmcp:eotmcp /opt/eot-mcp/mcp_server.py /opt/eot-mcp/mcp_ts.py\n', 1)
    t = t.replace('chmod 700 /opt/eot-mcp/mcp_server.py ', 'chmod 700 /opt/eot-mcp/mcp_server.py /opt/eot-mcp/mcp_ts.py ', 1)
    assert t.count('mcp_ts.py') == 6, t.count('mcp_ts.py')
    open(e, 'w', encoding='utf-8').write(t)
print('PATCHED')
