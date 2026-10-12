"""Prepaid ledger (docs/clinic/04_billing_brief.md sections 0, 1, 4, 5, 6, 7).

`ts.wallet.txn` rows are the only truth; `ts.wallet.balance` is their stored sum; rows are never edited or deleted. One code
path posts rows: `ts.wallet._post()` (wallet row lock + idempotency key). Every blocking decision (insufficient credit, monthly
cap) is taken in `ts_hold()` under that lock, in the transaction that creates the invitation.

Keys: hold:<assignment>, release:<assignment>, usage:<attempt>, refund:<attempt>, topup:<move>, topup-rev:<credit note>.
"""
import logging
import uuid
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools import CAPPED_ROLES, credit_ask, credit_roles, fmt_toman, jalali_month_bounds, rial_int

_logger = logging.getLogger(__name__)

NEW_TYPES = [('hold', 'رزرو اعتبار'), ('release', 'آزادسازی رزرو'), ('topup', 'شارژ اعتبار')]
NEW_REASONS = [('invite', 'دعوت'), ('expiry', 'پایان مهلت دعوت'), ('withdraw', 'لغو دعوت'), ('decline', 'رد دعوت'),
               ('topup', 'فاکتور شارژ'), ('topup_reversal', 'برگشت فاکتور شارژ'), ('insufficient', 'اعتبار ناکافی')]
# Refusal texts (wording only; the decisions are in ts_hold / ts_launch). Amounts of the panel balance are shown only to
# members with credits:read; everybody else is told whom to ask (UX audit G7-P12-1, G7-P4-2, G7-PAT-4).
INSUFFICIENT = ('اعتبار پنل برای این دعوت کافی نیست: موجودی قابل استفاده %s است و هزینهٔ این دعوت %s. '
                'اعتبار را شارژ کنید یا سنجه یا مجموعهٔ دیگری برگزینید.')
INSUFFICIENT_ASK = 'اعتبار پنل برای این دعوت کافی نیست. به %s خبر دهید تا اعتبار را شارژ کند.'
INSUFFICIENT_BATCH = ('اعتبار پنل برای این دعوت گروهی کافی نیست: %s نفر، هر نفر %s، روی هم %s لازم است و موجودی قابل '
                      'استفاده %s است. اعتبار را شارژ کنید یا گروه کوچک‌تری انتخاب کنید.')
INSUFFICIENT_BATCH_ASK = 'اعتبار پنل برای این دعوت گروهی کافی نیست. به %s خبر دهید تا اعتبار را شارژ کند.'
CAP_OVER = ('هزینهٔ این دعوت (%s) از باقی‌ماندهٔ سقف ماهانهٔ شما (%s) بیشتر است. سنجه یا مجموعهٔ دیگری برگزینید '
            'یا از %s بخواهید سقف را بالا ببرد.')
CAP_FULL = CAP_OVER     # older name
LOW_TEXT = 'اعتبار پنل «%s» به %s رسید. برای ادامهٔ دعوت‌ها اعتبار را شارژ کنید.'
# spend of a member in a month: a hold spends, a release or refund gives back, a debit_usage converts a released hold
SPEND_SQL = "CASE WHEN t.type IN ('hold', 'release', 'debit_usage', 'refund') THEN -t.amount ELSE 0 END"


class CreditRefused(UserError):
    """A blocking billing decision (kind insufficient | cap). The message is the panel text of the brief."""

    def __init__(self, message, kind, workspace=None, amount=0, member=None):
        super().__init__(message)
        self.ts_kind = kind
        self.ts_workspace = workspace
        self.ts_amount = amount
        self.ts_member = member

    def ts_log(self, env):
        """Write the credit.refused audit row (callers do this after their savepoint rolled back)."""
        env['ts.audit.event'].sudo().log('credit.refused', self.ts_workspace, workspace=self.ts_workspace,
                                         member=self.ts_member or None, outcome='denied', kind=self.ts_kind,
                                         amount=self.ts_amount)
        env['ts.wallet'].sudo()._ts_on_refused(self)


