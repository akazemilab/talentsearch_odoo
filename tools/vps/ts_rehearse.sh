#!/bin/bash
# ts_rehearse.sh DB INSTALL [UPGRADE]
#   preflight -> clone -> eot.ir baseline (clone on LIVE code) -> apply -> serve ->
#   [guard compare  ||  ORM suites that never commit]  -> portal compare -> pages ->
#   committing ORM suites + HTTP suites -> one REHEARSAL verdict line.
# Slots (parallel rehearsals): TS_SLOT=0|1|2 picks stage dir, port, fake-SMS ports and a lock;
# slot N>0 syncs from the worktree /root/ts_wt_sN (create it with `ts wt`). Env: SKIP_BASE=1 reuses
# the baseline snapshot of the same clone name; SKIP_CHECK=1 skips the preflight.
set -uo pipefail
DB=${1:?db}; MODS=${2:?install_modules}; UPG=${3:-}
SLOT=${TS_SLOT:-0}; export TS_SLOT=$SLOT
[[ $SLOT =~ ^[012]$ ]] || { echo "!! TS_SLOT must be 0, 1 or 2"; exit 2; }
PORT=$((8071 + 2 * SLOT))
STAGE=/opt/odoo/talentsearch_stage$([ "$SLOT" != 0 ] && echo "_s$SLOT")
REPO_DIR=$([ "$SLOT" = 0 ] && echo /root/talentsearch_odoo || echo /root/ts_wt_s$SLOT)
P=eot-odoo-prod; J=/root/ts-jobs
PORTAL_PATHS="/my /my/home /my/account /my/security"
ALL=" ${MODS//,/ } ${UPG//,/ } "
has(){ [[ $ALL == *" $1 "* ]]; }

exec 8>$J/slot$SLOT.lock
flock -n 8 || { echo "!! slot $SLOT is busy ($(cat $J/slot$SLOT.owner 2>/dev/null)); use another TS_SLOT"; exit 2; }
# capacity rule (4 cores): at most 2 rehearsals at once, and only 1 while a ship runs (live visitors first)
busy=0; for s in 0 1 2; do [ $s != $SLOT ] && ! flock -n $J/slot$s.lock true 2>/dev/null && ! grep -q "^ship" $J/slot$s.owner 2>/dev/null && busy=$((busy+1)); done
shipping=$(ssh $P "pgrep -f '[t]s_ship.sh' >/dev/null && echo 1 || echo 0")
if [ $busy -ge 2 ] || { [ "$shipping" = 1 ] && [ $busy -ge 1 ]; }; then echo "!! capacity: $busy other rehearsal(s) running, ship running: $shipping"; exit 2; fi
echo "$DB pid $$ since $(date +%T)" > $J/slot$SLOT.owner
trap 'rm -f $J/slot$SLOT.owner' EXIT
echo "=== $(date +%T) slot $SLOT: $DB on :$PORT, stage $STAGE, repo $REPO_DIR ($(git -C $REPO_DIR rev-parse --short HEAD) $(git -C $REPO_DIR branch --show-current))"

if [ "${SKIP_CHECK:-0}" != 1 ]; then
  echo "=== $(date +%T) preflight"
  out=$(python3 /root/talentsearch_odoo/tools/vps/ts_check.py $REPO_DIR); crc=$?
  echo "$out" | grep -E '^E |^CHECK'
  [ $crc -ne 0 ] && { echo "!! preflight failed"; exit 1; }
fi

ts sync >/dev/null || exit 1
orm(){  # orm FILE : odoo shell on the clone, only verdict lines
  ssh $P "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=$STAGE/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < $STAGE/tools/prod/$1 2>&1 | grep -E '^(FAIL|SUMMARY|    unexpected)|Error|Traceback'"
}
http(){ # http FILE : HTTP suite against the served clone
  ssh $P "TS_SLOT=$SLOT PYTHONIOENCODING=utf-8 python3 -u $STAGE/tools/prod/$1 $DB $PORT 2>&1 | grep -E '^(FAIL|SUMMARY)|Traceback|Error'"
}

