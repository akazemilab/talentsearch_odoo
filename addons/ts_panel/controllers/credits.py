"""Credits and usage page (S11, WAL-2, WAL-3). Read only: the ledger is written by the models. While the panel is in free mode
the page says so and never shows a price."""
from odoo import http
from odoo.http import request

from .base import member_or_404, render_in_shell, require

PAGE = 50


class TsPanelCredits(http.Controller):

    @http.route('/my/workspaces/<int:ws_id>/credits', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def page(self, ws_id, **kw):
        me = member_or_404(ws_id)
        denied = require(me, 'credits:read', 'credits')
        if denied:
            return denied
        ws = me.workspace_id
        wallet = request.env['ts.wallet']._for_workspace(ws)
        Txn = request.env['ts.wallet.txn'].sudo()
        rows = Txn.search([('workspace_id', '=', ws.id)], limit=PAGE)
        months = wallet.usage_by_month(6)
        names = sorted({n for _y, _m, by in months for n in by})
        return render_in_shell(
            'ts_panel.credits', me, 'credits', 'اعتبار و مصرف', wallet=wallet, free=wallet._free_mode(), rows=rows,
            month_units=wallet.current_month_units(), committed=wallet.committed(), months=months, names=names,
            type_labels=dict(Txn._fields['type'].selection), reason_labels=dict(Txn._fields['reason_code'].selection))
