"""Candidate side of a position invitation.

onb2: the two optional fairness questions (gender, age band) are no longer on the invitation page. They are asked once,
after the last part of the battery and before the feedback card (/my/assessments/battery/<id>/about); «رد شدن» skips them.
Storage and visibility are the same as before: ts_gender / ts_age_band on the invitation (EOT team only), used only for
the fairness view of closed positions with groups of ten or more. Asked once: `ts_fair_asked`."""
from odoo import http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import _ts_site_or_404

from ..models.position import AGE_BANDS, GENDERS


def fair_due(a):
    """The candidate finished every part of a position battery and was not asked yet."""
    a = a.sudo()
    return bool(a.position_id and a.state == 'done' and not a.ts_fair_asked and not (a.ts_gender or a.ts_age_band))


class TsHireFair(http.Controller):

    def _mine(self, assignment_id):
        a = request.env['ts.assignment'].sudo().search([
            ('id', '=', int(assignment_id)), ('user_id', '=', request.env.user.id), ('position_id', '!=', False)], limit=1)
        if not a:
            raise request.not_found()
        return a

    @http.route('/my/assessments/battery/<int:assignment_id>/about', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def fair_page(self, assignment_id, **kw):
        _ts_site_or_404()
        a = self._mine(assignment_id)
        if not fair_due(a):
            return request.redirect('/my/assessments/battery/%s' % a.id)
        return request.render('ts_hire.fair', {'a': a, 'genders': GENDERS, 'ages': AGE_BANDS, 'page_name': 'ts_assessments'})

    @http.route('/my/assessments/battery/<int:assignment_id>/about/save', type='http', auth='user', website=True,
                methods=['POST'], sitemap=False)
    def fair_save(self, assignment_id, **post):
        _ts_site_or_404()
        a = self._mine(assignment_id)
        if fair_due(a):
            vals = {'ts_fair_asked': True}
            if post.get('skip') != '1':
                if post.get('ts_gender') in dict(GENDERS):
                    vals['ts_gender'] = post['ts_gender']
                if post.get('ts_age_band') in dict(AGE_BANDS):
                    vals['ts_age_band'] = post['ts_age_band']
            a.sudo().write(vals)
            request.env['ts.audit.event'].sudo().log('hire.fair_questions', a, workspace=a.workspace_id,
                                                     answered=len(vals) > 1)
        return request.redirect('/my/assessments/battery/%s?submitted=1' % a.id)
