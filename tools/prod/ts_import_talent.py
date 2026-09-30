# Historical import of the interactive talent inventory (FormAfzar export) -> contacts + attempts.
# Run through the Odoo shell (stdin), parameters from the environment; prints COUNTS ONLY:
#   TS_IMPORT_XLSX=/path/export.xlsx [TS_IMPORT_LIVE=1] [TS_IMPORT_DRY=0] [TS_IMPORT_BATCH=label]
#   sudo -u odoo ... odoo-bin shell -c /etc/odoo20.conf -d eot_tsN ... --no-http < ts_import_talent.py
# Default is a dry run (everything is executed, then rolled back). eot_main needs TS_IMPORT_LIVE=1
# AND TS_IMPORT_DRY=0. No user account, no message of any kind, no consent claimed, released=False.
import hashlib
import json
import os
from collections import Counter

import openpyxl

from odoo.addons.ts_talent.models import engine_matrix as EM
from odoo.addons.ts_talent.models import importer as IM
from odoo.addons.ts_talent.models.text import norm_label

XLSX = os.environ['TS_IMPORT_XLSX']
LIVE = os.environ.get('TS_IMPORT_LIVE') == '1'
DRY = os.environ.get('TS_IMPORT_DRY', '1') != '0'
BATCH = os.environ.get('TS_IMPORT_BATCH') or 'formafzar-0ekrq'
SRC = 'formafzar:0ekrq:'
INSTITUTE = 'مؤسسه تعاملی هیجان اندیشه'
PREFIX = 'ts-import:'

db = env.cr.dbname
assert db.startswith('eot_ts') or (db == 'eot_main' and LIVE and not DRY), 'refusing: clones only unless --live and not dry'
if db == 'eot_main':
    assert LIVE and not DRY

inst = env['ts.instrument'].search([('code', '=', 'TALENT-INV-15')])
assert len(inst) == 1 and inst.state == 'published', 'talent instrument missing or unpublished'
version = inst.current_version_id
assert version.mode == 'matrix' and version.contract_version == '1.0'
items = version.item_ids.filtered(lambda i: not i.disabled).sorted(lambda i: (i.sequence, i.source_question_id, i.id))
assert len(items) == 15

ws_sheet = openpyxl.load_workbook(XLSX, read_only=True).worksheets[0]
rows = list(ws_sheet.iter_rows(values_only=True))
problems = IM.check_header(rows[0], [i.text for i in items])
assert not problems, 'sheet is not the expected export: %s' % problems
records = [IM.parse_row(r) for r in rows[1:] if any(c not in (None, '') for c in r)]

# ---- institute partner + education workspace (created once, never duplicated)
Partner = env['res.partner']
inst_partner = Partner.with_context(active_test=False).search([('name', '=', INSTITUTE)])
assert len(inst_partner) <= 1, 'more than one institute partner: stop'
counts = Counter()
if not inst_partner:
    inst_partner = Partner.create({'name': INSTITUTE, 'is_company': True})
    inst_partner.write({'is_company': True})  # Odoo 20 recomputes it on create; the explicit write sticks
    counts['institute_created'] = 1
workspace = env['ts.workspace'].search([('partner_id', '=', inst_partner.id), ('purpose', '=', 'education')])
assert len(workspace) <= 1, 'more than one education workspace: stop'
if not workspace:
    workspace = env['ts.workspace'].create({'name': INSTITUTE, 'purpose': 'education', 'partner_id': inst_partner.id})
    counts['workspace_created'] = 1

# ---- existing state (idempotency)
Attempt = env['ts.attempt']
have_refs = set(Attempt.search([('source', '=', 'import')]).mapped('source_ref'))
by_ref = {p.ref: p for p in Partner.search([('ref', '=like', PREFIX + '%')])}
by_email = {}
for p in by_ref.values():
    if p.email:
        by_email.setdefault(p.email.lower(), p)


