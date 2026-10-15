#!/bin/bash
# ts_ui_matrix.sh DB PORT OUTDIR : seed fixture users on a served clone of the slot (via ts_http_pv2_19.py), build the
# route matrix for public / owner / counselor, take shots with ts_shot.py (widths from TS_SHOT_WIDTHS) and copy the
# png files + report.txt to OUTDIR (under /root/share/out, synced to the owner's Mac). Called by `ts shots DB`.
# `ts shots DB ux` (TS_SHOT_WIDTHS=ux): the full UX-audit matrix instead (ts_ux_seed.py: every page route in its main
# states, roles owner / counselor / participant / player states / clinician / reviewer / public), widths 375,1280
# plus a dark-theme pass at 375 (TS_SHOT_DARK).
# `ts shots DB take` (TS_SHOT_WIDTHS=take): the same seed steps, but ts_ux_seed.py (TS_UX_ONLY=take) emits only the
# participant (test-taker) matrix: every page and state of the test-taking journey, signed out and signed in; widths
# 360,390,1280, dark pass at 390, and a viewport-only <stem>_fold.png per phone width (TS_SHOT_FOLD=1).
set -u
DB=$1; PORT=$2; OUT=$3; SLOT=${TS_SLOT:-0}
if [ "$SLOT" = 0 ]; then STAGE=/opt/odoo/talentsearch_stage; REPO=/root/talentsearch_odoo
else STAGE=/opt/odoo/talentsearch_stage_s$SLOT; REPO=/root/ts_wt_s$SLOT; fi
MODE=${TS_SHOT_WIDTHS:-}
SEED_ENV=; [ "$MODE" = take ] && SEED_ENV='TS_UX_ONLY=take'     # sudo drops the caller's environment: pass it explicitly
# W=career: only the ts_career pages (no seed suites; see the career branch below)
SHELL_CMD="cd /tmp && sudo -u odoo env HOME=/opt/odoo $SEED_ENV /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=$STAGE/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=error"
case "$DB" in eot_ts*) ;; *) echo "!! shots run on eot_ts* clones only"; exit 2 ;; esac
# onb1: the mobile sign-in (S-AUTH) renders only while codes can be sent. On the clone SMS is switched on with Kavenegar
# pointed at the discard port of the clone host (nothing listens there) and a dummy key, so no SMS can ever leave it;
# invitation/result SMS stay off. A pending code for 09127770375 (created «tomorrow», so its resend wait never ends)
# lets the matrix capture the code step: POSTSHOT /signup/send with that number.
echo "=== $(date +%T) sms on (dead endpoint)"
ssh eot-odoo-prod "$SHELL_CMD" <<'PY' 2>&1 | grep -E '^SHOTSMS|Error' | tail -3
from datetime import timedelta
from odoo import fields
assert env.cr.dbname.startswith('eot_ts'), env.cr.dbname
env['ir.config_parameter'].sudo().set_str('ts_kavenegar.api_base', 'http://127.0.0.1:9/v1/%s/%s.json')
c = env.company.sudo()
c.write({'kv_lines': '10004346'})
c.write({'kv_enabled': True, 'kv_api_key': 'SHOTS-NO-SEND', 'kv_sender': '10004346', 'ts_sms_otp': True,
         'ts_sms_invite': False, 'ts_sms_result': False})
P, O = '09127770375', env['ts.signup.otp'].sudo()
O.search([('phone', '=', P)]).unlink()
env['ts.signup.lock'].sudo().search([('phone', '=', P)]).unlink()
r = O.create({'phone': P, 'salt': 'shots', 'code_hash': '0' * 64, 'expires_at': fields.Datetime.now() + timedelta(days=2)})
env.cr.execute("update ts_signup_otp set create_date = now() + interval '1 day' where id = %s", [r.id])
env.cr.commit()
print('SHOTSMS on: kavenegar -> 127.0.0.1:9 (dead), otp', bool(c.kv_enabled and c.ts_sms_otp), 'code step for', P)
PY
echo "=== $(date +%T) seed"
[ "$MODE" = career ] || [ "$MODE" = clinic ] || ssh -n eot-odoo-prod "TS_SLOT=$SLOT PYTHONIOENCODING=utf-8 python3 -u $STAGE/tools/prod/ts_http_pv2_19.py $DB $PORT 2>&1 | grep -E '^(FAIL|SUMMARY)'"
if [ "$MODE" = career ]; then
  # ts_career: the free career pages of the HTTP suite's people (run ts_http_career.py on this clone first)
  export TS_SHOT_WIDTHS=360,390,1280 TS_SHOT_DARK=${TS_SHOT_DARK:-390} TS_SHOT_FOLD=1
  ssh eot-odoo-prod "$SHELL_CMD" 2>&1 > /tmp/ui_matrix_out_$DB.txt <<'PY'
