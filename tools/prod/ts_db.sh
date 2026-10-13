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
# A clone runs no scheduled action: its own server has no cron thread, and the LIVE server (no dbfilter) would otherwise
# run its crons on every clone database with the live code, against a schema the release under test may have changed
# (rehearsal eot_ts1004: the live import-job cron took a queued job of a clone and failed on a removed column). Every
# cron of a clone is switched off after the restore and again before each serve (an upgrade may switch some back on).
# Suites call the cron methods directly. Recommended ops change for the owner: pin the live server to eot_main.
crons_off(){ [[ $DB == eot_ts* ]] || return 0; sudo -u postgres psql -d "$DB" -Atc "WITH c AS (UPDATE ir_cron SET active = false WHERE active RETURNING 1) SELECT 'crons off: '||count(*) FROM c" 2>&1 | tail -1; }
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
    # clones never send real email (eot_main has the Liara server since 2026-10-12): servers off, queue dropped
    sudo -u postgres psql -d "$DB" -Atc "UPDATE ir_mail_server SET active = false; DELETE FROM mail_mail WHERE state IN ('outgoing', 'exception'); SELECT 'mail servers off: '||count(*) FROM ir_mail_server" 2>&1 | tail -1
    # clones never send real SMS either (onb3 risk review): the dump carries the live Kavenegar key and the live server
    # runs its crons on every clone. Kavenegar off with no key, its address and Odoo's SMS/IAP endpoints on a closed local
    # port, IAP SMS tokens void, the SMS queue dropped. Suites that need a gateway start a local fake (ts_flowlib.py).
    # The code guard (ts_kavenegar/tools/guard.py) is the second layer; ts_rehearse.sh checks this before any suite.
    sudo -u postgres psql -d "$DB" -v ON_ERROR_STOP=1 -At > /tmp/ts_clone_sms_$DB.log 2>&1 <<'SQL'
UPDATE res_company SET kv_enabled = false, kv_api_key = NULL;
DELETE FROM ir_config_parameter WHERE key IN ('ts_kavenegar.api_base', 'sms.endpoint', 'iap.endpoint', 'ts_kavenegar.live_db');
INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date) VALUES
  ('ts_kavenegar.api_base', 'http://127.0.0.1:9/v1/%s/%s.json', 1, 1, now(), now()),
  ('sms.endpoint', 'http://127.0.0.1:9', 1, 1, now(), now()),
  ('iap.endpoint', 'http://127.0.0.1:9', 1, 1, now(), now());
UPDATE iap_account a SET account_token = 'clone-void-' || a.id FROM iap_service s WHERE s.id = a.service_id AND s.technical_name = 'sms';
DELETE FROM sms_sms WHERE state IN ('outgoing', 'process');
SELECT 'sms: kavenegar on '||(SELECT count(*) FROM res_company WHERE kv_enabled OR coalesce(kv_api_key, '') <> '')||', api_base '||(SELECT value FROM ir_config_parameter WHERE key = 'ts_kavenegar.api_base');
SQL
    rc_sms=$?; tail -1 /tmp/ts_clone_sms_$DB.log
    [ $rc_sms -ne 0 ] && { echo "!! could not switch the clone's SMS off"; cat /tmp/ts_clone_sms_$DB.log | head -5; exit 1; }
    crons_off
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
    if [ $rc -ne 0 ]; then echo "--- exception lines:"; grep -E "^[A-Za-z_.]+(Error|Exception|Warning)[:(]" "/tmp/ts_apply_$DB.log" | head -8 | cut -c1-400; echo "--- last traceback lines:"; awk '/Traceback/{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' "/tmp/ts_apply_$DB.log" | tail -25 | cut -c1-300; fi
    step "rc=$rc"; exit $rc ;;
  serve)
    PORT=${3:-8071}; pkill -f "[-]d $DB " 2>/dev/null; sleep 1
    holder=$(ss -ltnp "sport = :$PORT" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
    if [ -n "$holder" ]; then echo "!! port $PORT is held by: $(tr '\0' ' ' < /proc/$holder/cmdline | grep -o -- '-d [^ ]*')"; exit 3; fi
    avail=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    [ "$avail" -lt 1500 ] && { echo "!! only ${avail} MB RAM available on prod; stop a clone first (ts db halt|stop)"; exit 3; }
    crons_off >/dev/null
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
