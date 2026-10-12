"""Candidate side of a position invitation: the invite page tells what the employer sees, and the optional,
separately stored fairness questions (gender, age band) are saved on acceptance."""
from odoo import http
from odoo.http import request

from odoo.addons.ts_org.controllers.main import TsOrg

from ..models.position import AGE_BANDS, GENDERS


class TsHireOrg(TsOrg):

    @http.route()
    def invite_page(self, token, **kw):
        res = super().invite_page(token, **kw)
        qc = getattr(res, 'qcontext', None)
        if qc is not None and qc.get('a') is not None:
            qc['hire_genders'] = GENDERS
            qc['hire_ages'] = AGE_BANDS
        return res

    @http.route()
    def invite_accept(self, token, **post):
        a = request.env['ts.assignment'].sudo().search([('token', '=', token)], limit=1)
        res = super().invite_accept(token, **post)
        if a and a.position_id and a.user_id == request.env.user:
            vals = {}
            if post.get('ts_gender') in dict(GENDERS):
                vals['ts_gender'] = post['ts_gender']
            if post.get('ts_age_band') in dict(AGE_BANDS):
                vals['ts_age_band'] = post['ts_age_band']
            if vals and not (a.ts_gender or a.ts_age_band):
                a.sudo().write(vals)
        return res
