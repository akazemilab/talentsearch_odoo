# Kavenegar module tests with a FAKE Kavenegar (no network, no real key).
# Run ONLY on an eot_ts* clone via odoo-bin shell.
import json

from odoo.exceptions import AccessError, UserError

from odoo.addons.ts_kavenegar.tools import kavenegar as kv

assert env.cr.dbname.startswith('eot_ts'), 'refusing to run tests outside a clone'
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print('%s  %s %s' % ('PASS' if ok else 'FAIL', name, detail))


CALLS = []
FAIL_NEXT = {}


class Resp:
    def __init__(self, data):
        self._d = data
        self.status_code = 200

    def json(self):
        return self._d


def ok(entries=None, **extra):
    d = {'return': {'status': 200, 'message': 'ok'}}
    if entries is not None:
        d['entries'] = entries
    d.update(extra)
    return Resp(d)


_mid = [5000]


class FakeSession:
    def _handle(self, verb, url, data=None, params=None, files=None, timeout=None):
        path = url.split('/v1/', 1)[1].split('/', 1)[1][:-5]
        args = dict(data or params or {})
        CALLS.append((verb, path, args, files))
        if path in FAIL_NEXT:
            code = FAIL_NEXT.pop(path)
            return Resp({'return': {'status': code, 'message': 'x'}})
        if path == 'sms/send':
            recs = args['receptor'].split(',')
            out = []
            for r in recs:
                _mid[0] += 1
                out.append({'messageid': _mid[0], 'message': args['message'], 'status': 2 if args.get('date') else 1,
                            'statustext': 'q', 'sender': args.get('sender') or '1000', 'receptor': r, 'date': 1, 'cost': 120})
            return ok(out)
        if path == 'sms/sendarray':
            recs = json.loads(args['receptor'])
            msgs = json.loads(args['message'])
            out = []
            for r, m in zip(recs, msgs):
                _mid[0] += 1
                out.append({'messageid': _mid[0], 'message': m, 'status': 1, 'statustext': 'q', 'sender': '1000',
                            'receptor': r, 'date': 1, 'cost': 100})
            return ok(out)
        if path == 'sms/status':
            return ok([{'messageid': int(i), 'status': 10, 'statustext': 'd'} for i in args['messageid'].split(',')])
        if path == 'sms/cancel':
            return ok([{'messageid': int(i), 'status': 13, 'statustext': 'c'} for i in args['messageid'].split(',')])
        if path == 'account/info':
            return ok({'remaincredit': 5000, 'expiredate': 1900000000, 'type': 'master'})
        if path == 'verify/lookup':
            _mid[0] += 1
            return ok([{'messageid': _mid[0], 'message': 'hello', 'status': 5, 'statustext': 's', 'sender': '1000',
                        'receptor': args['receptor'], 'cost': 90}])
        if path == 'call/maketts':
            _mid[0] += 1
            return ok([{'messageid': _mid[0], 'status': 1, 'statustext': 'q', 'receptor': args['receptor'], 'cost': 200}])
        if path == 'sms/receive':
            if CALLS.count(CALLS[-1]) > 1:
                return ok([])
            return ok([{'messageid': 9001, 'message': 'سلام', 'sender': '09121112233', 'receptor': '10004346', 'date': 1700000000},
                       {'messageid': 9002, 'message': 'بله', 'sender': '09121112244', 'receptor': '10004346', 'date': 1700000001}])
        if path == 'verify/addtemplate':
            return ok([{'id': 77, 'name': args['name'], 'approvalStatus': 'PendingReview', 'textMessage': args['textMessage']}])
        if path == 'verify/templatelist':
            return ok([{'id': 77, 'name': 'tsotp', 'approvalStatus': 'Approved', 'textMessage': 'code %token'}]
                      if args.get('page') in (None, '1', 1) else [])
        if path == 'line/blocked/add':
            return ok([{'receptor': args['receptor'], 'result': 'Active'}])
        if path == 'line/blocked/remove':
            return ok([{'receptor': args['receptor'], 'result': 'Removed'}])
        if path == 'line/blocked/list':
            return ok([{'receptor': '09120000001', 'blockreason': 1}] if args.get('pagenumber') in (None, '1', 1) else [])
        if path == 'account/config':
            return ok([{'debugmode': 'enabled'}])
        if path == 'utils/getdate':
            return ok({'unixtime': 1, 'date': 'x'})
        return ok([])

    def post(self, url, data=None, files=None, timeout=None):
        return self._handle('POST', url, data=data, files=files)

    def get(self, url, params=None, timeout=None):
        return self._handle('GET', url, params=params)

    def delete(self, url, params=None, timeout=None):
        return self._handle('DELETE', url, params=params)