ts db clone $DB || exit 1
ssh $P "rm -f /root/.ts_flow_${DB}_* /root/.ts_portal_$DB"   # a re-used clone name must not inherit stale test users
if [ "${SKIP_BASE:-0}" != 1 ]; then
  # baseline = the clone served on the code that is LIVE now (stage may already hold newer code)
  ssh $P "TS_CODE=/opt/odoo/talentsearch bash $STAGE/tools/prod/ts_db.sh serve $DB $PORT" || exit 1
  echo "=== $(date +%T) baseline"
  ssh $P "python3 -u $STAGE/tools/prod/ts_guard.py snapshot $DB $PORT ${DB}_base" || exit 1
  ssh $P "TS_CODE=/opt/odoo/talentsearch bash $STAGE/tools/prod/ts_portal_text.sh $DB $PORT www.eot.ir $PORTAL_PATHS" > $J/${DB}_portal_base.txt
  ssh $P "pkill -f '[-]d $DB '"; sleep 2
fi
ts db apply $DB "$MODS" "$UPG"; rc=$?; [ $rc -ne 0 ] && { echo "!! install failed"; ts db errors $DB 2>/dev/null | head -5; exit $rc; }
ts db serve $DB $PORT || exit 1

# ---- guard compare (HTTP + read-only SQL) runs while the ORM suites that never commit run:
#      an uncommitted shell transaction cannot change what the guard reads or renders.
echo "=== $(date +%T) guard || non-committing ORM suites"
ssh $P "python3 -u $STAGE/tools/prod/ts_guard.py compare $DB $PORT ${DB}_base" > $J/${DB}_guard.txt 2>&1 &
GPID=$!
NOCOMMIT=(tests_stage1.py tests_assessment.py)
has ts_talent && NOCOMMIT+=(tests_talent.py)
has ts_org && NOCOMMIT+=(tests_org.py tests_org_resp.py tests_panel.py tests_edge.py tests_signup.py)
has ts_panel && NOCOMMIT+=(tests_pv2_0.py tests_pv2_1.py tests_pv2_2.py tests_pv2_3.py tests_pv2_4.py tests_pv2_5.py tests_pv2_6.py tests_pv2_7.py tests_pv2_8.py tests_pv2_9.py tests_pv2_10.py tests_pv2_11.py tests_pv2_12.py tests_pv2_13.py tests_pv2_14.py)
for f in "${NOCOMMIT[@]}"; do
  [ -f $REPO_DIR/tools/prod/$f ] || continue
  grep -q "cr.commit" $REPO_DIR/tools/prod/$f && { echo "!! $f commits; it cannot run beside the guard"; continue; }
  echo "=== $(date +%T) orm $f"; orm $f
done
has ts_talent && { echo "=== $(date +%T) talent engine"; ssh $P "python3 $STAGE/tools/prod/tests_talent_engine.py" 2>&1 | grep -E '^(FAIL|SUMMARY)'; }
wait $GPID; g=$?
echo "=== $(date +%T) guard result"; cat $J/${DB}_guard.txt | tail -15

echo "=== $(date +%T) signed-in eot.ir portal (/my ...) before vs after"
ssh $P "bash $STAGE/tools/prod/ts_portal_text.sh $DB $PORT www.eot.ir $PORTAL_PATHS" > $J/${DB}_portal_after.txt
pb=$(head -1 $J/${DB}_portal_base.txt 2>/dev/null)
if grep -q '^!!' $J/${DB}_portal_base.txt $J/${DB}_portal_after.txt 2>/dev/null || [ "$pb" != "login: 303" ]; then
  echo "!! portal comparison invalid (base: $pb, after: $(head -1 $J/${DB}_portal_after.txt))"; pv=1
elif diff -q $J/${DB}_portal_base.txt $J/${DB}_portal_after.txt >/dev/null; then
  echo "portal: eot.ir UNCHANGED ($(wc -l < $J/${DB}_portal_base.txt) lines, signed in)"; pv=0
else
  echo "!! portal differs:"; diff $J/${DB}_portal_base.txt $J/${DB}_portal_after.txt | head -20; pv=1
fi

echo "=== $(date +%T) talent search pages"
ssh $P "python3 $STAGE/tools/prod/ts_pages.py $PORT talentsearch.ir / /employers /clinics /how-it-works /evidence /sample-report /help /privacy /consent-policy /contact /pricing /about /contact/thanks /masnavi /sitemap.xml /this-does-not-exist /panel /panel/terms /signup" | grep -E '^(FAIL|SUMMARY)'
ssh $P "python3 $STAGE/tools/prod/ts_pages.py $PORT odoo.innerquest.me /" | grep -E 'w1|FAIL' | head -1 | sed 's/^/unknown host -> /'

