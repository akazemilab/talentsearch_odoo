{
    'name': 'Talent Search - onboarding (one-tap invitations, test first, the first session inside a panel)',
    'summary': 'onb2 (docs/onboarding/02_invites_and_guest.md): invitation welcome screen with one-tap consent, sign-in '
               'scoped to one invitation by the SMS or e-mail that carried the link, device binding with a masked-number '
               'code, 12-character short links with a rate limit, fairness questions at the end, one consent screen for '
               'minors; a starter test answered before any account, the result kept with the mobile number, funnel '
               'events without personal data. onb3 (docs/onboarding/03_panel_first_session.md): kind-driven starter, '
               'the member\'s own try-out, sample reports, «شروع کار», one-screen invitation with a permanent link, guide '
               'SMS, audience pages, activation events',
    'version': '20.0.2.3.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_hire', 'ts_sms', 'website'],
    'data': [
        'security/ir.access.csv',
        'data/cron.xml',
        'data/starter.xml',
        'views/backend.xml',
        'views/web_welcome.xml',
        'views/web_guest.xml',
        'views/web_entry.xml',
        'data/onb3_data.xml',
        'views/web_onb3_panel.xml',
        'views/web_services.xml',
    ],
    'assets': {
        # the website-4 bundles only (never web.assets_frontend, shared with eot.ir)
        'ts_website.assets_ts': ['ts_onboard/static/src/scss/onboard.scss'],
    },
    'installable': True,
}