import json
U = env['res.users']
p = U.search([('login', '=', 'ts.career.http@example.invalid')])
q = U.search([('login', '=', 'ts.career.http2@example.invalid')])
run = env['ts.career.run'].sudo().search([('user_id', '=', p.id)])
res = run.ts_result() or {'rows': []}
code = res['rows'][0]['code'] if res['rows'] else 'none'
rq = env['ts.career.run'].sudo().ts_for_user(q, create=True)
at = rq.ts_ensure_attempt('CAREER-IP-60')
if at.state == 'consent':
    at.give_consent()
# completion (card mode): page 1 fully answered shows its end card «نیمی از راه»; page 2 shows its first card
for it in at.active_items()[:30]:
    at.save_answer(it.id, 3)
env.cr.commit()
print('CAREER matrix')
print(json.dumps({'': ['/career'], p.login: ['/career', '/career/r', '/career/r?ready=1', '/career/job/' + code, '/career/r?edit=1'],
                  q.login: ['/take/%s?page=1' % at.access_token, '/take/%s?page=2' % at.access_token, '/career']}))
PY
elif [ "$MODE" = clinic ]; then
  # clin9: the clinic panel per role (office / therapist / owner) at 1280 and 390 with the spacing audit (TS_SHOT_GAPS)
  # and one contact sheet per role and width (ts_sheet.py): review the sheets, not page by page
  export TS_SHOT_WIDTHS=1280,390 TS_SHOT_GAPS=1
  ssh -n eot-odoo-prod "TS_SLOT=$SLOT PYTHONIOENCODING=utf-8 python3 -u $STAGE/tools/prod/ts_http_clin8.py $DB $PORT 2>&1 | grep -E '^(FAIL|SUMMARY)'"
  ssh eot-odoo-prod "$SHELL_CMD" 2>&1 > /tmp/ui_matrix_out_$DB.txt <<'PY'
import json
ws = env['ts.workspace'].sudo().search([('name', '=', 'مرکز جریان clin8')], order='id desc', limit=1)
a = env['ts.assignment'].sudo().search([('workspace_id', '=', ws.id), ('state', '=', 'done')], limit=1)
W, C, AT = '/my/workspaces/%d' % ws.id, a.client_id.id, a.attempt_id.id
L = lambda r: 'ts.clin8.%s.http@example.invalid' % r
print('CLINIC matrix', ws.id, C, AT)
print(json.dumps({
    L('off'): [W, W + '/services', W + '/clients', W + '/clients/%d' % C, W + '/invites/new', W + '/invites', W + '/credits'],
    L('doc'): [W, W + '/services', W + '/clients', W + '/clients/%d/r/%d' % (C, AT), W + '/reports'],
    L('own'): [W, W + '/settings', W + '/members', W + '/credits']}))
PY
elif [ "$MODE" = ux ] || [ "$MODE" = take ]; then
  if [ "$MODE" = take ]; then
    export TS_SHOT_WIDTHS=360,390,1280 TS_SHOT_DARK=${TS_SHOT_DARK:-390} TS_SHOT_FOLD=1 TS_UX_ONLY=take
  else
    export TS_SHOT_WIDTHS=375,1280 TS_SHOT_DARK=${TS_SHOT_DARK:-375}
  fi
  scp -q $REPO/tools/prod/pv2_fixtures.py $REPO/tools/vps/ts_ux_seed.py $REPO/tools/vps/ts_onb2_seed.py eot-odoo-prod:/tmp/
  ssh -n eot-odoo-prod "$SHELL_CMD < /tmp/pv2_fixtures.py 2>&1 | grep -E '^FIXTURES|Error' | tail -3"
  ssh -n eot-odoo-prod "$SHELL_CMD < /tmp/ts_ux_seed.py 2>&1 | grep -E '^(UXMATRIX|SEED-SKIP)|Error' | tail -20"
  ssh -n eot-odoo-prod "TS_SLOT=$SLOT python3 $STAGE/tools/prod/ts_ux_users.py $DB $PORT /tmp/ux_matrix.json; cat /tmp/ux_matrix.json" > /tmp/ui_matrix_out_$DB.txt
