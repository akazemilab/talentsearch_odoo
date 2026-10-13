"""onb3 (ts_onboard 20.0.2.0.0): panels that existed before the release.

* ts_kind: the kind the owner chose («workspace.self_create» audit row), else from the purpose (a counseling panel whose
  only member is a counselling owner is «solo»).
* «شروع کار» (ts_onb_start) stays on only for panels that never sent a real invitation; a panel already at work (live:
  Sepehr, workspace 4; the school panels with invitations) sees its finished state: no start card, no second card.
* Activation marks from real data: first real invitation, first real shared result, and «opened» for a panel that already
  has a finished result. The 7-day team follow-up is marked done for every older panel (it is for new panels).
Sends nothing; idempotent (only empty values are filled).
"""
import json
import logging

_logger = logging.getLogger(__name__)
REAL = "a.ts_preview IS NOT TRUE AND COALESCE(a.channel, 'link') NOT IN ('self_share', 'import', 'preview')"


def migrate(cr, version):
    if not version:
        return
    cr.execute("SELECT res_id, detail FROM ts_audit_event WHERE event_type = 'workspace.self_create' AND res_model = 'ts.workspace'")
    chosen = {}
    for rid, detail in cr.fetchall():
        try:
            k = (json.loads(detail or '{}') or {}).get('kind')
        except ValueError:
            k = None
        if k:
            chosen[rid] = {'school': 'school', 'org': 'hr', 'clinic': 'clinic', 'solo': 'solo'}.get(k)
    cr.execute("SELECT id, purpose FROM ts_workspace WHERE ts_kind IS NULL")
    for wid, purpose in cr.fetchall():
        kind = chosen.get(wid)
        if not kind:
            kind = {'clinical': 'clinic', 'education': 'school', 'employment': 'hr'}.get(purpose)
            if kind == 'clinic':
                cr.execute("SELECT count(*), bool_and(role = 'owner' AND owner_practices IS TRUE) FROM ts_workspace_member "
                           "WHERE workspace_id = %s AND active", [wid])
                n, solo = cr.fetchone()
                if n == 1 and solo:
                    kind = 'solo'
        if kind:
            cr.execute("UPDATE ts_workspace SET ts_kind = %s WHERE id = %s", [kind, wid])
    cr.execute("UPDATE ts_workspace w SET ts_onb_first_invite_at = s.first FROM "
               "(SELECT a.workspace_id, MIN(a.create_date) AS first FROM ts_assignment a WHERE " + REAL +
               " GROUP BY a.workspace_id) s WHERE s.workspace_id = w.id AND w.ts_onb_first_invite_at IS NULL")
    cr.execute("UPDATE ts_workspace w SET ts_onb_result_ready_at = s.first, ts_onb_result_opened_at = COALESCE(w.ts_onb_result_opened_at, s.first) FROM "
               "(SELECT a.workspace_id, MIN(t.submitted_at) AS first FROM ts_assignment a JOIN ts_attempt t ON t.id = a.attempt_id "
               " WHERE a.state = 'done' AND " + REAL + " GROUP BY a.workspace_id) s "
               "WHERE s.workspace_id = w.id AND w.ts_onb_result_ready_at IS NULL")
    # «شروع کار» only for a panel that has not started; every older panel is past the 7-day follow-up
    cr.execute("UPDATE ts_workspace SET ts_onb_start = (ts_onb_first_invite_at IS NULL AND state = 'active'), "
               "ts_onb_followup_at = COALESCE(ts_onb_followup_at, now() AT TIME ZONE 'UTC')")
    cr.execute("SELECT count(*) FILTER (WHERE ts_onb_start), count(*) FROM ts_workspace")
    on, total = cr.fetchone()
    _logger.info('ts_onboard 20.0.2.0.0: kinds set, «شروع کار» on for %s of %s panels', on, total)
