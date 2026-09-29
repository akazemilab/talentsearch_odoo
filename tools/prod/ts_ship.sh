#!/bin/bash
# ts_ship.sh MODE MODULES LABEL  - apply Talent Search modules to the LIVE eot_main.
#   MODE = install | upgrade
# Runs detached on eot-odoo-prod (survives a dropped SSH). Only run after a
# rehearsal on an eot_ts* clone passed `ts_guard compare` with no difference.
# Steps: preconditions -> backup -> live eot.ir baseline -> stop odoo20 ->
# install/upgrade -> start -> wait -> live eot.ir compare. Prints the restore
# command at the top; it never restores automatically.
set -uo pipefail
MODE=${1:?install|upgrade}; MODS=${2:?modules}; LABEL=${3:?label}
CONF=/etc/odoo20.conf; TS_AP=/opt/odoo/talentsearch/addons
PY=/opt/odoo/venv/bin/python3; BIN=/opt/odoo/odoo/odoo-bin
FLAG=-i; [[ $MODE == upgrade ]] && FLAG=-u
step(){ echo "=== $(date -u +%T) $*"; }
fail(){ echo "!! $*"; exit 1; }

step preconditions
[[ -d $TS_AP/ts_core && -d $TS_AP/ts_website ]] || fail "modules not synced to $TS_AP"
grep -q "^addons_path.*$TS_AP" $CONF || {
  cp -a $CONF $CONF.bak_ts_$(date +%Y%m%d-%H%M%S)
  sed -i "s#^addons_path = #addons_path = $TS_AP,#" $CONF
  grep -q "^addons_path.*$TS_AP" $CONF || fail "could not add $TS_AP to addons_path"
  echo "added $TS_AP to addons_path (backup kept next to $CONF)"
}
systemctl is-active --quiet odoo20 || fail "odoo20 not active before ship"

step backup
TS=$(date +%Y%m%d-%H%M)
DUMP=/var/backups/odoo/eot_main_pre_ts_${LABEL}_$TS.dump
sudo -u postgres pg_dump -Fc eot_main -f "$DUMP" || fail "pg_dump failed"
tar -czf /var/backups/odoo/filestore_eot_main_pre_ts_${LABEL}_$TS.tgz -C /opt/odoo/.local/share/Odoo/filestore eot_main || fail "filestore backup failed"
echo "restore if needed: systemctl stop odoo20; sudo -u postgres dropdb eot_main; sudo -u postgres createdb -O odoo eot_main; sudo -u postgres pg_restore -d eot_main --no-owner --role=odoo $DUMP; systemctl start odoo20"

step "live eot.ir baseline"
python3 -u /opt/odoo/talentsearch/tools/prod/ts_guard.py snapshot eot_main 8069 live_${LABEL} || fail "baseline failed"

step "stop odoo20 + $MODE $MODS"
systemctl stop odoo20
sudo -u odoo env HOME=/opt/odoo $PY $BIN -c $CONF -d eot_main --db-filter='^eot_main$' $FLAG "$MODS" \
    --stop-after-init --no-http --workers=0 --max-cron-threads=0 > /tmp/ts_ship_$LABEL.log 2>&1; rc=$?
grep -E " (ERROR|CRITICAL) |Traceback|ParseError" /tmp/ts_ship_$LABEL.log | grep -v theme_paptic | head -10
step "upgrade rc=$rc; start odoo20"
systemctl start odoo20
for i in $(seq 1 60); do curl -s -o /dev/null -H "Host: www.eot.ir" http://127.0.0.1:8069/web/login && break; sleep 2; done
systemctl is-active odoo20
[[ $rc -ne 0 ]] && fail "module $MODE failed (odoo20 restarted on the unchanged code path); see /tmp/ts_ship_$LABEL.log"

step "live eot.ir compare"
python3 -u /opt/odoo/talentsearch/tools/prod/ts_guard.py compare eot_main 8069 live_${LABEL}; g=$?
step "done guard_rc=$g"
exit $g
