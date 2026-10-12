"""Credits page of a prepaid panel (docs/clinic/04_billing_brief.md section 6). Free panels keep ts_panel's page unchanged.

credits:read (owner, admin, clinic_director, hr_admin): available, held, this month, usage per counselor, caps (credits:manage),
low-balance threshold (credits:manage), price list, invoices with their portal link. A capped role (clinician, counselor,
hiring manager, reviewer) without credits:read: own cap and own month only, plus the price list. Everything is read with sudo
after the membership and permission checks of ts_panel's helpers."""
from datetime import datetime, time

from markupsafe import Markup

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.ts_panel.controllers.base import flash_error, flash_ok, forbidden, member_or_404, render_in_shell
from odoo.addons.ts_battery.controllers.main import TsBatteryInvites
from odoo.addons.ts_panel.controllers.credits import TsPanelCredits

from ..tools import CAPPED_ROLES, fmt_toman, item_title, rial_int

TEAM = 'به دست تیم استعدادیاب'

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬,', '01234567890123456789  ')


def _rial_from_toman(text):
    """«۱٬۲۰۰٬۰۰۰» (toman, as typed on the page) -> 12000000 Rial; None when it is not a whole number."""
    s = (text or '').strip().translate(_DIGITS).replace(' ', '')
    if s == '':
        return 0
    return int(s) * 10 if s.isdigit() else None


def _price_rows(me):
    """{'prices': [(kind label, name, rial)] of the PRICED items this panel (and this member) may invite, dearest first,
    'free_n': how many other items cost nothing}. A panel offers dozens of items; listing every free one buried the prices."""
    ws = me.workspace_id.sudo()
    rows = [('مجموعه', item_title(b), ws.ts_item_price(battery=b)) for b in me.allowed_batteries()]
    rows += [('سنجه', item_title(i), ws.ts_item_price(instrument=i)) for i in me.allowed_instruments()]
    priced = sorted((r for r in rows if r[2]), key=lambda r: (-r[2], r[1]))
    return {'prices': priced, 'free_n': len(rows) - len(priced)}


def _ledger_rows(ws, rows, type_labels, reason_labels, jalali):
    """Display rows of the ledger, newest first. Presentation only: the ledger rows stay as they are (UX audit G7-P2-4).
    * A completion is posted as a pair (release of the hold, then the debit of the same price, same assignment): it is
      shown as ONE row «کسر از رزرو · تکمیل سنجه», amount «… تومان (از رزرو)», the balance after it (unchanged).
    * A zero debit (free panel, unpriced item) reads «تکمیل سنجه · بدون هزینه» (G8-P4-4).
    * A back-office grant or correction says it was made by the EOT team."""
    out = []
    rows = list(rows)
    i = 0
    while i < len(rows):
        r = rows[i]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        row = {'date': jalali(r.txn_date), 'label': type_labels.get(r.type, r.type),
               'why': reason_labels.get(r.reason_code, '') if r.reason_code else '',
               'amount': ws.ts_toman_signed(r.amount), 'balance': fmt_toman(r.balance_after), 'kind': r.type}
        if (r.type == 'debit_usage' and r.amount < 0 and nxt and nxt.type == 'release' and nxt.reason_code == 'completion'
                and nxt.assignment_id and nxt.assignment_id == r.assignment_id and rial_int(nxt.amount) == -rial_int(r.amount)):
            row.update(label='کسر از رزرو', why=reason_labels.get('completion', 'تکمیل سنجه'), kind='debit_held',
                       amount=Markup('%s <small class="tsb-ledger__note">(از رزرو)</small>') % fmt_toman(-r.amount))
            i += 1
        elif r.type == 'debit_usage' and not rial_int(r.amount):
            row.update(label=reason_labels.get('completion', 'تکمیل سنجه'), why='', amount='بدون هزینه', kind='free')
        elif r.type == 'adjust' and r.reason_code in (False, None, 'manual', 'correction'):
            row.update(why=TEAM)
        elif r.type == 'grant':
            row.update(why=TEAM)
        if row['why'] == row['label']:
            row['why'] = ''
        out.append(row)
        i += 1
    return out


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
        type_labels = dict(Txn._fields['type'].selection)
        reason_labels = dict(Txn._fields['reason_code'].selection)
        # every capped member is listed in the commitment table, with ۰ when he sent nothing this month (G8-P4-4)
        by_member = wallet.ts_month_by_member()
        seen = {u.id for u, _n, _s in by_member}
        by_member += [(cm.user_id, 0, 0) for cm in capped if cm.user_id.id not in seen]
        return render_in_shell(
            'ts_billing.credits_prepaid', me, 'credits', 'اعتبار و مصرف', wallet=wallet, st=st,
            by_member=by_member, capped=capped, can_manage=me.has_perm('credits:manage'),
            invoices=inv_rows, rows=_ledger_rows(ws, rows, type_labels, reason_labels, jalali), **_price_rows(me),
            toman=ws.ts_toman, threshold=rial_int(wallet.low_threshold), collapse_prices=True, cap_left=None)

    def _own_page(self, me):
        st = me.ts_bill_state()
        return render_in_shell('ts_billing.credits_own', me, 'credits', 'هزینهٔ دعوت‌های شما', st=st,
                               toman=me.workspace_id.ts_toman, collapse_prices=False,
                               cap_left=st['cap_left'] if st and st['capped'] else None, **_price_rows(me))

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


class TsBillingInvites(TsBatteryInvites):
    """Step 2 of the invitation wizard: an item the panel balance or the member's monthly cap cannot cover is refused right
    there, with the same text the creation would give (UX audit G7-P11-1). Presentation only: the binding check stays in
    ts.wallet.ts_hold() at creation."""

    def _read_item(self, me, post, d):
        err = super()._read_item(me, post, d)
        if err:
            return err
        bill = me.ts_bill_prices()
        if not bill:
            return None
        if d.get('battery_id'):
            price, why = bill['bat'].get(d['battery_id'], 0), bill['why_bat'].get(d['battery_id'])
        else:
            price, why = bill['inst'].get(d.get('instrument_id'), 0), bill['why_inst'].get(d.get('instrument_id'))
        if not why:
            return None
        ws = me.workspace_id.sudo()
        W = request.env['ts.wallet'].sudo()
        if why == 'cap':
            return W.ts_refusal_cap(ws, price, bill['cap_left'] or 0)
        return W.ts_refusal_insufficient(ws, bill['available'], price, me)