# ---- suites that commit or depend on each other's committed fixtures: strictly in order
echo "=== $(date +%T) http participant flow"; http ts_http_flow.py
if has ts_talent; then
  echo "=== $(date +%T) http talent flow"; ssh $P "rm -f /root/.ts_flow_${DB}_*"; http ts_http_talent.py
  echo "=== $(date +%T) http institute (education) view"; ssh $P "rm -f /root/.ts_flow_${DB}_ts.edu*"; http ts_http_edu.py
  echo "=== $(date +%T) http responsible-specialist UI"; http ts_http_resp.py
fi
has ts_org && { echo "=== $(date +%T) http organization flow"; http ts_http_org.py; }
if has ts_sms; then
  echo "=== $(date +%T) http mobile sign-in + invite links"; http ts_http_signup.py
  echo "=== $(date +%T) http panel self-service"; http ts_http_panel.py
fi
if has ts_panel; then
  echo "=== $(date +%T) panel v2: ts_check self-test"; python3 /root/talentsearch_odoo/tools/vps/ts_check.py --selftest | sed 's/^SELFTEST FAILED/FAIL ts_check selftest/'
  echo "=== $(date +%T) panel v2: fixtures twice (P22)"
  fx(){ ssh $P "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=$STAGE/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < $STAGE/tools/prod/pv2_fixtures.py 2>&1 | grep -E '^FIXTURES|Error|Traceback'"; }
  f1=$(fx); f2=$(fx); echo "$f1"
  if [[ "$f1" == FIXTURES* ]] && [ "$f1" = "$f2" ]; then echo "PASS  fixtures run twice with identical counts"; else echo "FAIL  fixtures differ between runs: [$f1] [$f2]"; fi
  echo "=== $(date +%T) http panel v2 S0"; http ts_http_pv2_0.py
  echo "=== $(date +%T) http panel v2 S1"; http ts_http_pv2_1.py
  echo "=== $(date +%T) http panel v2 S2"; http ts_http_pv2_2.py
  echo "=== $(date +%T) http panel v2 S3"; http ts_http_pv2_3.py
  echo "=== $(date +%T) http panel v2 S4"; http ts_http_pv2_4.py
  echo "=== $(date +%T) http panel v2 S5"; http ts_http_pv2_5.py
  echo "=== $(date +%T) http panel v2 S6"; http ts_http_pv2_6.py
  echo "=== $(date +%T) http panel v2 S7"; http ts_http_pv2_7.py
  echo "=== $(date +%T) http panel v2 S8"; http ts_http_pv2_8.py
  echo "=== $(date +%T) http panel v2 S9"; http ts_http_pv2_9.py
  echo "=== $(date +%T) http panel v2 S10"; http ts_http_pv2_10.py
  echo "=== $(date +%T) http panel v2 S11"; http ts_http_pv2_11.py
  echo "=== $(date +%T) http panel v2 S12"; http ts_http_pv2_12.py
  echo "=== $(date +%T) http panel v2 S13"; http ts_http_pv2_13.py
  echo "=== $(date +%T) http panel v2 S14"; http ts_http_pv2_14.py
fi
if has ts_kavenegar; then
  echo "=== $(date +%T) kavenegar tests (fake API, commits)"; orm tests_kavenegar.py
  echo "=== $(date +%T) kavenegar webhooks (http)"; http ts_http_kv.py
fi
has ts_sms && { echo "=== $(date +%T) talent search SMS flows (fake Kavenegar)"; http ts_http_sms.py; }

echo "[guard rc=$g]"
# one verdict line: guard, portal, failures that are not on the known list
unknown=$(grep -E '^(FAIL|Traceback)' $J/${TS_JOB:-rehearse_none}.log 2>/dev/null | grep -vFf /root/talentsearch_odoo/tools/vps/known_failures.txt | grep -c .)
echo "REHEARSAL $DB slot $SLOT: guard $([ $g = 0 ] && echo UNCHANGED || echo DIFFERS), portal $([ $pv = 0 ] && echo UNCHANGED || echo 'NOT OK'), unexpected failures: ${unknown:-?}"
echo "next: ts db stop $DB   (the clone keeps serving on :$PORT until then)"
