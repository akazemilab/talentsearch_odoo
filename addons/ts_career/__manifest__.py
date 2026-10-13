{
    'name': 'Talent Search - free career match',
    'summary': 'Free personal career match (person -> 923 O*NET occupations): Persian O*NET Interest Profiler (60), '
               'education and experience (job zone), optional work styles (personal IPIP-HEXACO copy) and ability tasks, '
               'CAREER-MATCH engine (quick and full tiers), /career pages, daily cap of new free runs',
    'version': '20.0.1.1.0',
    'category': 'Services/Talent Search',
    'author': 'EOT',
    'license': 'LGPL-3',
    'depends': ['ts_onboard'],
    'data': [
        'security/ir.access.csv',
        'views/web_career.xml',
        'data/load.xml',
    ],
    'assets': {
        'ts_website.assets_ts': ['ts_career/static/src/scss/career.scss'],
    },
    'installable': True,
}
