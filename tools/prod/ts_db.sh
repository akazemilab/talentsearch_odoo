#!/bin/bash
# ts_db.sh - Talent Search database operations on eot-odoo-prod (run as root).
#   clone DB            restore the newest eot_main dump + filestore into DB
#   install DB MODS     -i MODS on DB (comma list), stop after init
#   upgrade DB MODS     -u MODS on DB
#   serve DB [PORT]     serve DB detached (default :8071, workers=0, no cron); refuses a port held by
#                       another clone and refuses when prod has < 1.5 GB RAM available
#   halt DB             stop the clone's server only (database kept)
#   reload DB MODS [PORT]  halt -> upgrade MODS -> serve again (fast re-test on the same clone)
#   stop DB  (= drop)   stop serving + DROP the DB + filestore, with proof
# Parallel slots: TS_CODE may be /opt/odoo/talentsearch_stage or talentsearch_stage_s1/_s2 (one
# stage dir per rehearsal slot); /opt/odoo/talentsearch is the LIVE code (read-only: baselines).
#   modules DB          installed module names, one per line
#   errors DB [N]       last N tracebacks of the clone server, condensed (exception + template element + our file)
# Safety: every command refuses any DB name starting with eot_main unless
# TS_LIVE=1 is set (only `ts ship` sets it, after a passing rehearsal).
set -uo pipefail
FS=/opt/odoo/.local/share/Odoo/filestore
PY=/opt/odoo/venv/bin/python3; BIN=/opt/odoo/odoo/odoo-bin
CODE=${TS_CODE:-/opt/odoo/talentsearch_stage}   # TS_CODE=/opt/odoo/talentsearch serves a clone on the LIVE code (read-only use: baselines)
[[ $CODE =~ ^/opt/odoo/talentsearch(_stage(_s[12])?)?$ ]] || { echo "!! bad TS_CODE $CODE"; exit 2; }
AP=$CODE/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons
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
  apply)
    INS=${3:-}; UPG=${4:-}; ARGS=()
    [ -n "$INS" ] && ARGS+=(-i "$INS"); [ -n "$UPG" ] && ARGS+=(-u "$UPG")
    step "apply install=[$INS] upgrade=[$UPG]"
    odoo "${ARGS[@]}" --stop-after-init --no-http > "/tmp/ts_apply_$DB.log" 2>&1; rc=$?
    grep -E " (ERROR|CRITICAL) |Traceback|ParseError" "/tmp/ts_apply_$DB.log" | grep -v theme_paptic | head -20
    grep -E "Talent Search instruments loaded" "/tmp/ts_apply_$DB.log" | tail -1 | cut -c1-240
    step "rc=$rc"; exit $rc ;;
  serve)
    PORT=${3:-8071}; pkill -f "[-]d $DB " 2>/dev/null; sleep 1
    holder=$(ss -ltnp "sport = :$PORT" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
    if [ -n "$holder" ]; then echo "!! port $PORT is held by: $(tr '\0' ' ' < /proc/$holder/cmdline | grep -o -- '-d [^ ]*')"; exit 3; fi
    avail=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    [ "$avail" -lt 1500 ] && { echo "!! only ${avail} MB RAM available on prod; stop a clone first (ts db halt|stop)"; exit 3; }
    sudo -u odoo setsid nohup $PY $BIN -c /etc/odoo20.conf -d "$DB" --db-filter="^$DB\$" --addons-path=$AP --http-port=$PORT --gevent-port=$((PORT+1000)) --workers=0 --max-cron-threads=0 --no-database-list > "/tmp/ts_serve_$DB.log" 2>&1 &
    for i in $(seq 1 25); do curl -s -o /dev/null -H "Host: www.eot.ir" "http://127.0.0.1:$PORT/web/login" && break; sleep 2; done
    echo "serving $DB on :$PORT (code $CODE)" ;;
  halt)
    pkill -f "[-]d $DB " 2>/dev/null; sleep 2
    echo "halted $DB (database kept); procs left: $(pgrep -fc "[-]d $DB ")" ;;
  reload)
    MODS=${3:?modules}; PORT=${4:-8071}
    pkill -f "[-]d $DB " 2>/dev/null; sleep 2
    step "reload: upgrade $MODS"
    odoo -u "$MODS" --stop-after-init --no-http > "/tmp/ts_reload_$DB.log" 2>&1; rc=$?
    grep -E " (ERROR|CRITICAL) |Traceback|ParseError" "/tmp/ts_reload_$DB.log" | grep -v theme_paptic | head -20
    [ $rc -ne 0 ] && { step "rc=$rc"; exit $rc; }
    exec bash "$0" serve "$DB" "$PORT" ;;
  stop|drop)
    [[ $DB == eot_main* ]] && { echo "!! never"; exit 2; }
    pkill -f "[-]d $DB " 2>/dev/null; sleep 2
    sudo -u postgres dropdb --if-exists --force "$DB"; rm -rf "$FS/$DB"
    echo "dropped $DB - pg: $(sudo -u postgres psql -Atc "select count(*) from pg_database where datname='$DB'") fs: $(ls -d $FS/$DB 2>/dev/null | wc -l) proc: $(pgrep -fc "[-]d $DB ")" ;;
  errors)
    # last N server errors of the clone, condensed: the exception line + the QWeb element / file line
    python3 - "/tmp/ts_serve_$DB.log" "${3:-3}" <<'PY'
import re, sys
s = open(sys.argv[1], encoding='utf-8', errors='replace').read() if __import__('os').path.exists(sys.argv[1]) else ''
blocks = re.split(r'\n(?=\S.*Traceback \(most recent call last\))|\n(?=Traceback \(most recent call last\))', s)
tb = [b for b in blocks if 'Traceback' in b]
print(f'{len(tb)} traceback(s) in {sys.argv[1]}')
for b in tb[-int(sys.argv[2]):]:
    lines = b.splitlines()
    exc = [l for l in lines if re.match(r'^[\w.]+(Error|Exception)\b', l.strip())]
    where = [l.strip() for l in lines if 'Element:' in l or 'Template:' in l or l.strip().startswith('File "/opt/odoo/talentsearch')]
    print('--', (exc[-1].strip() if exc else lines[-1].strip())[:240])
    for w in where[-3:]:
        print('   ', w[:200])
PY
    ;;
  modules)
    sudo -u postgres psql -d "$DB" -Atc "select name from ir_module_module where state='installed' order by 1" ;;
  *) echo "unknown command $CMD"; exit 2 ;;
esac
