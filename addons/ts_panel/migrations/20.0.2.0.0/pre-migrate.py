def migrate(cr, version):
    """S4: responsible_id on invitations and imported results becomes a stored related field of the client.
    Keep the old values in a scratch table so the post-migration can carry them to the clients."""
    cr.execute("DROP TABLE IF EXISTS ts_panel_resp_snap")
    cr.execute("""CREATE TABLE ts_panel_resp_snap AS
                  SELECT 'a'::text AS kind, id, responsible_id FROM ts_assignment WHERE responsible_id IS NOT NULL
                  UNION ALL
                  SELECT 't'::text, id, responsible_id FROM ts_attempt WHERE responsible_id IS NOT NULL""")
