"""onb2: the fairness questions moved from the invitation page to the end of the battery. A candidate who accepted before
this version already saw them on the invitation page: they are not asked a second time."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""UPDATE ts_assignment SET ts_fair_asked = TRUE
                   WHERE position_id IS NOT NULL AND user_id IS NOT NULL AND ts_fair_asked IS NOT TRUE""")
