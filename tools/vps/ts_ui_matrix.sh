#!/bin/bash
# ts_ui_matrix.sh DB PORT OUTDIR : seed fixture users on a served clone of the slot (via ts_http_pv2_19.py), build the
# route matrix for public / owner / counselor, take shots with ts_shot.py (widths from TS_SHOT_WIDTHS) and copy the
# png files + report.txt to OUTDIR (under /root/share/out, synced to the owner's Mac). Called by `ts shots DB`.
set -u
DB=$1; PORT=$2; OUT=$3; SLOT=${TS_SLOT:-0}
if [ "$SLOT" = 0 ]; then STAGE=/opt/odoo/talentsearch_stage; REPO=/root/talentsearch_odoo
else STAGE=/opt/odoo/talentsearch_stage_s$SLOT; REPO=/root/ts_wt_s$SLOT; fi
echo "=== $(date +%T) seed"
ssh -n eot-odoo-prod "TS_SLOT=$SLOT PYTHONIOENCODING=utf-8 python3 -u $STAGE/tools/prod/ts_http_pv2_19.py $DB $PORT 2>&1 | grep -E '^(FAIL|SUMMARY)'"
scp -q $REPO/tools/vps/ts_ui_seed.py eot-odoo-prod:/tmp/ts_ui_seed.py
ssh -n eot-odoo-prod "cd /tmp && sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell -c /etc/odoo20.conf -d $DB --db-filter='^$DB\$' --addons-path=$STAGE/addons,/opt/odoo/themes,/opt/odoo/enterprise,/opt/odoo/odoo/addons --no-http --log-level=error < /tmp/ts_ui_seed.py 2>&1 | grep -E '^(MATRIX|consent)'; cat /tmp/ui_matrix.json" > /tmp/ui_matrix_out_$DB.txt
head -1 /tmp/ui_matrix_out_$DB.txt
tail -1 /tmp/ui_matrix_out_$DB.txt > /root/ts-jobs/ui_matrix_$DB.json
echo "=== $(date +%T) shots"
rm -rf /root/ts-jobs/shots; mkdir -p /root/ts-jobs/shots
python3 $REPO/tools/vps/ts_shot.py $DB $PORT --matrix /root/ts-jobs/ui_matrix_$DB.json 2>&1 | tee /root/ts-jobs/ui_shot_report_$DB.txt | tail -3
rm -rf "$OUT"; mkdir -p "$OUT"; cp /root/ts-jobs/shots/*.png "$OUT"/ 2>/dev/null; cp /root/ts-jobs/ui_shot_report_$DB.txt "$OUT"/report.txt
echo "=== $(date +%T) done: $(ls "$OUT" | wc -l) files in $OUT"
