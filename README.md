# talentsearch_odoo

Talent Search (talentsearch.ir) by EOT: Odoo 20 modules served as **website 2**
inside the `eot_main` database on eot-odoo-prod, next to eot.ir (website 1).

- `addons/` - Talent Search modules (`ts_*`), deployed to /opt/odoo/talentsearch/addons
- `tools/vps/ts` - VPS toolkit (sync, clone, install, serve, guard, push)
- `tools/prod/ts_db.sh` - clone / install / upgrade / serve / stop (refuses eot_main unless TS_LIVE=1)
- `tools/prod/ts_guard.py` - proves eot.ir is unchanged: fingerprints website-1/generic rows and every rendered eot.ir page before and after a change

Hard rule: nothing here may modify eot.ir (website 1) views, pages, menus, redirects, theme or DNS.
Every install/upgrade is rehearsed on an `eot_ts*` clone and must pass `ts guard compare` first.