def person_for(rec):
    """Same mobile -> same contact; no mobile -> same e-mail; otherwise a contact of its own."""
    if rec['phone']:
        key = 'p:' + rec['phone']
    elif rec['email'] and rec['email'] in by_email:
        return by_email[rec['email']], False
    elif rec['email']:
        key = 'e:' + rec['email']
    else:
        key = 'row:' + rec['src_id']
    ref = PREFIX + hashlib.sha1(key.encode()).hexdigest()[:16]
    if ref in by_ref:
        return by_ref[ref], False
    name = rec['name'] or 'شرکت‌کنندهٔ بدون نام (ردیف %s)' % rec['src_id']
    vals = {'name': name, 'ref': ref}
    if rec['email']:
        vals['email'] = rec['email']
    if rec['phone']:
        vals['phone'] = rec['phone']
    p = Partner.create(vals)
    by_ref[ref] = p
    if rec['email']:
        by_email.setdefault(rec['email'], p)
    return p, True


mismatch = 0
created_attempts = env['ts.attempt']
for rec in records:
    counts['rows'] += 1
    for _blk, why in rec['skipped']:
        counts['block_skipped_' + why] += 1
    if not rec['fields']:
        counts['row_skipped_no_valid_field'] += 1
        continue
    src_ref = SRC + rec['src_id']
    if src_ref in have_refs:
        counts['row_skipped_exists'] += 1
        continue
    if rec['phone_given'] and not rec['phone']:
        counts['phone_unparsable'] += 1
    if rec['email_given'] and not rec['email']:
        counts['email_unparsable'] += 1
    if rec['created'] is None:
        counts['date_unparsable'] += 1
    partner, made = person_for(rec)
    counts['contacts_created' if made else 'contacts_merged'] += 1
    attempt = Attempt.create({
        'person_id': partner.id, 'instrument_id': inst.id, 'version_id': version.id, 'source': 'import',
        'source_ref': src_ref, 'import_batch': BATCH, 'workspace_id': workspace.id, 'state': 'done',
        'consent_service': False, 'consent_research': False, 'consent_version': 'IMPORT-FORMAFZAR',
        'released': False, 'started_at': rec['created'], 'submitted_at': rec['created'],
    })
    for seq, f in enumerate(rec['fields'], 1):
        straight = len(set(f['answers'])) == 1
        fld = env['ts.attempt.field'].create({
            'attempt_id': attempt.id, 'sequence': seq, 'label': f['label'], 'label_norm': norm_label(f['label']),
            'state': 'done', 'started_at': rec['created'], 'finished_at': rec['created'], 'seconds': 0,
            'flag_straight': straight, 'flag_fast': False, 'source_ref': '%s:%s' % (src_ref, f['block'])})
        for it, val in zip(items, f['answers']):
            env['ts.attempt.cell'].create({'field_id': fld.id, 'attempt_id': attempt.id, 'item_id': it.id,
                                           'value': val, 'answered_at': rec['created']})
        counts['fields_imported'] += 1
        counts['fields_straight'] += 1 if straight else 0
    result = EM.score_matrix(attempt.ts_engine_input())
    profile = dict(result, interpretation=EM.interpret(result, gap=version.noise_gap))
    attempt.write({'engine_version': result['engine'], 'input_hash': result['input_hash'],
                   'output_hash': result['output_hash'], 'profile_json': json.dumps(profile, ensure_ascii=False)})
    for f, rf in zip(rec['fields'], result['fields']):
        ok, n = IM.derived_matches(f, rf)
        counts['derived_compared'] += n and 1
        if not ok:
            mismatch += 1
    created_attempts |= attempt
    counts['attempts_created'] += 1

bad_rescore = sum(1 for a in created_attempts if not a.rescore_matches())
counts['rescore_mismatch'] = bad_rescore
counts['derived_mismatch'] = mismatch
leaks = Attempt.search_count([('source', '=', 'import'), '|', ('user_id', '!=', False), ('released', '=', True)])
counts['imported_with_user_or_released'] = leaks
assert mismatch == 0 and bad_rescore == 0 and leaks == 0, 'validation failed: %s' % dict(counts)

print('DB', db, 'DRY' if DRY else 'WRITE', 'LIVE' if LIVE else 'clone')
for k in sorted(counts):
    print('  %-34s %s' % (k, counts[k]))
if DRY:
    env.cr.rollback()
    print('ROLLED BACK (dry run)')
else:
    env.cr.commit()
    print('COMMITTED')
