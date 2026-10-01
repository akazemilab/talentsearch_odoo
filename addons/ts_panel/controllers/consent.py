"""Consent page for minors (S16, GRD-2, GRD-5). Overrides POST /take/<token>/consent.

* Someone who takes a test on their own (no panel) says whether they are 18. Under 18 they must say a guardian agrees; the
  ledger gets a `guardian` row (given_as guardian, method checkbox).
* A minor client inside a panel must tick their own assent; the ledger gets an `assent` row.
Adults and the old flow are unchanged; the service and research rows follow every accepted consent.
"""
from odoo import http
from odoo.http import request

from odoo.addons.ts_assessment.controllers.main import TsAssessment, _my_attempt, _ts_site_or_404

TEXT_VERSION = 'TS-MINOR-1405-07-v1'


class TsPanelConsent(TsAssessment):

    @http.route()
    def consent(self, token, **post):
        _ts_site_or_404()
        attempt = _my_attempt(token)
        if attempt.state == 'consent' and post.get('consent_service') == '1':
            kind = None
            if not attempt.workspace_id:
                if post.get('age18') not in ('yes', 'no'):
                    return request.redirect('/take/%s?error=age' % token)
                if post['age18'] == 'no':
                    if post.get('guardian_ok') != '1':
                        return request.redirect('/take/%s?error=guardian_ok' % token)
                    kind = 'guardian'
            elif attempt.client_id.age_group == 'minor':
                if post.get('assent_ok') != '1':
                    return request.redirect('/take/%s?error=assent' % token)
                kind = 'assent'
            res = super().consent(token, **post)
            attempt.invalidate_recordset()
            if attempt.state == 'in_progress' and kind:
                request.env['ts.consent.record']._log(
                    kind, request.env.user, attempt=attempt, workspace=attempt.workspace_id, version=TEXT_VERSION,
                    given_as='guardian' if kind == 'guardian' else 'self', client=attempt.client_id)
            return res
        return super().consent(token, **post)
