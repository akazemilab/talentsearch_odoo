#!/bin/bash
# ts_db.sh - Talent Search database operations on eot-odoo-prod (run as root).
#   clone DB            restore the newest eot_main dump + filestore into DB
#   install DB MODS     -i MODS on DB (comma list), stop after init
#   upgrade DB MODS     -u MODS on DB
#   serve DB [PORT]     serve DB detached (default :8071, workers=0, no cron)
#   stop DB             stop serving + drop DB + filestore, with proof
#   modules DB          installed module names, one per line
# Safety: every command refuses any DB name starting with eot_main unless
# TS_LIVE=1 is set (only `ts ship` sets it, after a passing rehearsal).
set -uo pipefail
FS=/opt/odoo/.local/share/Odoo/filestore
PY=/opt/odoo/venv/bin/python3; BIN=/opt/odoo/odoo/odoo-bin
AP=/opt/odoo/talentsearch/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons
CMD=${1:?command}; DB=${2:?db}
step(){ echo "=== $(date +%T) $*"; }
guard_db(){
  if [[ $DB == eot_main* && ${TS_LIVE:-0} != 1 ]]; then echo "!! refusing live db $DB (clones must be eot_ts*)"; exit 2; fi
  if [[ $DB != eot_main && $DB != eot_ts* ]]; then echo "!! clone names must start with eot_ts"; exit 2; fi
}
odoo(){ sudo -u odoo env HOME=/opt/odoo $PY $BIN -c /etc/odoo20.conf -d "$DB" --db-filter="^$DB\$" --addons-path=$AP --workers=0 --max-cron-threads=0 "$@"; }
guard_db
case $CMD in
  clone)
    [[ $DB == eot_main* ]] && { echo "!! clone target cannot be eot_main"; exit 2; }
    step reset; pkill -f "[-]d $DB" 2>/dev/null; sleep 1
    sudo -u postgres dropdb --if-exists --force "$DB"; rm -rf "$FS/$DB"
    DUMP=$(ls -t /var/backups/odoo/eot_main_pre_*.dump | head -1)
    step "restore $DUMP"
    sudo -u postgres createdb -O odoo "$DB" || exit 1
    sudo -u postgres pg_restore -d "$DB" --no-owner --role=odoo -j 4 "$DUMP" 2>&1 | grep -v '^$' | tail -3
    cp -a "$FS/eot_main" "$FS/$DB"; chown -R odoo:odoo "$FS/$DB"
    step done; sudo -u postgres psql -d "$DB" -Atc "select 'websites='||count(*) from website" ;;
  install|upgrade)
    MODS=${3:?modules}; FLAG=-i; [[ $CMD == upgrade ]] && FLAG=-u
    step "$CMD $MODS"
    odoo $FLAG "$MODS" --stop-after-init --no-http > "/tmp/ts_${CMD}_$DB.log" 2>&1; rc=$?
    grep -E " (ERROR|CRITICAL) |Traceback|ParseError|ValidationError" "/tmp/ts_${CMD}_$DB.log" | grep -v theme_paptic | head -20
    grep -E "Modules loaded|modules loaded" "/tmp/ts_${CMD}_$DB.log" | tail -1
    step "rc=$rc"; exit $rc ;;
  serve)
    PORT=${3:-8071}; pkill -f "[-]d $DB " 2>/dev/null; sleep 1
    sudo -u odoo setsid nohup $PY $BIN -c /etc/odoo20.conf -d "$DB" --db-filter="^$DB\$" --addons-path=$AP --http-port=$PORT --gevent-port=$((PORT+1000)) --workers=0 --max-cron-threads=0 --no-database-list > "/tmp/ts_serve_$DB.log" 2>&1 &
    for i in $(seq 1 25); do curl -s -o /dev/null -H "Host: www.eot.ir" "http://127.0.0.1:$PORT/web/login" && break; sleep 2; done
    echo "serving $DB on :$PORT" ;;
  stop)
    [[ $DB == eot_main* ]] && { echo "!! never"; exit 2; }
    pkill -f "[-]d $DB " 2>/dev/null; sleep 2
    sudo -u postgres dropdb --if-exists --force "$DB"; rm -rf "$FS/$DB"
    echo "pg: $(sudo -u postgres psql -Atc "select count(*) from pg_database where datname='$DB'") fs: $(ls -d $FS/$DB 2>/dev/null | wc -l) proc: $(pgrep -fc "[-]d $DB ")" ;;
  modules)
    sudo -u postgres psql -d "$DB" -Atc "select name from ir_module_module where state='installed' order by 1" ;;
  *) echo "unknown command $CMD"; exit 2 ;;
esac