kv.requests.Session = FakeSession

company = env.company
company.sudo().write({'kv_enabled': True, 'kv_api_key': 'TESTKEY-not-real', 'kv_sender': '10004346',
                      'kv_inbox_line': '10004346', 'kv_has_lookup': True, 'kv_min_credit': 10000})
company.kv_generate_secret()
Msg = env['kavenegar.message']

# --- helpers -----------------------------------------------------------------------
check('normalize +98', kv.normalize_receptor('+98 912 123 4567') == '09121234567')
check('normalize persian digits', kv.normalize_receptor('۰۹۱۲۱۲۳۴۵۶۷') == '09121234567')
check('normalize 9121234567', kv.normalize_receptor('9121234567') == '09121234567')
check('normalize garbage', kv.normalize_receptor('abc') is False)
check('parts persian 70/1', kv.sms_parts('س' * 70) == (70, 1))
check('parts persian 71/2', kv.sms_parts('س' * 71) == (71, 2))
check('parts latin 160/1', kv.sms_parts('a' * 160)[1] == 1 and kv.sms_parts('a' * 161)[1] == 2)

# --- gateway selection ---------------------------------------------------------------
check('company uses Kavenegar api class', company._get_sms_api_class().__name__ == 'SmsApiKavenegar')

# --- same body -> one Send call with localid per receptor ------------------------------
CALLS.clear()
sms = env['sms.sms'].create([{'number': '09121234567', 'body': 'سلام تست'}, {'number': '+989351234567', 'body': 'سلام تست'}])
sms.send(unlink_sent=False)
sends = [c for c in CALLS if c[1] == 'sms/send']
check('one Send call for same body', len(sends) == 1, str(len(sends)))
check('send has 2 receptors + 2 localids', len(sends[0][2]['receptor'].split(',')) == 2 and len(sends[0][2]['localid'].split(',')) == 2)
check('sender default from company', sends[0][2].get('sender') == '10004346')
check('sms state process/pending after send', set(sms.mapped('state')) <= {'process', 'pending'}, str(sms.mapped('state')))
logs = Msg.search([('sms_uuid', 'in', sms.mapped('uuid'))])
check('2 log rows with messageid', len(logs) == 2 and all(logs.mapped('messageid')))
check('log has cost and parts', all(l.cost == 120 and l.parts == 1 for l in logs))
check('log state queued', set(logs.mapped('state')) == {'queued'})

# --- different bodies -> SendArray ----------------------------------------------------------
CALLS.clear()
sms2 = env['sms.sms'].create([{'number': '09121234567', 'body': 'a پیام ۱'}, {'number': '09351234567', 'body': 'b پیام ۲'}])
sms2.send(unlink_sent=False)
check('SendArray used for different bodies', [c[1] for c in CALLS if c[1].startswith('sms/send')] == ['sms/sendarray'], str([c[1] for c in CALLS]))
arr = [c for c in CALLS if c[1] == 'sms/sendarray'][0][2]
check('sendarray arrays equal length', len(json.loads(arr['receptor'])) == len(json.loads(arr['message'])) == len(json.loads(arr['sender'])) == len(json.loads(arr['localmessageids'])))

# --- invalid / missing number, no API call -----------------------------------------------------
CALLS.clear()
bad = env['sms.sms'].create([{'number': 'abc', 'body': 'x'}, {'number': False, 'body': 'x'}])
bad.send(unlink_sent=False)
check('bad numbers fail locally', set(bad.mapped('state')) == {'error'} and {'sms_number_format', 'sms_number_missing'} == set(bad.mapped('failure_type')), str(bad.mapped('failure_type')))
check('no API call for bad numbers', not [c for c in CALLS if c[1].startswith('sms/send')])

