"""PDF reports (docs/clinic/01_architecture.md section 5): one result and one battery, rendered on demand from the same
report blocks as the screen pages, never stored (`attachment` is empty on both ir.actions.report records).

The controllers decide access first (participant: own attempt; panel: `result_level()` exactly like the screen page, level
'status' -> 404) and pass `data = {'mode': 'self' | 'panel', 'level': ...}`. These models only shape the values; they never
widen what the level allows: at 'summary' / 'education' only bands are rendered, scores and counselor guides only at
'clinical' (the same `ts_panel.result_bands_body` the screen uses).
"""
import os

from markupsafe import Markup

from odoo import api, models

from odoo.addons.ts_assessment.models.attempt import fa_digits

KIND = {'self': 'گزارش نتیجهٔ سنجه', 'summary': 'خلاصهٔ نتیجه', 'education': 'گزارش در سطح مشاور',
        'clinical': 'گزارش ویژهٔ مشاور'}
PANEL_LEVELS = ('summary', 'education', 'clinical')
# wkhtmltopdf cannot load the website asset bundle, so the fonts are named by absolute file path. Only WOFF2 files exist in
# ts_website/static/fonts and wkhtmltopdf's QtWebKit does not read WOFF2: the rule is kept (a TTF placed next to them is
# picked up first) and the text falls back to the system stack in report_pdf.xml ('Vazirmatn', 'Tahoma', 'DejaVu Sans').
FONTS = (('Vazirmatn FD', 'Vazirmatn-FD'), ('Vazirmatn', 'Vazirmatn'))


def _font_faces():
    try:
        from odoo.tools.misc import file_path
        base = os.path.dirname(file_path('ts_website/static/fonts/README'))
    except Exception:
        return ''
    rules = []
    for family, stem in FONTS:
        srcs = []
        for fname, fmt in ((stem + '.ttf', 'truetype'), (stem + '-Var.ttf', 'truetype'), (stem + '-Var.woff2', 'woff2')):
            path = os.path.join(base, fname)
            if os.path.exists(path):
                srcs.append("url('file://%s') format('%s')" % (path, fmt))
        if srcs:
            rules.append("@font-face { font-family: '%s'; src: %s; font-weight: 100 900; }" % (family, ', '.join(srcs)))
    return Markup('\n'.join(rules))


def _talent(attempt, org_view):
    """Values of the talent (matrix) section: the plain summary and the full table, no raw answers."""
    from odoo.addons.ts_talent.controllers.main import report_ctx
    ctx = report_ctx(attempt, org_view=org_view)     # the PDF never prints raw answers (the screen keeps them for the participant)
    return {'summary': ctx['summary'], 'fields': ctx['fields'], 'rows': ctx['rows'], 'interp': ctx['interp'],
            'fmt': ctx['fmt'], 'joinfa': ctx['joinfa'], 'org_view': org_view}


def _who(at, mode):
    """The person's name as the reader knows it: for staff the panel's own record of the participant (client, else the
    name the panel typed on the invitation); for the person the account's own name. Never the formatted mobile that a
    mobile-only account carries until its owner gives a name (onb1)."""
    at = at.sudo()
    client = at.client_id if 'client_id' in at._fields else False
    if mode == 'panel':
        a = at.assignment_id if 'assignment_id' in at._fields else False
        return (client.name if client else '') or (a.invitee_name if a else '') or ''
    return at.person_id.name if 'person_id' in at._fields and at.person_id else (at.partner_id.ts_known_name() if at.partner_id else '')


def _section(at, mode, level):
    """One instrument of a report: {'at', 'inst', 'level', 'results', 'talent', 'done'}."""
    done = at.state == 'done' and at.released
    matrix = bool(at.ts_is_matrix()) if hasattr(at, 'ts_is_matrix') else False
    out = {'at': at, 'inst': at.instrument_id, 'level': level if done else 'status', 'done': done,
           'results': at.env['ts.attempt.result'], 'talent': None}
    if not done:
        return out
    if matrix and (mode == 'self' or level == 'education'):
        out['talent'] = _talent(at, mode != 'self')
    elif mode == 'self' or level in PANEL_LEVELS:
        out['results'] = at.result_rows()
    return out


class ReportAttemptPdf(models.AbstractModel):
    _name = 'report.ts_brand.attempt_pdf'
    _description = 'استعدادیاب: PDF نتیجهٔ یک سنجه'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        mode = 'panel' if data.get('mode') == 'panel' else 'self'
        level = data.get('level') or 'self'
        at = self.env['ts.attempt'].sudo().browse(docids)[:1]
        sec = _section(at, mode, level)
        return {
            'doc_ids': at.ids, 'doc_model': 'ts.attempt', 'docs': at, 'attempt': at, 'mode': mode, 'level': level,
            'sections': [sec], 'single': True, 'brand': at.ts_brand_header(), 'fa': fa_digits,
            'kind': KIND.get('self' if mode == 'self' else level, ''), 'title': at.instrument_id.ts_title(),
            'who': _who(at, mode), 'when': at.jalali(at.submitted_at, False) if at.submitted_at else '',
            'ref': at.name, 'limitations': at.instrument_id.limitations or '', 'font_faces': _font_faces(),
        }


class ReportBatteryPdf(models.AbstractModel):
    _name = 'report.ts_brand.battery_pdf'
    _description = 'استعدادیاب: PDF نتیجهٔ یک مجموعه'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        mode = 'panel' if data.get('mode') == 'panel' else 'self'
        level = data.get('level') or 'self'
        a = self.env['ts.assignment'].sudo().browse(docids)[:1]
        rows = a.ts_battery_attempts()
        done, total = a.ts_battery_progress()
        last = max(rows.filtered(lambda t: t.submitted_at).mapped('submitted_at') or [a.create_date])
        return {
            'doc_ids': a.ids, 'doc_model': 'ts.assignment', 'docs': a, 'assignment': a, 'mode': mode, 'level': level,
            'sections': [_section(t, mode, level) for t in rows], 'single': False, 'brand': a.ts_brand_header(),
            'fa': fa_digits, 'kind': 'گزارش مجموعهٔ سنجه‌ها' if mode == 'self' else KIND.get(level, ''),
            'title': a.battery_id.name, 'who': (a.client_id.name if mode == 'panel' and a.client_id else '')
            or (a.invitee_name if mode == 'panel' else a.user_id.partner_id.ts_known_name()) or a.invitee_name or '',
            'when': rows[:1].jalali(last, False) if rows else '', 'ref': a.name, 'done': done, 'total': total,
            'limitations': 'هر سنجه تصویری از پاسخ‌ها در همان روز است و به‌تنهایی مبنای تصمیم نیست.',
            'font_faces': _font_faces(),
        }
