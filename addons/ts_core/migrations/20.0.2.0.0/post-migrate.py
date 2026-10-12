"""onb1: mark the panels customers built themselves at /panel (audit event workspace.self_create), so the new-panel
invitation limit of their first week applies to them only. Idempotent; logs counts only."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""UPDATE ts_workspace w SET self_service = TRUE
                  FROM ts_audit_event a
                  WHERE a.event_type = 'workspace.self_create' AND a.res_model = 'ts.workspace' AND a.res_id = w.id
                    AND w.self_service IS NOT TRUE""")
    _logger.info('ts_core 20.0.2.0.0: %d self-service panel(s) marked', cr.rowcount)
