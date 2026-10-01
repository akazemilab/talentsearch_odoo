"""Panel v2 S1: M1 (audit rows get ip_hash, the raw address is removed) and M2 (owner_practices for solo panels).
Idempotent; prints counts only."""
import logging
import secrets

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # M1 ---------------------------------------------------------------------------------------------------
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = 'ts_core.audit_ip_salt'")
    row = cr.fetchone()
    if row:
        salt = row[0]
    else:
        salt = secrets.token_hex(16)
        cr.execute("INSERT INTO ir_config_parameter (key, value, create_date, write_date, create_uid, write_uid) "
                   "VALUES ('ts_core.audit_ip_salt', %s, now(), now(), 1, 1)", [salt])
    cr.execute("""UPDATE ts_audit_event SET ip_hash = substr(encode(sha256(convert_to(%s || ip_address, 'UTF8')), 'hex'), 1, 16)
                  WHERE ip_address IS NOT NULL AND ip_hash IS NULL""", [salt])
    hashed = cr.rowcount
    cr.execute("UPDATE ts_audit_event SET ip_address = NULL WHERE ip_address IS NOT NULL")
    _logger.info('ts_core 20.0.1.1.0 M1: %d audit rows hashed, %d raw addresses removed', hashed, cr.rowcount)
    # M2 ---------------------------------------------------------------------------------------------------
    cr.execute("""
        UPDATE ts_workspace_member m SET owner_practices = TRUE
        FROM ts_audit_event a
        WHERE a.event_type = 'workspace.self_create' AND a.res_id = m.workspace_id AND m.role = 'owner'
          AND a.detail LIKE '{%%' AND (a.detail::jsonb ->> 'kind') = 'solo' AND m.owner_practices IS NOT TRUE""")
    _logger.info('ts_core 20.0.1.1.0 M2: %d solo owner(s) marked as practising', cr.rowcount)
