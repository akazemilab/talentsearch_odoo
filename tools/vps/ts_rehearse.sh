#!/bin/bash
# ts_rehearse.sh DB MODULES : clone -> serve -> eot.ir baseline -> install -> serve -> guard compare -> TS page check
DB=${1:?db}; MODS=${2:?modules}; PORT=8071
ts db clone $DB || exit 1
if [ "${SKIP_BASE:-0}" != 1 ]; then
  ts db serve $DB $PORT && ts guard snapshot $DB $PORT ${DB}_base || exit 1
  ssh eot-odoo-prod "pkill -f '[-]d $DB '"; sleep 2
fi
ts db install $DB $MODS; rc=$?; [ $rc -ne 0 ] && { echo "!! install failed"; exit $rc; }
ts db serve $DB $PORT
echo "=== guard"; ts guard compare $DB $PORT ${DB}_base; g=$?
echo "=== talent search pages"
for p in / /employers /clinics /how-it-works /evidence /sample-report /help /privacy /consent-policy /contact /pricing /about /contact/thanks /masnavi /sitemap.xml /this-does-not-exist; do echo "--- $p"; ts get $PORT "$p" ts.innerquest.me | head -3 | cut -c1-220; done
echo "=== unknown host falls back to eot.ir"; ts get $PORT / odoo.innerquest.me | head -2
echo "=== stage 1 tests"
ssh eot-odoo-prod "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=/opt/odoo/talentsearch/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=warn < /opt/odoo/talentsearch/tools/prod/tests_stage1.py 2>&1 | grep -E '^(PASS|FAIL|SUMMARY)'"
echo "[guard rc=$g]"
