"""onb1 risk review: the sign-in lock is now kept per (number, hashed address) plus a per-number 24-hour row. The rows only
hold short-lived counters, so a database that already has the first version of the table starts it again (the old
unique(phone) constraint would refuse the new rows). A database without the table (live) is untouched."""


def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS ts_signup_lock CASCADE")