class TsWallet(models.Model):
    _inherit = 'ts.wallet'

    currency_id = fields.Many2one('res.currency', related='workspace_id.company_id.currency_id', string='ارز')
    balance = fields.Monetary('موجودی', compute='_compute_totals', store=True, currency_field='currency_id')
    low_threshold = fields.Monetary('آستانهٔ هشدار', default=0, currency_field='currency_id',
                                    help='وقتی موجودی قابل استفاده از این مبلغ کمتر شود، به اعضایی که «اعتبار و مصرف» را می‌بینند '
                                         '(مالک، هماهنگ‌کننده، مدیر مرکز مشاوره یا مدیر منابع انسانی) اعلان می‌رسد. ۰ = خاموش.')
    held = fields.Monetary('رزروشده', compute='_compute_held', currency_field='currency_id')
    billing_mode = fields.Selection(related='workspace_id.billing_mode')

    @api.model
    def _ts_on_refused(self, err):
        """Hook after a refusal was audited (ts_brand: the cap_reached notice to the counselor). Never raises."""
        return None

    def _compute_held(self):
        for w in self:
            w.held = w.ts_held() if w.id else 0

    # ------------------------------------------------------------------ numbers (one SQL query each)
    def _lock(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM ts_wallet WHERE id = %s FOR UPDATE', [self.id])

    def ts_available(self):
        """available = SUM(amount): holds are negative rows already."""
        self.ensure_one()
        self.env.flush_all()
        self.env.cr.execute('SELECT COALESCE(SUM(amount), 0) FROM ts_wallet_txn WHERE wallet_id = %s', [self.id])
        return rial_int(self.env.cr.fetchone()[0])

    def ts_held(self):
        """held = -(SUM(hold) + SUM(release)) >= 0."""
        self.ensure_one()
        self.env.flush_all()
        self.env.cr.execute("SELECT COALESCE(SUM(amount), 0) FROM ts_wallet_txn WHERE wallet_id = %s AND type IN ('hold', 'release')",
                            [self.id])
        return -rial_int(self.env.cr.fetchone()[0])

    def ts_month_spend(self, member=None):
        """Spend of the current Jalali month (Asia/Tehran): of the whole panel, or of the invitations `member` sent."""
        self.ensure_one()
        start, end = jalali_month_bounds()
        self.env.flush_all()
        sql = ("SELECT COALESCE(SUM(%s), 0) FROM ts_wallet_txn t LEFT JOIN ts_assignment a ON a.id = t.assignment_id "
               "WHERE t.wallet_id = %%s AND t.txn_date >= %%s AND t.txn_date < %%s" % SPEND_SQL)
        args = [self.id, start, end]
        if member is not None:
            sql += ' AND a.invited_by_id = %s'
            args.append(member.user_id.id)
        self.env.cr.execute(sql, args)
        return rial_int(self.env.cr.fetchone()[0])

    def ts_month_debited(self):
        """«کسرشده این ماه»: what completions actually took from the panel in the current Jalali month (debit rows; a refund
        of a voided attempt gives its amount back). Holds that are still open are not in it (they are «رزروشده»)."""
        self.ensure_one()
        start, end = jalali_month_bounds()
        self.env.flush_all()
        self.env.cr.execute("SELECT COALESCE(SUM(amount), 0) FROM ts_wallet_txn WHERE wallet_id = %s AND type IN ('debit_usage', 'refund') "
                            "AND txn_date >= %s AND txn_date < %s", [self.id, start, end])
        return -rial_int(self.env.cr.fetchone()[0])

    @api.model
    def ts_refusal_insufficient(self, ws, available, price, member=None):
        """Text of an insufficient-credit refusal for `member` (None = a member who may see the balance)."""
        if member is not None and not member.sudo().has_perm('credits:read'):
            return INSUFFICIENT_ASK % credit_ask(ws.purpose)
        return INSUFFICIENT % (fmt_toman(available), fmt_toman(price))

    @api.model
    def ts_refusal_cap(self, ws, price, left):
        return CAP_OVER % (fmt_toman(price), fmt_toman(max(left, 0)), credit_ask(ws.purpose))

    def ts_month_by_member(self):
        """[(user, invitations held this month, spend)] for the per-counselor table, highest spend first."""
        self.ensure_one()
        start, end = jalali_month_bounds()
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT a.invited_by_id, COUNT(DISTINCT CASE WHEN t.type = 'hold' THEN t.assignment_id END), COALESCE(SUM(%s), 0) "
            "FROM ts_wallet_txn t JOIN ts_assignment a ON a.id = t.assignment_id "
            "WHERE t.wallet_id = %%s AND t.txn_date >= %%s AND t.txn_date < %%s AND a.invited_by_id IS NOT NULL "
            "GROUP BY a.invited_by_id ORDER BY 3 DESC" % SPEND_SQL, [self.id, start, end])
        U = self.env['res.users'].sudo()
        return [(U.browse(uid), n, rial_int(s)) for uid, n, s in self.env.cr.fetchall()]

    @api.model
    def _free_mode(self):
        """Per panel now: a prepaid panel is never free; every other panel keeps today's rule."""
        if len(self) == 1 and self.workspace_id.billing_mode == 'prepaid':
            return False
        if len(self) == 1:
            return True
        return super()._free_mode()

    # ------------------------------------------------------------------ the only writer of the ledger
    def _post(self, type_, amount, units, idem_key, reason, attempt=None, actor=None, free=None, assignment=None, move=None):
        """Append one ledger row. Idempotent on `idem_key`: a second call returns the existing row. Locks the wallet row
        while it computes `balance_after`. (Replaces ts_panel's _post: numeric money, explicit assignment.)"""
        self.ensure_one()
        self._lock()
        Txn = self.env['ts.wallet.txn'].sudo()
        old = Txn.search([('idem_key', '=', idem_key)], limit=1)
        if old:
            return old
        amount = rial_int(amount)
        self.env.flush_all()
        self.env.cr.execute('SELECT COALESCE(SUM(amount), 0) FROM ts_wallet_txn WHERE wallet_id = %s', [self.id])
        before = rial_int(self.env.cr.fetchone()[0])
        a = assignment or self.env['ts.assignment']
        if attempt and not a:
            a = attempt.sudo().assignment_id if 'assignment_id' in attempt._fields else a
            a = a or self.env['ts.assignment'].sudo().search([('attempt_id', '=', attempt.id)], limit=1)
        ev = self.env['ts.usage.event'].sudo().search([('attempt_id', '=', attempt.id)], limit=1) if attempt else False
        return Txn.create({
            'wallet_id': self.id, 'type': type_, 'amount': amount, 'units': units, 'idem_key': idem_key,
            'reason_code': reason, 'attempt_id': attempt.id if attempt else False,
            'assignment_id': a.id if a else False, 'usage_event_id': ev.id if ev else False,
            'move_id': move.id if move else False,
            'actor_id': (actor or self.env.user).id, 'balance_after': before + amount,
            'free': (self.workspace_id.billing_mode != 'prepaid') if free is None else free,
        })

    @api.model
    def _key_exists(self, key):
        return bool(self.env['ts.wallet.txn'].sudo().search_count([('idem_key', '=', key)]))

    # ------------------------------------------------------------------ 5.1 hold at invitation
    def ts_hold(self, assignment, price, member, product=None):
        """Lock, check (available, then the member's monthly cap), post the hold and write price_held. Raises CreditRefused."""
        self.ensure_one()
        ws = self.workspace_id
        price = rial_int(price)
        self._lock()
        if self._key_exists('hold:%d' % assignment.id):
            return False
        available = self.ts_available()
        if available < price:
            raise CreditRefused(self.ts_refusal_insufficient(ws, available, price, member or None), 'insufficient', ws,
                                price, member)
        if member and member.role in CAPPED_ROLES and member.monthly_cap > 0:
            committed = self.ts_month_spend(member)
            cap = rial_int(member.monthly_cap)
            if committed + price > cap:
                raise CreditRefused(self.ts_refusal_cap(ws, price, cap - committed), 'cap', ws, price, member)
        row = self._post('hold', -price, 0, 'hold:%d' % assignment.id, 'invite', assignment=assignment, free=False)
        assignment.sudo().write({'price_held': price, 'priced_product_id': product.id if product else False})
        self.env['ts.audit.event'].sudo().log('credit.hold', assignment, workspace=ws, member=member or None, amount=price,
                                              assignment=assignment.id)
        self._ts_low_balance_check()   # a hold lowers the available credit too
        return row

    def ts_release(self, assignment, reason):
        """Give an unconverted hold back (withdraw, decline, expiry). Once: returns the new row or False."""
        self.ensure_one()
        a = assignment.sudo()
        if not a.price_held:
            return False
        self._lock()
        if not self._key_exists('hold:%d' % a.id) or self._key_exists('release:%d' % a.id):
            return False
        row = self._post('release', a.price_held, 0, 'release:%d' % a.id, reason, assignment=a, free=False)
        self.env['ts.audit.event'].sudo().log('credit.release', a, workspace=self.workspace_id, amount=rial_int(a.price_held),
                                              reason=reason)
        return row

    # ------------------------------------------------------------------ 5.2 charge at completion
    def _debit_usage(self, attempt):
        """Single: the hold of the invitation is converted (release + debit of the held price). Battery: the first attempt to
        finish converts the whole battery price; later attempts debit 0. Free / unpriced / already converted: debit 0."""
        self.ensure_one()
        key = 'usage:%d' % attempt.id
        self._lock()
        old = self.env['ts.wallet.txn'].sudo().search([('idem_key', '=', key)], limit=1)
        if old:
            return old
        at = attempt.sudo()
        a = at.assignment_id if 'assignment_id' in at._fields else self.env['ts.assignment']
        a = a or self.env['ts.assignment'].sudo().search([('attempt_id', '=', at.id)], limit=1)
        free = self.workspace_id.billing_mode != 'prepaid'
        if a and a.price_held > 0 and self._key_exists('hold:%d' % a.id) and not self._key_exists('release:%d' % a.id):
            price = rial_int(a.price_held)
            self._post('release', price, 0, 'release:%d' % a.id, 'completion', assignment=a, free=False)
            row = self._post('debit_usage', -price, 1, key, 'completion', at, assignment=a, free=False)
            self.env['ts.audit.event'].sudo().log('credit.debit', a, workspace=self.workspace_id, amount=price,
                                                  attempt=at.id, assignment=a.id)
            self._ts_low_balance_check()
            return row
        return self._post('debit_usage', 0, 1, key, 'completion', at, assignment=a or None, free=free)

    # ------------------------------------------------------------------ 6 low balance
    def _ts_low_balance_check(self):
        self.ensure_one()
        if self.low_threshold > 0 and self.ts_available() < self.low_threshold:
            self._ts_low_balance_notify()

    def _ts_low_balance_notify(self, force=False):
        """One in-app notification `low_balance` to the members with credits:read, at most once per 24 h per wallet.
        `force`: also when no threshold is set (an open link that could not hold its price)."""
        self.ensure_one()
        w = self.sudo()
        available = w.ts_available()
        if not force and not (w.low_threshold > 0 and available < w.low_threshold):
            return False
        now = fields.Datetime.now()
        if w.low_alert_sent_on and w.low_alert_sent_on > now - timedelta(hours=24):
            return False
        ws = w.workspace_id
        N = self.env['ts.notification'].sudo()
        url = '/my/workspaces/%s/credits' % ws.id
        title = LOW_TEXT % (ws.name, fmt_toman(available))
        sent = 0
        for m in ws.member_ids.filtered(lambda x: x.active):
            if m.has_perm('credits:read'):
                row = N._notify(m.user_id, 'low_balance', url, ws)
                if row:
                    row.title = title
                    sent += 1
        w.low_alert_sent_on = now
        self.env['ts.audit.event'].sudo().log('credit.low_balance', ws, workspace=ws, amount=available, recipients=sent)
        return sent

    def ts_set_threshold(self, by, amount):
        """Owner side of the credits page (credits:manage). Rial, multiple of 10, 0 = off."""
        self.ensure_one()
        if not by.has_perm('credits:manage') or by.workspace_id != self.workspace_id:
            raise UserError('آستانهٔ هشدار را %s تعیین می‌کند.' % credit_roles(self.workspace_id.purpose, 'یا'))
        amount = rial_int(amount)
        if amount < 0 or amount % 10:
            raise UserError('آستانه را به ریال و مضربی از ۱۰ بنویسید؛ ۰ یعنی خاموش.')
        old = rial_int(self.low_threshold)
        if old == amount:
            return False
        self.sudo().write({'low_threshold': amount})
        self.env['ts.audit.event'].sudo().log('credit.threshold_change', self.workspace_id, workspace=self.workspace_id,
                                              member=by, old=old, new=amount)
        return True

    # ------------------------------------------------------------------ back office
    def ts_grant(self, amount, reason, actor=None):
        if rial_int(amount) % 10:
            raise UserError('مبلغ را به ریال و مضربی از ۱۰ بنویسید.')
        return super().ts_grant(rial_int(amount), reason, actor=actor)

    def ts_adjust(self, amount, reason, actor=None):
        if rial_int(amount) % 10:
            raise UserError('مبلغ را به ریال و مضربی از ۱۰ بنویسید.')
        return super().ts_adjust(rial_int(amount), reason, actor=actor)

    def action_ts_grant_wizard(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'ts.wallet.grant.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_wallet_id': self.id}}

    # ------------------------------------------------------------------ 7 company currency (one-off, guarded)
    @api.model
    def _ts_switch_company_currency(self):
        """Company 1 USD -> IRR when nothing in accounting exists yet. Never raises during install. Returns a short verdict."""
        company = self.env['res.company'].sudo().browse(1).exists()
        if not company:
            return 'skipped:no-company'
        cur = company.currency_id
        if cur.name == 'IRR':
            return 'already'
        if cur.name != 'USD':
            _logger.warning('ts_billing: company currency is %s, not USD; currency switch skipped', cur.name)
            return 'skipped:not-usd'
        self.env.flush_all()
        cr = self.env.cr
        cr.execute('SELECT (SELECT COUNT(*) FROM account_move), (SELECT COUNT(*) FROM account_move_line), '
                   '(SELECT COUNT(*) FROM product_template WHERE list_price != 0)')
        moves, lines, priced = cr.fetchone()
        if moves or lines or priced:
            _logger.warning('ts_billing: currency switch skipped (account.move %s, account.move.line %s, priced products %s)',
                            moves, lines, priced)
            return 'skipped:accounting'
        irr = self.env.ref('base.IRR', raise_if_not_found=False)
        if not irr:
            _logger.warning('ts_billing: currency IRR not found; switch skipped')
            return 'skipped:no-irr'
        try:
            with cr.savepoint():
                irr = irr.sudo()
                irr.write({'active': True, 'rounding': 1.0, 'position': 'after'})   # decimal_places follows rounding
                company.write({'currency_id': irr.id})
        except Exception as e:      # noqa: BLE001 - never fail an install on this
            _logger.warning('ts_billing: currency switch refused: %s', e)
            return 'skipped:refused'
        self.env['ts.audit.event'].sudo().log('billing.currency_switch', company, old='USD', new='IRR')
        _logger.info('ts_billing: company 1 currency switched USD -> IRR')
        return 'switched'


class TsWalletTxn(models.Model):
    _inherit = 'ts.wallet.txn'

    type = fields.Selection(selection_add=NEW_TYPES, ondelete={k: 'cascade' for k, _l in NEW_TYPES})
    reason_code = fields.Selection(selection_add=NEW_REASONS, ondelete={k: 'set null' for k, _l in NEW_REASONS})
    currency_id = fields.Many2one('res.currency', related='wallet_id.workspace_id.company_id.currency_id', string='ارز')
    amount = fields.Monetary(required=True, currency_field='currency_id')
    balance_after = fields.Monetary(currency_field='currency_id')
    move_id = fields.Many2one('account.move', 'فاکتور', ondelete='set null', index=True)
