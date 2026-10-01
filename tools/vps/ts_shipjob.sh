#!/bin/bash
# ts_shipjob.sh INS UPG LABEL - started by `ts ship` as job ship_LABEL. Holds the slot-0 lock (no
# rehearsal can sync stage while the ship reads it), syncs stage, starts ts_ship.sh DETACHED on prod
# (survives this job or the VPS dying), mirrors its log here until it ends, then runs `ts live` and
# records the shipped commit in /root/ts-jobs/LIVE_COMMIT (reference for `ts check`).
set -uo pipefail
INS=$1; UPG=$2; LABEL=$3; P=eot-odoo-prod; J=/root/ts-jobs; REPO=/root/talentsearch_odoo
exec 8>$J/slot0.lock
flock -n 8 || { echo "!! slot 0 is busy ($(cat $J/slot0.owner 2>/dev/null)); wait for that rehearsal"; exit 2; }
echo "ship $LABEL pid $$ since $(date +%T)" > $J/slot0.owner
trap 'rm -f $J/slot0.owner' EXIT
COMMIT=$(git -C $REPO rev-parse HEAD)
echo "=== $(date +%T) ship $LABEL: install=[$INS] upgrade=[$UPG] commit $(git -C $REPO rev-parse --short HEAD) ($(git -C $REPO branch --show-current))"
ssh $P "systemctl is-active --quiet odoo20" || { echo "!! odoo20 not active"; exit 1; }
restarts=$(ssh $P "journalctl -u odoo20 --since '-3min' --no-pager | grep -c 'Started odoo20\|Stopping odoo20'")
[ "$restarts" -gt 0 ] && { echo "!! odoo20 restarted in the last 3 minutes (someone else is working); wait for quiet"; exit 1; }
TS_SLOT=0 ts sync || exit 1
R=/root/ts-jobs/ship_$LABEL.log
ssh $P "test ! -e $R" || { echo "!! $R already exists on prod: label $LABEL was used before"; exit 1; }
ssh $P "TS_SHIP_DRY=${TS_SHIP_DRY:-0} setsid nohup bash /opt/odoo/talentsearch_stage/tools/prod/ts_ship.sh $(printf '%q ' "$INS" "$UPG" "$LABEL") > $R 2>&1 < /dev/null &"
sleep 3
seen=0
while :; do
  out=$(ssh $P "tail -n +$((seen + 1)) $R" 2>/dev/null) && [ -n "$out" ] && { printf '%s\n' "$out"; seen=$((seen + $(printf '%s\n' "$out" | wc -l))); }
  ssh $P "pgrep -f '[t]s_ship.sh' >/dev/null" || break
  sleep 10
done
rest=$(ssh $P "tail -n +$((seen + 1)) $R"); [ -n "$rest" ] && printf '%s\n' "$rest"
if ssh $P "grep -q 'done guard_rc=0' $R"; then
  [ "${TS_SHIP_DRY:-0}" = 1 ] || echo "$COMMIT" > $J/LIVE_COMMIT; ok=1
else ok=0; fi
echo "=== $(date +%T) live probes"; ts live
echo "SHIP $LABEL: $([ $ok = 1 ] && echo 'OK, eot.ir UNCHANGED' || echo 'NOT OK - read the log above')"
[ $ok = 1 ]
