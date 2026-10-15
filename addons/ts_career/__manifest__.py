{
    'name': 'Talent Search - free career match',
    'summary': 'Free personal career match (person -> 923 O*NET occupations): Persian O*NET Interest Profiler (60), '
               'education and experience (job zone), optional work styles (personal IPIP-HEXACO copy) and ability tasks, '
               'CAREER-MATCH engine (quick and full tiers), /career pages, daily cap of new free runs; completion '
               '(docs/career/01_completion.md): start before sign-in, one-tap consent, one item at a time, SMS reminders, '
               'funnel steps',
    'version': '20.0.1.2.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_onboard'],
    'data': [
        'security/ir.access.csv',
        'views/web_career.xml',
        'views/web_career_completion.xml',
        'data/load.xml',
        'data/nudge_data.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_career/static/src/scss/career.scss'],
    },
    'installable': True,
}
