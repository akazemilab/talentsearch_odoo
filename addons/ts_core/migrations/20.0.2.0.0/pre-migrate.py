"""onb1 (owner decision 2026-10-12, "there is no need for approval"):
- every panel waiting in the old «pilot» state (approved or not) becomes «active»; draft, suspended and closed panels
  are left exactly as they are (workspace 2, closed, stays closed);
- the licence check becomes a badge: a member without a licence number no longer shows «pending».
Runs before the new schema (the selection loses 'pilot'). Idempotent; logs counts only."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("SELECT id FROM ts_workspace WHERE state = 'pilot' ORDER BY id")
    ids = [r[0] for r in cr.fetchall()]
    if ids:
        cr.execute("UPDATE ts_workspace SET state = 'active' WHERE id IN %s", [tuple(ids)])
        # one append-only audit row per moved panel (same shape as ts.audit.event.log)
        cr.execute("""INSERT INTO ts_audit_event (event_type, actor_id, res_model, res_id, workspace_id, purpose, detail, outcome,
                                                  create_date, write_date, create_uid, write_uid)
                      SELECT 'workspace.state', 1, 'ts.workspace', id, id, purpose,
                             '{"state": "active", "from": "pilot", "by": "migration onb1 (no approval)"}', 'ok',
                             now() at time zone 'UTC', now() at time zone 'UTC', 1, 1
                      FROM ts_workspace WHERE id IN %s""", [tuple(ids)])
    _logger.info('ts_core 20.0.2.0.0: %d pilot panel(s) moved to active: %s', len(ids), ids)
    cr.execute("""UPDATE ts_workspace_member SET verification_state = 'not_required'
                  WHERE (verification_state IS NULL OR verification_state = 'pending')
                    AND COALESCE(TRIM(license_number), '') = ''""")
    _logger.info('ts_core 20.0.2.0.0: %d member(s) without a licence number set to no badge', cr.rowcount)
