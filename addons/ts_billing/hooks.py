"""Install-time migration (docs/clinic/04_billing_brief.md section 1).

ts_panel created the ledger money columns as int4 (they carried units). ts_billing makes them Monetary (numeric). The ORM does
not cast int4 -> numeric (it would move the old column aside and create an empty one), so the type is changed here, before the
module's models are loaded. Existing rows were free rows (0 or +-1 units, never money): their amount becomes 0 and the running
balances are recomputed (all 0). `units` is untouched (statistics).
"""
import logging

_logger = logging.getLogger(__name__)

MONEY_COLUMNS = [('ts_wallet_txn', 'amount'), ('ts_wallet_txn', 'balance_after'), ('ts_wallet', 'balance'),
                 ('ts_wallet', 'low_threshold')]


def _column_type(cr, table, column):
    cr.execute("SELECT data_type FROM information_schema.columns WHERE table_name = %s AND column_name = %s", [table, column])
    row = cr.fetchone()
    return row[0] if row else None


def pre_init_hook(env):
    cr = env.cr
    changed = []
    for table, column in MONEY_COLUMNS:
        if _column_type(cr, table, column) == 'integer':
            cr.execute('ALTER TABLE "%s" ALTER COLUMN "%s" TYPE numeric USING "%s"::numeric' % (table, column, column))
            changed.append('%s.%s' % (table, column))
    if _column_type(cr, 'ts_wallet_txn', 'amount'):
        # unit rows -> free money rows; a ledger row is never edited through the ORM, so this is SQL, once, at install
        cr.execute("UPDATE ts_wallet_txn SET amount = 0, balance_after = 0 WHERE amount != 0 OR balance_after != 0")
        rows = cr.rowcount
        cr.execute("UPDATE ts_wallet SET balance = 0, low_threshold = 0 WHERE balance != 0 OR low_threshold != 0")
        _logger.info('ts_billing pre_init: columns %s -> numeric; %d ledger row(s) set to amount 0', changed, rows)