else
  scp -q $REPO/tools/vps/ts_ui_seed.py $REPO/tools/vps/ts_onb2_seed.py $REPO/tools/vps/ts_onb3_seed.py eot-odoo-prod:/tmp/
  ssh -n eot-odoo-prod "chmod 644 /tmp/ts_onb2_seed.py /tmp/ts_onb3_seed.py; $SHELL_CMD < /tmp/ts_ui_seed.py 2>&1 | grep -E '^(MATRIX|consent|ONB2SEED|ONB3SEED|SEED-SKIP)'; cat /tmp/ui_matrix.json" > /tmp/ui_matrix_out_$DB.txt
  # onb2: the claimed-report login has the owner's password (ts_onb2_seed.py copies the hash): the same root-only file
  ssh -n eot-odoo-prod "f=/root/.ts_flow_${DB}_ts.pv2s19.owner.http; [ -f \$f ] && install -m 600 \$f /root/.ts_flow_${DB}_ts.onb2.shot.claim"
fi
head -1 /tmp/ui_matrix_out_$DB.txt
tail -1 /tmp/ui_matrix_out_$DB.txt > /root/ts-jobs/ui_matrix_$DB.json
echo "=== $(date +%T) shots"
rm -rf /root/ts-jobs/shots; mkdir -p /root/ts-jobs/shots
PY=/root/eot-browser/venv/bin/python; [ -x "$PY" ] || PY=python3
$PY $REPO/tools/vps/ts_shot.py $DB $PORT --matrix /root/ts-jobs/ui_matrix_$DB.json 2>&1 | tee /root/ts-jobs/ui_shot_report_$DB.txt | tail -3
rm -rf "$OUT"; mkdir -p "$OUT"; cp /root/ts-jobs/shots/*.png "$OUT"/ 2>/dev/null; cp /root/ts-jobs/ui_shot_report_$DB.txt "$OUT"/report.txt
cp /root/ts-jobs/ui_matrix_$DB.json "$OUT"/matrix.json 2>/dev/null
if [ "$MODE" = clinic ]; then
  for r in off doc own; do for w in 1280 390; do
    if [ $w = 1280 ]; then c=3; t=520; else c=6; t=260; fi
    $PY $REPO/tools/vps/ts_sheet.py "$OUT/sheet_${r}_$w.png" $c $t $(ls /root/ts-jobs/shots/ts.clin8.${r}.http_*_$w.png 2>/dev/null)
  done; done
  # clin10: the side box and menu of each role's dashboard, side by side (one small image for shell reviews)
  for r in off doc own; do
    f=$(ls /root/ts-jobs/shots/ts.clin8.${r}.http_my_workspaces_*_1280.png 2>/dev/null | grep -E '_[0-9]+_1280.png$' | head -1)
    [ -n "$f" ] && python3 $REPO/tools/vps/ts_crop.py "$f" /root/ts-jobs/rail_$r.png -400 0 400 600 >/dev/null
  done
  TS_SHEET_CROP=2000 $PY $REPO/tools/vps/ts_sheet.py "$OUT/rails.png" 3 400 /root/ts-jobs/rail_off.png /root/ts-jobs/rail_doc.png /root/ts-jobs/rail_own.png
  # only pages that have a problem or a gap over 24px: the page line, then its gap line (short enough to read whole)
  awk '/^[0-9-]+ /{u=$0; p=($0 !~ / ok( \[|$)/)} /^ *gaps /{ if ($0 !~ / -$/ || p) print u "\n" $0 }' \
    /root/ts-jobs/ui_shot_report_$DB.txt | sed 's/#tsp-rail:[^|]*| *//g' > "$OUT/gaps.txt"
  echo "gaps: $(grep -c ' gaps ' "$OUT/gaps.txt") page/width with gaps or problems"
fi
echo "=== $(date +%T) done: $(ls "$OUT" | wc -l) files in $OUT"
