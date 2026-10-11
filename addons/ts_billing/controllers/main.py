"""Credits page of a prepaid panel (docs/clinic/04_billing_brief.md section 6). Free panels keep ts_panel's page unchanged.

credits:read (owner, admin, clinic_director, hr_admin): available, held, this month, usage per counselor, caps (credits:manage),
low-balance threshold (credits:manage), price list, invoices with their portal link. A capped role (clinician, counselor,
hiring manager, reviewer) without credits:read: own cap and own month only, plus the price list. Everything is read with sudo
after the membership and permission checks of ts_panel's helpers."""
from datetime import datetime, time

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_panel.controllers.base import flash_error, flash_ok, forbidden, member_or_404, render_in_shell
from odoo.addons.ts_panel.controllers.credits import TsPanelCredits

from ..tools import CAPPED_ROLES, rial_int

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬,', '01234567890123456789  ')


def _rial_from_toman(text):
    """«۱٬۲۰۰٬۰۰۰» (toman, as typed on the page) -> 12000000 Rial; None when it is not a whole number."""
    s = (text or '').strip().translate(_DIGITS).replace(' ', '')
    if s == '':
        return 0
    return int(s) * 10 if s.isdigit() else None


def _price_rows(me):
    """[(kind label, name, rial)] of the items this panel (and this member) may invite."""
    ws = me.workspace_id.sudo()
    rows = [('مجموعه', b.name, ws.ts_item_price(battery=b)) for b in me.allowed_batteries()]
    rows += [('سنجه', i.title or i.name, ws.ts_item_price(instrument=i)) for i in me.allowed_instruments()]
    return rows


class TsBillingCredits(TsPanelCredits):

    @http.route()
    def page(self, ws_id, **kw):
        me = member_or_404(ws_id)
        ws = me.workspace_id
        if not ws.ts_is_prepaid():
            return super().page(ws_id, **kw)
        if not me.has_perm('credits:read'):
            if me.role in CAPPED_ROLES and me.can_act():
                return self._own_page(me)
            return super().page(ws_id, **kw)     # the usual 403
        wallet = request.env['ts.wallet']._for_workspace(ws)
        st = me.ts_bill_state()
        M = request.env['ts.workspace.member'].sudo()
        capped = M.search([('workspace_id', '=', ws.id), ('active', '=', True), ('role', 'in', list(CAPPED_ROLES))],
                          order='id')
        Txn = request.env['ts.wallet.txn'].sudo()
        rows = Txn.search([('workspace_id', '=', ws.id)], limit=50)
        invoices = ws.ts_invoices()
        from odoo.addons.ts_assessment.models.attempt import jalali
        inv_rows = [{'name': m.name, 'date': jalali(datetime.combine(m.invoice_date, time(12)), with_time=False) if m.invoice_date else '',
                     'amount': rial_int(m.amount_total), 'paid': m.payment_state in ('paid', 'in_payment'),
                     'url': '/my/invoices/%s?access_token=%s' % (m.id, m._portal_ensure_token())} for m in invoices]
        return render_in_shell(
            'ts_billing.credits_prepaid', me, 'credits', 'اعتبار و مصرف', wallet=wallet, st=st,
            by_member=wallet.ts_month_by_member(), capped=capped, can_manage=me.has_perm('credits:manage'),
            prices=_price_rows(me), invoices=inv_rows, rows=rows,
            type_labels=dict(Txn._fields['type'].selection), reason_labels=dict(Txn._fields['reason_code'].selection),
            toman=ws.ts_toman, threshold=rial_int(wallet.low_threshold))

    def _own_page(self, me):
        return render_in_shell('ts_billing.credits_own', me, 'credits', 'اعتبار و مصرف', st=me.ts_bill_state(),
                               prices=_price_rows(me), toman=me.workspace_id.ts_toman)

    @http.route('/my/workspaces/<int:ws_id>/credits/cap', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def set_cap(self, ws_id, **post):
        me = member_or_404(ws_id)
        if not me.has_perm('credits:manage') or not me.can_act():
            return forbidden(me, 'credits:manage', 'credits')
        mid = post.get('member_id') or ''
        target = request.env['ts.workspace.member'].sudo().search(
            [('id', '=', int(mid) if mid.isdigit() else 0), ('workspace_id', '=', me.workspace_id.id)], limit=1)
        back = post.get('back') if post.get('back') in ('member',) else 'credits'
        url = ('/my/workspaces/%s/members/%s#tsb-cap' % (ws_id, target.id)) if (back == 'member' and target) \
            else '/my/workspaces/%s/credits#tsb-caps' % ws_id
        if not target:
            raise request.not_found()
        rial = _rial_from_toman(post.get('cap'))
        try:
            if rial is None:
                raise UserError('سقف را به تومان و با عدد بنویسید؛ ۰ یعنی بدون سقف.')
            changed = target.ts_set_cap(me, rial)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('سقف ماهانه ذخیره شد.' if changed else 'تغییری نبود.')
        return request.redirect(url)

    @http.route('/my/workspaces/<int:ws_id>/credits/threshold', type='http', auth='user', website=True, methods=['POST'],
                sitemap=False)
    def set_threshold(self, ws_id, **post):
        me = member_or_404(ws_id)
        if not me.has_perm('credits:manage') or not me.can_act():
            return forbidden(me, 'credits:manage', 'credits')
        wallet = request.env['ts.wallet']._for_workspace(me.workspace_id)
        rial = _rial_from_toman(post.get('threshold'))
        try:
            if rial is None:
                raise UserError('آستانه را به تومان و با عدد بنویسید؛ ۰ یعنی خاموش.')
            changed = wallet.ts_set_threshold(me, rial)
        except (UserError, ValidationError) as e:
            flash_error(str(e.args[0] if e.args else e))
        else:
            flash_ok('آستانهٔ هشدار ذخیره شد.' if changed else 'تغییری نبود.')
        return request.redirect('/my/workspaces/%s/credits#tsb-alert' % ws_id)
