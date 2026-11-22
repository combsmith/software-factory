"""The mutants of `sonar-project.properties`: tools/mutants.py runs them."""

TARGETS = ("sonar-project.properties",)
MUTANTS = [
    # A change to a path only a person decides waits under its own code (issue 746, decision 0207).
    ("Sonar's traversal rule is set aside for every file", 'sonar-project.properties',
     'sonar.issue.ignore.multicriteria.transportpath.resourceKey=adapters/github.py',
     'sonar.issue.ignore.multicriteria.transportpath.resourceKey=**/*', ('tests.test_adapters.Transport.test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect',)),
    ("Sonar's traversal rule is set aside under a name its list does not hold", 'sonar-project.properties',
     'sonar.issue.ignore.multicriteria=p50stubhttp,p50stubxss,contexttest,trialapptest,transportpath\n',
     'sonar.issue.ignore.multicriteria=p50stubhttp,p50stubxss,contexttest,trialapptest\n', ('tests.test_adapters.Transport.test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect',)),
    ("a second line sets Sonar's traversal rule aside for every file", 'sonar-project.properties',
     'sonar.issue.ignore.multicriteria.transportpath.resourceKey=adapters/github.py',
     'sonar.issue.ignore.multicriteria.transportpath.resourceKey=adapters/github.py\nsonar.issue.ignore.multicriteria.transportpath.resourceKey=**/*', ('tests.test_adapters.Transport.test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect',)),
    ('a line Sonar reads as the same key sets its traversal rule aside for every file', 'sonar-project.properties',
     'sonar.issue.ignore.multicriteria.transportpath.resourceKey=adapters/github.py',
     'sonar.issue.ignore.multicriteria.transportpath.resourceKey=adapters/github.py\n sonar.issue.ignore.multicriteria.transportpath.resourceKey=**/*', ('tests.test_adapters.Transport.test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect',)),
    ('an entry sets every Sonar rule aside for every file', 'sonar-project.properties',
     'sonar.issue.ignore.multicriteria=p50stubhttp,p50stubxss,contexttest,trialapptest,transportpath\n',
     'sonar.issue.ignore.multicriteria=p50stubhttp,p50stubxss,contexttest,trialapptest,transportpath,all\nsonar.issue.ignore.multicriteria.all.ruleKey=*\nsonar.issue.ignore.multicriteria.all.resourceKey=**/*\n', ('tests.test_adapters.Transport.test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect',)),
    ("Sonar is told to leave the transport's file unread", 'sonar-project.properties',
     'sonar.exclusions=**/node_modules/**,**/vendor/**,**/dist/**\n',
     'sonar.exclusions=**/node_modules/**,**/vendor/**,**/dist/**,adapters/github.py\n', ('tests.test_adapters.Transport.test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect',)),
]
