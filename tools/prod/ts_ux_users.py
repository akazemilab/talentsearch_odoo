#!/usr/bin/env python3
"""Set clone-only passwords for every login in the UX matrix (ts_ux_seed.py output):  ts_ux_users.py DB PORT /tmp/ux_matrix.json"""
import importlib.util, json, os, sys
DB, PORT, F = sys.argv[1], sys.argv[2], sys.argv[3]
assert DB.startswith('eot_ts'), 'clones only'
spec = importlib.util.spec_from_file_location('flowlib', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ts_flowlib.py'))
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
lib.setup(DB, PORT)
logins = [k for k in json.load(open(F)) if k]
for login in logins:
    lib.ensure_user(login)
print('UXUSERS', len(logins))
