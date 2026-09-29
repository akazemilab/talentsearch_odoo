#!/usr/bin/env python3
"""Read-only extraction of the Talent Search instrument source from the old
sepehrtherapy.ir Odoo (db 'eot', x_psy_* models) into one JSON file.

Only search_read / fields_get are called. Output is cross-validated against the
counts of the CSV exports the owner attached (36/33/183/131/393/1340) and
refuses to write on any mismatch.

    python3 extract_psy_source.py OUT.json
"""
import json, os, sys, xmlrpc.client
from collections import Counter

ENV = '/root/hesabfa-odoo-sync/.env'
cfg = {}
for line in open(ENV):
    if '=' in line and not line.lstrip().startswith('#'):
        k, v = line.strip().split('=', 1)
        cfg[k] = v.strip().strip('"').strip("'")
URL, DB, USER = cfg['ODOO_URL'], cfg['ODOO_DB'], cfg['ODOO_USERNAME']
PWD = cfg.get('ODOO_API_KEY') or cfg.get('ODOO_PASSWORD')
common = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(DB, USER, PWD, {})
assert uid, 'authentication failed'
obj = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/object', allow_none=True)


def call(model, method, *args, **kw):
    return obj.execute_kw(DB, uid, PWD, model, method, list(args), kw)


def read_all(model, domain=None, skip=('binary', 'image')):
    fields = call(model, 'fields_get', attributes=['type'])
    names = [f for f, d in fields.items() if d['type'] not in skip and f not in ('__last_update',)]
    ctx = {'active_test': False, 'lang': 'fa_IR'}
    return call(model, 'search_read', domain or [], fields=names, context=ctx, order='id')


MODELS = ['x_psy_assessment', 'x_psy_scoring_contract', 'x_psy_factor', 'x_psy_factor_scoring_rule',
          'x_psy_factor_threshold_rule', 'x_psy_assessment_item']
data = {m: read_all(m) for m in MODELS}
q_ids = sorted({r['x_question_id'][0] for r in data['x_psy_assessment_item'] if r.get('x_question_id')})
data['survey.question'] = call('survey.question', 'read', q_ids,
                               fields=['id', 'title', 'survey_id', 'question_type', 'scale_min', 'scale_max',
                                       'scale_min_label', 'scale_mid_label', 'scale_max_label', 'sequence',
                                       'constr_mandatory'], context={'lang': 'fa_IR'})
imd = call('ir.model.data', 'search_read', [('model', 'in', MODELS)], fields=['module', 'name', 'model', 'res_id'])
data['xmlids'] = {f"{r['model']}:{r['res_id']}": f"{r['module']}.{r['name']}" for r in imd}
data['_source'] = {'url': URL, 'db': DB, 'extracted_by_uid': uid}

expected = {'x_psy_assessment': 36, 'x_psy_scoring_contract': 33, 'x_psy_factor': 183,
            'x_psy_factor_scoring_rule': 131, 'x_psy_factor_threshold_rule': 393, 'x_psy_assessment_item': 1340}
got = {m: len(data[m]) for m in expected}
inactive = [c for c in data['x_psy_scoring_contract'] if not c.get('x_active')]
print('inactive contracts (not in owner export):', [(c['x_name'], c['x_version']) for c in inactive])
got['x_psy_scoring_contract'] -= len(inactive)
print('counts', got, 'questions', len(data['survey.question']))
bad = {m: (got[m], n) for m, n in expected.items() if got[m] != n}
if bad:
    sys.exit('!! count mismatch vs owner exports: %s' % bad)
print('question types', Counter(q['question_type'] for q in data['survey.question']),
      'scales', Counter((q['scale_min'], q['scale_max']) for q in data['survey.question']))
json.dump(data, open(sys.argv[1], 'w'), ensure_ascii=False, default=str)
print('wrote', sys.argv[1], os.path.getsize(sys.argv[1]), 'bytes')
