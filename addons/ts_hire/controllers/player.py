"""Candidate feedback on the battery result page of a position (benchmark practice and ITC 2.8.10: constructive
feedback to every candidate). The candidate always sees their own report; the employer never sees this page."""
from odoo import http
from odoo.http import request

from odoo.addons.ts_tasks.controllers.main import TsTaskPlayer

from ..models.hexaco import HEXACO_CODE

HR_NOTE = ('این گزارش بازخورد برای خود شماست. سازمان پاسخ‌ها و نمره‌های شما را نمی‌بیند؛ اگر اشتراک‌گذاری را پذیرفته باشید، '
           'فقط خلاصهٔ تناسب شما با نیازهای این شغل را می‌بیند. هیچ تصمیمی به‌طور خودکار از این نتیجه گرفته نمی‌شود.')


class TsHirePlayer(TsTaskPlayer):

    @http.route()
    def my_battery(self, assignment_id, **kw):
        res = super().my_battery(assignment_id, **kw)
        qc = getattr(res, 'qcontext', None)
        a = qc and qc.get('a')
        if not a or not a.position_id:
            return res
        qc['limit_note'] = HR_NOTE
        qc['counselor'] = ''
        strengths, abilities = [], []
        for t in a.ts_battery_attempts().filtered(lambda x: x.state == 'done' and x.released):
            if t.instrument_id.code == HEXACO_CODE:
                rows = t.result_rows().filtered(lambda r: r.band == 'high').sorted(lambda r: -r.score)[:3]
                strengths = [{'name': r.factor_id.name, 'text': r.client_text} for r in rows]
            elif t.version_id.mode == 'task':
                abilities += [{'name': r.factor_id.name, 'band': r.band, 'band_fa': r.band_fa()} for r in t.result_rows()]
        qc['hire_feedback'] = {'position': a.position_id.name, 'strengths': strengths, 'abilities': abilities}
        return res
