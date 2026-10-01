#!/bin/bash
# ts_portal_text.sh DB PORT HOST PATH... : create (once) a portal user on a CLONE,
# sign in over HTTP and print the visible text of each PATH, one block per path.
# Refuses anything that is not an eot_ts* clone. The password never leaves the box.
set -uo pipefail
DB=${1:?db}; PORT=${2:?port}; HOST=${3:?host}; shift 3
[[ $DB == eot_ts* ]] || { echo "!! clones only"; exit 2; }
PW_FILE=/root/.ts_portal_$DB; LOGIN=ts.portal.check@example.invalid
if [ ! -f $PW_FILE ]; then
  PW=$(openssl rand -hex 12); umask 077; echo "$PW" > $PW_FILE
  cd /tmp && sudo -u odoo env HOME=/opt/odoo TS_PW="$PW" /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf \
    -d $DB --db-filter="^$DB\$" --addons-path=${TS_CODE:-/opt/odoo/talentsearch_stage}/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons \
    --no-http --log-level=warn >/dev/null 2>&1 <<'PY'
import os
u = env['res.users'].with_context(no_reset_password=True).search([('login', '=', 'ts.portal.check@example.invalid')])
if not u:
    p = env['res.partner'].create({'name': 'بررسی پرتال', 'email': 'ts.portal.check@example.invalid'})
    u = env['res.users'].with_context(no_reset_password=True).create({'name': 'بررسی پرتال', 'login': 'ts.portal.check@example.invalid',
        'partner_id': p.id, 'group_ids': [(6, 0, [env.ref('base.group_portal').id])]})
u.password = os.environ['TS_PW']
env.cr.commit()
PY
fi
PW=$(cat $PW_FILE); J=$(mktemp)
tok=$(curl -s -c $J -b $J -H "Host: $HOST" "http://127.0.0.1:$PORT/web/login" | grep -o 'name="csrf_token" value="[^"]*"' | head -1 | sed 's/.*value="//;s/"//')
code=$(curl -s -o /dev/null -w "%{http_code}" -c $J -b $J -H "Host: $HOST" -X POST "http://127.0.0.1:$PORT/web/login" \
  --data-urlencode "csrf_token=$tok" --data-urlencode "login=$LOGIN" --data-urlencode "password=$PW" --data-urlencode "redirect=/my")
if [ "$code" != 303 ]; then
  # the clone was re-restored (same name) but the password file survived: the user no longer exists.
  # Recreate it once; a comparison made while signed out is worthless.
  if [ -z "${TS_PORTAL_RETRY:-}" ]; then rm -f $J $PW_FILE; TS_PORTAL_RETRY=1 exec bash "$0" "$DB" "$PORT" "$HOST" "$@"; fi
  echo "!! portal login failed ($code): comparison invalid"
fi
echo "login: $code"
for p in "$@"; do
  echo "##### $p"
  curl -s -b $J -H "Host: $HOST" "http://127.0.0.1:$PORT$p" | python3 -c '
import sys,re,html
s=sys.stdin.read()
t=re.findall(r"<title>(.*?)</title>",s,re.S); print("title:", html.unescape(t[0].strip()) if t else "-")
b=re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>","",s)
m=re.search(r"(?is)<main[^>]*>(.*)</main>",b); b=m.group(1) if m else b
b=re.sub(r"<[^>]+>","\n",b)
for l in html.unescape(b).split("\n"):
    l=l.strip()
    if l: print(l)
'
done
rm -f $J
