#!/bin/bash
# ts_rehearse.sh DB MODULES : clone -> serve -> eot.ir baseline -> install -> serve -> guard compare -> TS page check
DB=${1:?db}; MODS=${2:?install_modules}; UPG=${3:-}; PORT=8071
PORTAL_PATHS="/my /my/home /my/account /my/security"
ts db clone $DB || exit 1
ssh eot-odoo-prod "rm -f /root/.ts_flow_${DB}_*"   # a re-used clone name must not inherit stale test-user passwords
if [ "${SKIP_BASE:-0}" != 1 ]; then
  # baseline = the clone served on the code that is LIVE now (stage may already hold newer code)
  ts sync >/dev/null; ssh eot-odoo-prod "TS_CODE=/opt/odoo/talentsearch bash /opt/odoo/talentsearch_stage/tools/prod/ts_db.sh serve $DB $PORT" && ts guard snapshot $DB $PORT ${DB}_base || exit 1
  ssh eot-odoo-prod "TS_CODE=/opt/odoo/talentsearch bash /opt/odoo/talentsearch_stage/tools/prod/ts_portal_text.sh $DB $PORT www.eot.ir $PORTAL_PATHS" > /root/ts-jobs/${DB}_portal_base.txt
  ssh eot-odoo-prod "pkill -f '[-]d $DB '"; sleep 2
fi
ts db apply $DB "$MODS" "$UPG"; rc=$?; [ $rc -ne 0 ] && { echo "!! install failed"; exit $rc; }
ts db serve $DB $PORT
echo "=== guard"; ts guard compare $DB $PORT ${DB}_base; g=$?
echo "=== signed-in eot.ir portal (/my ...) before vs after"
ssh eot-odoo-prod "bash /opt/odoo/talentsearch_stage/tools/prod/ts_portal_text.sh $DB $PORT www.eot.ir $PORTAL_PATHS" > /root/ts-jobs/${DB}_portal_after.txt
if diff -q /root/ts-jobs/${DB}_portal_base.txt /root/ts-jobs/${DB}_portal_after.txt >/dev/null; then echo "portal: eot.ir UNCHANGED"; else echo "!! portal differs:"; diff /root/ts-jobs/${DB}_portal_base.txt /root/ts-jobs/${DB}_portal_after.txt | head -40; fi
echo "=== talent search pages"
for p in / /employers /clinics /how-it-works /evidence /sample-report /help /privacy /consent-policy /contact /pricing /about /contact/thanks /masnavi /sitemap.xml /this-does-not-exist; do echo "--- $p"; ts get $PORT "$p" talentsearch.ir | head -3 | cut -c1-220; done
echo "=== unknown host falls back to eot.ir"; ts get $PORT / odoo.innerquest.me | head -2
echo "=== stage 1 tests"
ssh eot-odoo-prod "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=/opt/odoo/talentsearch_stage/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < /opt/odoo/talentsearch_stage/tools/prod/tests_stage1.py 2>&1 | grep -E '^(PASS|FAIL|SUMMARY)'"
echo "=== assessment tests"
ssh eot-odoo-prod "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=/opt/odoo/talentsearch_stage/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < /opt/odoo/talentsearch_stage/tools/prod/tests_assessment.py 2>&1 | grep -E '^(PASS|FAIL|SUMMARY|    unexpected)|Error'"
echo "=== http participant flow"
ssh eot-odoo-prod "PYTHONIOENCODING=utf-8 python3 -u /opt/odoo/talentsearch_stage/tools/prod/ts_http_flow.py $DB $PORT"
if [[ " ${MODS//,/ } " == *" ts_talent "* ]]; then
  echo "=== talent engine tests"; ssh eot-odoo-prod "python3 /opt/odoo/talentsearch_stage/tools/prod/tests_talent_engine.py" 2>&1 | grep -E '^(FAIL|SUMMARY)|passed' 
  echo "=== talent tests"
  ssh eot-odoo-prod "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=/opt/odoo/talentsearch_stage/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < /opt/odoo/talentsearch_stage/tools/prod/tests_talent.py 2>&1 | grep -E '^(FAIL|SUMMARY|    unexpected)|Error'"
  echo "=== http talent flow"
  ssh eot-odoo-prod "rm -f /root/.ts_flow_${DB}_*; PYTHONIOENCODING=utf-8 python3 -u /opt/odoo/talentsearch_stage/tools/prod/ts_http_talent.py $DB $PORT" | grep -E '^(FAIL|SUMMARY)|Traceback|Error'
fi
if [[ " ${MODS//,/ } ${UPG//,/ } " == *" ts_talent "* ]]; then
  echo "=== http institute (education) view"
  ssh eot-odoo-prod "rm -f /root/.ts_flow_${DB}_ts.edu*; PYTHONIOENCODING=utf-8 python3 -u /opt/odoo/talentsearch_stage/tools/prod/ts_http_edu.py $DB $PORT" | grep -E '^(PASS|FAIL|SUMMARY)|Traceback|Error'
  echo "=== http responsible-specialist UI"
  ssh eot-odoo-prod "PYTHONIOENCODING=utf-8 python3 -u /opt/odoo/talentsearch_stage/tools/prod/ts_http_resp.py $DB $PORT" | grep -E '^(PASS|FAIL|SUMMARY)|Traceback|Error'
fi
if [[ " ${MODS//,/ } ${UPG//,/ } " == *" ts_org "* ]]; then
  echo "=== organization tests"
  ssh eot-odoo-prod "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=/opt/odoo/talentsearch_stage/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < /opt/odoo/talentsearch_stage/tools/prod/tests_org.py 2>&1 | grep -E '^(PASS|FAIL|SUMMARY|    unexpected)|Error'"
  echo "=== responsible-specialist tests"
  ssh eot-odoo-prod "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\\$' --addons-path=/opt/odoo/talentsearch_stage/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < /opt/odoo/talentsearch_stage/tools/prod/tests_org_resp.py 2>&1 | grep -E '^(PASS|FAIL|SUMMARY|    unexpected)|Error'"
  echo "=== http organization flow"
  ssh eot-odoo-prod "PYTHONIOENCODING=utf-8 python3 -u /opt/odoo/talentsearch_stage/tools/prod/ts_http_org.py $DB $PORT"
fi
if [[ " ${MODS//,/ } ${UPG//,/ } " == *" ts_kavenegar "* ]]; then
  echo "=== kavenegar tests (fake API)"
  ssh eot-odoo-prod "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=/opt/odoo/talentsearch_stage/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < /opt/odoo/talentsearch_stage/tools/prod/tests_kavenegar.py 2>&1 | grep -E '^(PASS|FAIL|SUMMARY|    unexpected)|Error|Traceback'"
  echo "=== kavenegar webhooks (http)"
  ssh eot-odoo-prod "python3 -u /opt/odoo/talentsearch_stage/tools/prod/ts_http_kv.py $DB $PORT"
fi
if [[ " ${MODS//,/ } ${UPG//,/ } " == *" ts_sms "* ]]; then
  echo "=== talent search SMS flows (fake Kavenegar)"
  ssh eot-odoo-prod "PYTHONIOENCODING=utf-8 python3 -u /opt/odoo/talentsearch_stage/tools/prod/ts_http_sms.py $DB $PORT"
fi
echo "[guard rc=$g]"
