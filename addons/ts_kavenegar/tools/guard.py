"""Clones never text anyone (onb3 risk review).

A clone is restored from a dump of the live database, so it carries the live Kavenegar key and settings, and the live
Odoo server also runs its scheduled actions on every clone database. Two layers keep every SMS of a clone away from real
phones:

1. tools/prod/ts_db.sh (clone step) switches Kavenegar off, blanks the key, points `ts_kavenegar.api_base` at a closed
   local port and points Odoo's own SMS and IAP endpoints there too.
2. This guard, in code: an SMS leaves only from the live database (`ts_kavenegar.live_db`, default eot_main), or, on any
   other database, only to a local fake gateway (the test suites start one on 127.0.0.1). It sits on every send path:
   the Kavenegar client (`res.company._kv_client`: SMS, OTP lookups, account calls), the sms.sms queue
   (`sms.sms._split_by_api`, Kavenegar and Odoo IAP alike) and the Talent Search notification helper.
"""
LIVE_DB_PARAM = 'ts_kavenegar.live_db'
LIVE_DB_DEFAULT = 'eot_main'
LOCAL_PREFIXES = ('http://127.0.0.1:', 'http://localhost:')
CLONE_API_BASE = 'http://127.0.0.1:9/v1/%s/%s.json'      # a closed local port: what ts_db.sh sets on every clone


def is_live_db(env):
    """True on the production database only."""
    want = (env['ir.config_parameter'].sudo().get_str(LIVE_DB_PARAM) or '').strip() or LIVE_DB_DEFAULT
    return env.cr.dbname == want


def local_gateway(env):
    """True when the Kavenegar address of this database is a local fake (the test suites)."""
    base = (env['ir.config_parameter'].sudo().get_str('ts_kavenegar.api_base') or '').strip()
    return base.startswith(LOCAL_PREFIXES)


def sms_route_allowed(env):
    """May this database hand an SMS to the Kavenegar client? The live database, or any database whose gateway is a
    local fake. Odoo's own IAP SMS route is allowed on the live database only (see sms.sms._split_by_api)."""
    return is_live_db(env) or local_gateway(env)