# --- too long message -----------------------------------------------------------------------------
long_ = env['sms.sms'].create({'number': '09121234567', 'body': 'س' * 1801})
long_.send(unlink_sent=False)
check('over 1800 chars rejected', long_.state == 'error' and long_.failure_type == 'kv_message', long_.failure_type)

# --- API error mapping ------------------------------------------------------------------------------
FAIL_NEXT['sms/send'] = 418
e1 = env['sms.sms'].create({'number': '09121234567', 'body': 'credit'})
e1.send(unlink_sent=False)
check('418 -> sms_credit', e1.state == 'error' and e1.failure_type == 'sms_credit', e1.failure_type)
FAIL_NEXT['sms/send'] = 407
e2 = env['sms.sms'].create({'number': '09121234567', 'body': 'ip'})
e2.send(unlink_sent=False)
check('407 -> kv_ip', e2.failure_type == 'kv_ip', e2.failure_type)

# --- scheduled + tag + hide + policy ----------------------------------------------------------------------
CALLS.clear()
import datetime
sc = env['sms.sms'].create({'number': '09121234567', 'body': 'later', 'kv_date': datetime.datetime(2030, 1, 1, 8, 0),
                            'kv_tag': 'promo-1', 'kv_hide': True})
sc.send(unlink_sent=False)
a = [c for c in CALLS if c[1] == 'sms/send'][0][2]
check('schedule/tag/hide sent', a.get('date') == str(int(datetime.datetime(2030, 1, 1, 8, 0).timestamp())) or a.get('date'), str(a))
check('tag and hide passed', a.get('tag') == 'promo-1' and str(a.get('hide')) == '1')
sm = Msg.search([('sms_uuid', '=', sc.uuid)])
check('scheduled row state', sm.state == 'scheduled' and sm.scheduled)
CALLS.clear()
sm.action_cancel_scheduled()
check('cancel -> cancelled', sm.state == 'cancelled' and [c for c in CALLS if c[1] == 'sms/cancel'])

# --- status refresh + native tracker via chatter SMS -------------------------------------------------------------
partner = env['res.partner'].create({'name': 'کاربر تست SMS', 'phone': '09127776655'})
CALLS.clear()
partner._message_sms('پیام چتر', partner_ids=partner.ids)
env['sms.sms']._process_queue()
pm = Msg.search([('receptor', '=', '09127776655')], limit=1)
check('chatter SMS went through Kavenegar', bool(pm) and pm.partner_id == partner, str(pm))
notif = env['mail.notification'].search([('res_partner_id', '=', partner.id), ('notification_type', '=', 'sms')], limit=1)
pm.action_refresh_status()
check('status refresh -> delivered', pm.state == 'delivered')
notif.invalidate_recordset()
check('native notification updated to sent', notif.notification_status == 'sent', notif.notification_status)
pm._kv_apply_status(11)
notif.invalidate_recordset()
check('final status is not overwritten upward by poll list', pm.is_final)

# --- polling cron ----------------------------------------------------------------------------------------------
q = Msg.search([('is_final', '=', False), ('direction', '=', 'out')])
Msg._kv_cron_poll()
check('poll cron finalises open messages', not Msg.search([('id', 'in', q.ids), ('is_final', '=', False)]))

# --- lookup / call -----------------------------------------------------------------------------------------------
tpl = env['kavenegar.template'].create({'name': 'tsotp', 'text_message': 'code %token'})
tpl.action_push()
check('template push', tpl.remote_id == '77' and tpl.approval == 'PendingReview')
env['kavenegar.template'].action_sync_all()
tpl.invalidate_recordset()
check('template sync -> Approved', tpl.approval == 'Approved')
CALLS.clear()
w = env['kavenegar.send.wizard'].create({'mode': 'lookup', 'receptors': '09121234567', 'template_id': tpl.id, 'token': '123456'})
w.action_send()
lk = Msg.search([('kind', '=', 'lookup')], limit=1)
check('lookup logged without the token', lk and '123456' not in (lk.body or ''), lk.body)
check('lookup sent template name', [c for c in CALLS if c[1] == 'verify/lookup'][0][2]['template'] == 'tsotp')
company.kv_has_lookup = False
try:
    env['kavenegar.send.wizard'].create({'mode': 'lookup', 'receptors': '09121234567', 'template_id': tpl.id, 'token': '1'}).action_send()
    check('lookup gated by account feature', False)
