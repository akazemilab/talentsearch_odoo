"""The participant's own pages on Talent Search (S15; PRT-1, PRT-2, PRV-2, ACC-1, ACC-2, ACC-5, ACC-6, AUD-4).

Everything here belongs to the signed-in person: every search is by `user_id = request.env.user` and a row of someone else
is a 404. `/my` and `/my/account` replace the stock pages on the Talent Search website ONLY; on every other website the
stock controller answers unchanged (eot.ir is guarded).
"""
from datetime import datetime, time

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404
from odoo.addons.ts_assessment.models.attempt import fa_digits, jalali
from odoo.addons.ts_org.models.panel import ROLE_LABELS

from .base import flash_error, flash_ok, need_reauth, pop_flash

OPEN_INVITE_STATES = ('invited', 'opened')
REQUEST_WORDS = {'new': 'ثبت شد', 'in_review': 'در حال بررسی', 'done': 'انجام شد', 'rejected': 'رد شد'}


def _ts_site():
    website = request.env.website
    return bool(website and website._ts_is_current())


class TsPanelPortal(CustomerPortal):

    # ------------------------------------------------------------------ PRT-1 home
    @http.route()
    def home(self, **kw):
        if not _ts_site():
            return super().home(**kw)
        env, user = request.env, request.env.user
        A = env['ts.assignment'].sudo()
        T = env['ts.attempt'].sudo()
        invites = A.search([('user_id', '=', False), ('client_id.user_id', '=', user.id), ('state', 'in', OPEN_INVITE_STATES),
                            ('withdrawn', '=', False), ('declined', '=', False)], order='id desc', limit=10)  # ts-scope-ok: own invitations
        mine = T.search([('user_id', '=', user.id)], order='id desc')                                      # ts-scope-ok: own attempts
        going = mine.filtered(lambda a: a.state in ('consent', 'in_progress'))
        done = mine.filtered(lambda a: a.state == 'done' and a.released)[:3]
        shared_n = {a.id: len([s for s in a.ts_shares() if s.share_level != 'none']) for a in done}
        memberships = env['ts.workspace.member'].sudo().search([('user_id', '=', user.id), ('active', '=', True)])  # ts-scope-ok: own memberships
        unread = env['ts.notification'].sudo()._unread_count(user)
        return request.render('ts_panel.my_home', {
            'invites': invites, 'going': going, 'done': done, 'shared_n': shared_n, 'memberships': memberships, 'unread': unread,
            'fa': fa_digits, 'jalali': jalali, 'page_name': 'ts_my_home'})

    # ------------------------------------------------------------------ ACC-1, ACC-2 account
    @http.route()
    def account(self, **kwargs):
        if not _ts_site():
            return super().account(**kwargs)
        user = request.env.user
        phone = user.sudo().partner_id.ts_phone if 'ts_phone' in user.sudo().partner_id._fields else False
        ok, err = pop_flash()
        return request.render('ts_panel.my_account', {
            'user': user, 'phone_verified': bool(phone), 'ok': ok, 'error': err, 'page_name': 'ts_my_account'})

    @http.route('/my/account/name', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def account_name(self, **post):
        _ts_site_or_404()
        name = ' '.join((post.get('name') or '').split())
        if len(name) < 2 or len(name) > 80:
            flash_error('نام باید ۲ تا ۸۰ نویسه باشد.')
        else:
            request.env.user.sudo().write({'name': name})
            request.env['ts.audit.event'].sudo().log('account.name')
            flash_ok('نام شما ذخیره شد.')
        return request.redirect('/my/account')

    # ------------------------------------------------------------------ PRV-2, AUD-4 who can see my results
    def _views(self, assignment):
        """(role label, day) of each opening of the result by that panel; never a name."""
        Ev = request.env['ts.audit.event'].sudo()
        rows = Ev.search([('event_type', '=', 'result.view'), ('res_model', '=', 'ts.attempt'), ('res_id', '=', assignment.attempt_id.id),
                          ('workspace_id', '=', assignment.workspace_id.id), ('outcome', '=', 'ok')], order='id desc', limit=20)
        return [(ROLE_LABELS.get(r.member_id.role, 'عضو پنل') if r.member_id else 'عضو پنل', jalali(r.create_date, with_time=False)) for r in rows]

    @http.route('/my/sharing', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def sharing(self, **kw):
        _ts_site_or_404()
        user = request.env.user
        mine = request.env['ts.attempt'].sudo().search([('user_id', '=', user.id), ('state', '=', 'done'), ('released', '=', True)],  # ts-scope-ok: own attempts
                                                      order='id desc')
        Consent = request.env['ts.consent.record'].sudo()
        blocks = []
        for at in mine:
            shares = []
            for a in at.ts_shares():
                since = Consent.search([('assignment_id', '=', a.id), ('kind', '=', 'share')], order='id desc', limit=1)  # ts-scope-ok: own ledger
                resp = a.client_id.responsible_id.user_id.name if a.client_id.responsible_id else False
                shares.append({'a': a, 'aid': a.id, 'panel': a.workspace_id.name, 'resp': resp, 'level': a.ts_level_word(),
                               'since': jalali(since.at or a.create_date, with_time=False), 'active': a.share_level != 'none',
                               'views': self._views(a) if a.share_level != 'none' else []})
            can_share = (not at.workspace_id and at.source != 'import')
            blocks.append({'at': at, 'shares': shares, 'can_share': can_share})
        ok, err = pop_flash()
        limit = request.env['ir.config_parameter'].sudo().get_int('ts_panel.share_max_panels', 3) or 3
        return request.render('ts_panel.my_sharing', {'blocks': blocks, 'fa': fa_digits, 'ok': ok, 'error': err, 'limit': limit,
                                                      'page_name': 'ts_my_sharing'})

    @http.route('/my/sharing/<int:aid>/revoke', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def sharing_revoke(self, aid, **post):
        _ts_site_or_404()
        user = request.env.user
        a = request.env['ts.assignment'].sudo().search([('id', '=', aid), ('user_id', '=', user.id), ('attempt_id', '!=', False)], limit=1)  # ts-scope-ok: own
        if not a:
            raise request.not_found()
        try:
            a.action_revoke_share(user)
            flash_ok('اشتراک لغو شد؛ پنل دیگر این نتیجه را نمی‌بیند.')
        except UserError as e:
            flash_error(str(e.args[0] if e.args else e))
        return request.redirect('/my/sharing')

    # ------------------------------------------------------------------ ACC-5, ACC-6 my data
    @http.route('/my/privacy', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def privacy(self, **kw):
        _ts_site_or_404()
        user = request.env.user
        reqs = request.env['ts.data.request'].sudo().search([('user_id', '=', user.id)], limit=20)          # ts-scope-ok: own requests
        ok, err = pop_flash()
        return request.render('ts_panel.my_privacy', {'reqs': reqs, 'words': REQUEST_WORDS, 'jalali': jalali,
                                                       'jd': lambda d: jalali(datetime.combine(d, time(12)), with_time=False), 'ok': ok, 'error': err,
                                                       'page_name': 'ts_my_privacy'})

    @http.route('/my/privacy/export', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def privacy_export(self, **post):
        _ts_site_or_404()
        denied = need_reauth('دریافت نسخهٔ داده‌هایتان', '/my/privacy')
        if denied:
            return denied
        req = request.env['ts.data.request'].ts_open(request.env.user, 'export')
        return request.redirect('/my/privacy/jobs/%s' % req.job_id.id)

    @http.route('/my/privacy/erase', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def privacy_erase(self, **post):
        _ts_site_or_404()
        denied = need_reauth('درخواست حذف داده‌هایتان', '/my/privacy')
        if denied:
            return denied
        try:
            request.env['ts.data.request'].ts_open(request.env.user, 'erase')
            flash_ok('درخواست حذف ثبت شد. تا ۳۰ روز دیگر بررسی می‌شود و وضعیت آن را همین‌جا می‌بینید.')
        except UserError as e:
            flash_error(str(e.args[0] if e.args else e))
        return request.redirect('/my/privacy')

    def _own_job(self, jid):
        job = request.env['ts.job'].sudo().search([('id', '=', jid), ('user_id', '=', request.env.user.id), ('kind', '=', 'data_export')], limit=1)  # ts-scope-ok: own job
        if not job:
            raise request.not_found()
        return job

    @http.route('/my/privacy/jobs/<int:jid>', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def privacy_job(self, jid, **kw):
        _ts_site_or_404()
        job = self._own_job(jid)
        return request.render('ts_panel.my_privacy_job', {'job': job, 'ready': job.can_download_own(request.env.user), 'jalali': jalali,
                                                          'page_name': 'ts_my_privacy'})

    @http.route('/my/privacy/jobs/<int:jid>/download', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def privacy_download(self, jid, **kw):
        _ts_site_or_404()
        job = self._own_job(jid)
        if not job.can_download_own(request.env.user):
            raise request.not_found()
        att = job.result_attachment_id.sudo()
        raw = att.raw
        data = bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.content
        request.env['ts.audit.event'].sudo().log('data.download', job)
        return request.make_response(data, headers=[
            ('Content-Type', 'application/zip'), ('Content-Disposition', 'attachment; filename="my-data.zip"'),
            ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')])
