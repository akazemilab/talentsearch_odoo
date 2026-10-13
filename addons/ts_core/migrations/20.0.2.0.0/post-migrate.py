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
    # owners of a counseling center who already counsel show up once in «مالک مشاور شد (بررسی پروانه)»
    cr.execute("""UPDATE ts_workspace_member m SET practising_since = COALESCE(m.write_date, m.create_date)
                  FROM ts_workspace w
                  WHERE m.workspace_id = w.id AND w.purpose = 'clinical' AND m.role = 'owner'
                    AND m.owner_practices IS TRUE AND m.practising_since IS NULL""")
    _logger.info('ts_core 20.0.2.0.0: %d counseling owner(s) listed for a licence review', cr.rowcount)
