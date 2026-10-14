"""clin8 (owner 2026-10-14): «خدمات», the clinic's service catalog inside the panel.

Everything this member may send: batteries first, then single instruments by category, each with who it is for, about
how long, how many questions and (for the office and the owner, `credits:read`) the price of one use. «فرستادن به مراجع»
opens the one-screen invitation with that item chosen. Presentation only: what may be sent is still decided by the
panel catalog and the member restriction (ts_battery), and the price by the product (ts_billing).
"""
from odoo import http
from odoo.http import request

from odoo.addons.ts_assessment.models.attempt import fa_digits
from odoo.addons.ts_billing.tools import fmt_toman
from odoo.addons.ts_panel.controllers.base import member_or_404, render_in_shell, require


def _price(rec, show):
    if not show or not rec.product_id:
        return ''
    p = rec.product_id.sudo().list_price
    return fmt_toman(p) if p else ''


class TsServices(http.Controller):

    @http.route('/my/workspaces/<int:ws_id>/services', type='http', auth='user', website=True, methods=['GET'],
                sitemap=False)
    def services(self, ws_id, **kw):
        me = member_or_404(ws_id)
        ws = me.workspace_id
        if ws.purpose != 'clinical':
            raise request.not_found()
        denied = require(me, 'invites:create', 'services')
        if denied:
            return denied
        show_price = me.has_perm('credits:read')
        can_send = me.can_act()
        send = '/my/workspaces/%d/invites/new?pick=%s'
        bats = []
        for b in me.allowed_batteries().sorted(lambda x: x.ts_title().replace('‌', ' ')):
            card = b.ts_card()
            bats.append({'id': b.id, 'title': card['name'], 'facts': card, 'desc': card.get('description') or '',
                         'lines': [ln['name'] for ln in card.get('lines', [])], 'price': _price(b, show_price),
                         'send': (send % (ws.id, 'b%d' % b.id)) if can_send else ''})
        groups = {}
        for i in me.allowed_instruments():
            groups.setdefault(i.category or 'دیگر', []).append({
                'id': i.id, 'title': i.ts_title(), 'time': i.ts_total_time_label(), 'effort': i.ts_effort_label(),
                'summary': i.summary or '', 'use': i.intended_use or '', 'limits': i.limitations or '',
                'price': _price(i, show_price), 'send': (send % (ws.id, 'i%d' % i.id)) if can_send else ''})
        cats = [{'name': k, 'rows': sorted(v, key=lambda r: r['title'].replace('‌', ' '))}
                for k, v in sorted(groups.items(), key=lambda kv: kv[0].replace('‌', ' '))]
        return render_in_shell(
            'ts_onboard.services', me, 'services', 'خدمات', bats=bats, cats=cats, show_price=show_price,
            n_total=len(bats) + sum(len(c['rows']) for c in cats), fa=fa_digits,
            members_url=('/my/workspaces/%d/members' % ws.id) if me.has_perm('catalog:assign') else None)
