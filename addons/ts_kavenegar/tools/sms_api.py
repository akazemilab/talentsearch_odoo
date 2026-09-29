import itertools
import logging

from odoo import _
from odoo.addons.sms.tools.sms_api import SmsApiBase

from .kavenegar import (KavenegarError, normalize_receptor, sms_parts, STATUS_TEXT)

_logger = logging.getLogger(__name__)

FAILURE_TYPES = ('sms_number_format', 'sms_number_missing', 'sms_credit', 'sms_acc', 'sms_server',
                 'kv_ip', 'kv_sender', 'kv_message', 'kv_links', 'kv_charset', 'kv_rate',
                 'kv_test_only', 'kv_service', 'sms_blacklist', 'sms_not_delivered')
CHUNK = 200


class SmsApiKavenegar(SmsApiBase):
    """Sends odoo sms.sms batches through Kavenegar (Send / SendArray)."""
    PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {f: f for f in FAILURE_TYPES}

    def __init__(self, env, account=None):
        super().__init__(env, account=account)
        self._extras = {}

    def _get_sms_api_error_messages(self):
        return {
            'kv_ip': _('The server IP is not allowed in the Kavenegar panel.'),
            'kv_sender': _('The sender line is invalid.'),
            'kv_message': _('The message is empty or too long.'),
            'kv_links': _('Links are restricted on this line.'),
            'kv_charset': _('The text has forbidden characters.'),
            'kv_rate': _('Too many requests, retry later.'),
            'kv_test_only': _('Test messages are only delivered to the account owner number.'),
            'kv_service': _('This service is not enabled on the Kavenegar account.'),
        }

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        company = (self.company or self.env.company).sudo()
        try:
            client = company._kv_client()
        except KavenegarError as e:
            return [self._fail(n['uuid'], e) for m in messages for n in m['numbers']]
        limit = 4000 if company.kv_has_messenger else 1800
        items, results = [], []
        for m in messages:
            body = m.get('content') or ''
            for n in m['numbers']:
                uuid = n['uuid']
                ex = dict(self._extras.get(uuid) or {})
                rec = normalize_receptor(n.get('number'))
                if not n.get('number'):
                    results.append({'uuid': uuid, 'state': 'sms_number_missing',
                                    'failure_reason': _('Missing number')})
                elif not rec:
                    results.append({'uuid': uuid, 'state': 'sms_number_format',
                                    'failure_reason': _('Wrong number format')})
                elif not body.strip() or len(body) > limit:
                    results.append({'uuid': uuid, 'state': 'kv_message',
                                    'failure_reason': _('Message empty or longer than %s characters', limit)})
                else:
                    ex['sender'] = ex.get('sender') or company.kv_sender
                    ex['tag'] = ex.get('tag') or company.kv_default_tag
                    items.append(dict(uuid=uuid, receptor=rec, body=body, ex=ex))

        def key(i):
            e = i['ex']
            return (e.get('date'), e.get('tag') or '', bool(e.get('hide')), e.get('policy'),
                    e.get('mediaid'), e.get('type'))
        items.sort(key=lambda i: str(key(i)))
        for k, grp in itertools.groupby(items, key=key):
            grp = list(grp)
            for start in range(0, len(grp), CHUNK):
                results += self._send_chunk(client, company, k, grp[start:start + CHUNK])
        return results

    def _fail(self, uuid, err):
        return {'uuid': uuid, 'state': err.failure_type, 'failure_reason': err.message}

    def _send_chunk(self, client, company, k, chunk):
        date, tag, hide, policy, mediaid, type_ = k
        uuids = [i['uuid'] for i in chunk]
        bodies = {i['body'] for i in chunk}
        senders = {i['ex'].get('sender') or '' for i in chunk}
        try:
            if len(bodies) == 1 and len(senders) == 1:
                entries = client.send(
                    [i['receptor'] for i in chunk], chunk[0]['body'], sender=senders.pop() or None,
                    date=date, type_=type_, localid=uuids, hide=hide, tag=tag or None,
                    policy=policy, mediaid=mediaid)
            else:
                entries = client.sendarray(
                    [i['receptor'] for i in chunk], [i['ex'].get('sender') or '' for i in chunk],
                    [i['body'] for i in chunk], date=date, types=[type_] * len(chunk) if type_ is not None else None,
                    localids=uuids, hide=hide, tag=tag or None, policy=policy, mediaid=mediaid)
        except KavenegarError as e:
            _logger.info('Kavenegar send failed: %s', e)
            return [self._fail(i['uuid'], e) for i in chunk]
        by_receptor = {}
        for e in entries:
            by_receptor.setdefault(str(e.get('receptor')), []).append(e)
        out = []
        for idx, i in enumerate(chunk):
            e = entries[idx] if len(entries) == len(chunk) else (by_receptor.get(i['receptor']) or [None]).pop(0)
            if not e:
                out.append({'uuid': i['uuid'], 'state': 'sms_server',
                            'failure_reason': _('No answer for this number from Kavenegar')})
                continue
            status = int(e.get('status') or 0)
            chars, parts = sms_parts(i['body'])
            kv = {
                'company_id': company.id, 'direction': 'out', 'kind': 'sms', 'sms_uuid': i['uuid'],
                'messageid': str(e.get('messageid') or ''), 'receptor': i['receptor'],
                'sender': e.get('sender') or i['ex'].get('sender'),
                'body': '***' if i['ex'].get('secret') else i['body'],
                'kv_status': status, 'status_text': e.get('statustext') or STATUS_TEXT.get(status),
                'cost': float(e.get('cost') or 0), 'tag': tag or False, 'characters': chars, 'parts': parts,
                'scheduled': bool(date),
            }
            if status in (6, 11, 14):
                out.append({'uuid': i['uuid'], 'state': 'sms_blacklist' if status == 14 else 'sms_server',
                            'failure_reason': kv['status_text'], 'kv': kv})
            elif status == 13:
                out.append({'uuid': i['uuid'], 'state': 'processing', 'kv': kv})
            elif status in (4, 5, 10):
                out.append({'uuid': i['uuid'], 'state': 'delivered' if status == 10 else 'success', 'kv': kv})
            else:
                out.append({'uuid': i['uuid'], 'state': 'processing', 'kv': kv})
        return out