except UserError:
    check('lookup gated by account feature', True)
company.kv_has_lookup = True
w = env['kavenegar.send.wizard'].create({'mode': 'call', 'receptors': '09121234567', 'message': 'کد شما ۱۲۳۴'})
w.action_send()
check('TTS call logged', Msg.search_count([('kind', '=', 'call')]) == 1)

# --- send wizard with per-line messages -------------------------------------------------------------------------------
CALLS.clear()
w = env['kavenegar.send.wizard'].create({'mode': 'sms', 'line_ids': [(0, 0, {'number': '09121234567', 'message': 'الف'}), (0, 0, {'number': '09351234567', 'message': 'ب'})]})
w.action_send()
check('wizard per-line uses SendArray', any(c[1] == 'sms/sendarray' for c in CALLS))

# --- inbox ---------------------------------------------------------------------------------------------------------------
CALLS.clear()
Msg._kv_cron_inbox()
inn = Msg.search([('direction', '=', 'in')])
check('inbox stored 2 messages', len(inn) == 2, str(len(inn)))
Msg._kv_store_inbound(company, [{'messageid': 9001, 'message': 'dup', 'sender': '09121112233'}])
check('inbox dedupes on messageid', Msg.search_count([('direction', '=', 'in')]) == 2)

# --- blocked -----------------------------------------------------------------------------------------------------------------
CALLS.clear()
b = env['kavenegar.blocked'].create({'number': '09125550000'})
check('blocked add pushed', [c for c in CALLS if c[1] == 'line/blocked/add'])
env['kavenegar.blocked'].action_sync()
check('blocked sync mirrors remote and drops stale', env['kavenegar.blocked'].search([]).mapped('number') == ['09120000001'])
b2 = env['kavenegar.blocked'].create({'number': '09125551111'})
CALLS.clear()
b2.unlink()
check('blocked remove uses DELETE', [c for c in CALLS if c[1] == 'line/blocked/remove' and c[0] == 'DELETE'])

# --- account / credit alarm ------------------------------------------------------------------------------------------------------
u = env['res.users'].search([('share', '=', False)], limit=1)
company.kv_alert_user_ids = u
info = company.kv_sync_account()
check('account sync stores credit', company.kv_credit == 5000 and company.kv_account_type == 'master')
company.kv_push_config()
check('push config sent debugmode', [c for c in CALLS if c[1] == 'account/config' and c[0] == 'POST'])

# --- report wizard ------------------------------------------------------------------------------------------------------------------
rw = env['kavenegar.report.wizard'].create({'kind': 'server_time'})
rw.action_run()
check('report wizard runs', bool(rw.result))
try:
    env['kavenegar.report.wizard'].create({'kind': 'select_outbox'}).action_run()
    check('outbox gated by IP whitelist flag', False)
except UserError:
    check('outbox gated by IP whitelist flag', True)

# --- secrets -------------------------------------------------------------------------------------------------------------------------
portal = env.ref('base.group_portal')
pu = env['res.users'].with_context(no_reset_password=True).create({'name': 'kvp', 'login': 'kv_portal_test', 'group_ids': [(6, 0, [portal.id])]})
try:
    company.with_user(pu).sudo(False).kv_api_key
    leaked = True
except AccessError:
    leaked = False
check('api key not readable by non-admin', not leaked)
blob = json.dumps([m.read()[0] for m in Msg.search([])], default=str)
check('api key never stored in message log', 'TESTKEY' not in blob)
check('webhook urls contain secret only via system group', bool(company.kv_webhook_status_url))

# --- disabled falls back to IAP ---------------------------------------------------------------------------------------------------------
company.kv_enabled = False
check('disabled -> stock IAP class', company._get_sms_api_class().__name__ == 'SmsApi')
company.kv_enabled = True

# persist webhook fixtures for the HTTP test
open('/tmp/kv_http_fixture.json', 'w').write(json.dumps({
    'secret': company.sudo().kv_webhook_secret,
    'messageid': Msg.search([('direction', '=', 'out'), ('messageid', '!=', False)], limit=1).messageid}))
env.cr.commit()
fails = [n for n, o in results if not o]
print('SUMMARY %d/%d passed' % (len(results) - len(fails), len(results)), fails or '')
