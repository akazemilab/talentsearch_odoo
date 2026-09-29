import hmac
import json
import logging

from odoo import http
from odoo.http import request

from ..tools.kavenegar import STATUS_TEXT

_logger = logging.getLogger(__name__)


def _payload():
    """Kavenegar callbacks may come as query string, form or JSON."""
    data = dict(request.httprequest.args.items())
    data.update(request.httprequest.form.items())
    if request.httprequest.is_json or (request.httprequest.data or b'').lstrip()[:1] in (b'{', b'['):
        try:
            j = json.loads(request.httprequest.data or b'{}')
            if isinstance(j, dict):
                data.update(j)
            elif isinstance(j, list):
                data['_list'] = j
        except ValueError:
            pass
    return data


class KavenegarWebhook(http.Controller):
    """Only answers on the Talent Search website; anywhere else it is a plain 404."""

    def _company(self, secret):
        site = request.env.website
        ts_site = request.env.ref('ts_website.website_ts', raise_if_not_found=False)
        if ts_site and site != ts_site:
            raise request.not_found()
        for c in request.env['res.company'].sudo().search([('kv_enabled', '=', True)]):
            if c.kv_webhook_secret and hmac.compare_digest(c.kv_webhook_secret, secret):
                return c
        raise request.not_found()

    @http.route('/kavenegar/<string:secret>/status', type='http', auth='public',
                methods=['GET', 'POST'], csrf=False, website=True, sitemap=False)
    def status(self, secret, **kw):
        company = self._company(secret)
        data = _payload()
        rows = data.get('_list') or [data]
        Msg = request.env['kavenegar.message'].sudo()
        for r in rows:
            mid = str(r.get('messageid') or r.get('id') or '')
            try:
                status = int(r.get('status'))
            except (TypeError, ValueError):
                continue
            msg = Msg.search([('company_id', '=', company.id), ('direction', '=', 'out'),
                              ('messageid', '=', mid)], limit=1) if mid else Msg
            if not msg and r.get('localid'):
                msg = Msg.search([('sms_uuid', '=', str(r['localid']))], limit=1)
            if msg:
                msg._kv_apply_status(status, r.get('statustext') or STATUS_TEXT.get(status))
            else:
                _logger.info('Kavenegar status callback for unknown message id')
        return 'OK'

    @http.route('/kavenegar/<string:secret>/inbound', type='http', auth='public',
                methods=['GET', 'POST'], csrf=False, website=True, sitemap=False)
    def inbound(self, secret, **kw):
        company = self._company(secret)
        data = _payload()
        rows = data.get('_list') or [data]
        rows = [r for r in rows if r.get('message') is not None]
        if rows:
            request.env['kavenegar.message'].sudo()._kv_store_inbound(company, rows)
        return 'OK'
