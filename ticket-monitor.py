import httplib
import urllib
from time import sleep
from json import dumps
from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from engineers import engineers, ids
from optparse import OptionParser

oparser = OptionParser()
oparser.add_option('-c', '--config', dest='conffile', help='path to config file', metavar='FILENAME')
(options, args) = oparser.parse_args()

parser = SafeConfigParser()

if options.conffile is not None:
    parser.read(options.conffile)
else:
    parser.read('salesforce.conf')

sf_url = parser.get('SalesForce', 'url')
sf_usr = parser.get('SalesForce', 'username')
sf_pwd = parser.get('SalesForce', 'password')
sf_tkn = parser.get('SalesForce', 'token')
slack_hook = parser.get('Slack', 'monitor_hook_url')
shift_url = parser.get('misc', 'shift_status_json_url')

sev_wait = [5, 20, 40, 80]

ntickets = {}

sf = Salesforce(custom_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)

def slack_send(username, icon_emoji, text):
    params = dumps({"username": username,
                    "icon_emoji": icon_emoji,
                    "text": text
                    })
    conn = httplib.HTTPSConnection("hooks.slack.com")
    conn.request("POST", slack_hook, params)
    res = conn.getresponse()
    conn.close()
    return res.status, res.reason


def prepare_json_data(json_data):
    json_data_string = ''
    for c in json_data:
        if c in '{}["]':
            c = ' '
        json_data_string = json_data_string + c
    return json_data_string


while True:
    for t in ntickets:
        ntickets[t]['stillnew'] = False

    for case in sf.query("SELECT Id, Subject, Severity_Level__c, CaseNumber from Case where Status = 'New'")['records']:
        if case['Id'] in ntickets:
            if case['Severity_Level__c'] is not None:
                nsev = int(case['Severity_Level__c'][-1])
            else:
                print("%s is an alert and has no severity. Treating as Sev3" % case['CaseNumber'])
                nsev = 3
            ntickets[case['Id']]['stillnew'] = True
            ntickets[case['Id']]['wait'] += 5
            if ntickets[case['Id']]['wait'] >= sev_wait[nsev-1]:
                print("A Sev %d ticket is still new (%d min since last notification), sending notification again (%s: %s)" %
                      (nsev, ntickets[case['Id']]['wait'], case['CaseNumber'], case['Subject']))
                try:
                    url = urllib.urlopen(shift_url)
                    stats=jslon.loads(url.read())
                    if len(stats) > 1:
                        del(stats['timestamp'])
                        suggest = sorted(stats, key=lambda k: len(stats[k]), reverse=False)[0]
                        message = "<!here> %s should take care of %s.  <%s|%s>" % (suggest,
                                                                                   case['CaseNumber'],
                                                                                   ntickets[case['Id']]['url'],
                                                                                   ntickets[case['Id']]['title'])
                except:
                    message = "<!here> A %s ticket is still New! #%s <%s|%s>" % (case['Severity_Level__c'],
                                                                                 case['CaseNumber'],
                                                                                 ntickets[case['Id']]['url'],
                                                                                 ntickets[case['Id']]['title'])
                slack_send("New Ticket Warning",
                           ":warning:",
                           message
                           )

                ntickets[case['Id']]['wait'] = 0
            else:
                print("Still new ticket, but too early to notify again (waited %d out of %d)... Sev %d, (%s: %s)" %
                      (ntickets[case['Id']]['wait'], sev_wait[nsev-1], nsev, case['CaseNumber'], case['Subject']))
        else:
            print("Found new ticket, recording and notifying (%s: %s)" % (case['CaseNumber'], case['Subject']))

            ntickets[case['Id']] = {'title': prepare_json_data(case['Subject']), 'url': sf_url + '/console#%2f' + case['Id'], 'wait': 0, 'stillnew': True, 'uid': case['Id']}
            url = sf_url + '/console#%2f' + case['Id']

            slack_send("New Ticket Notification",
                       ":ticket:",
                       "A new %s ticket is here! #%s <%s|%s>" %
                       (case['Severity_Level__c'], case['CaseNumber'], ntickets[case['Id']]['url'], ntickets[case['Id']]['title'])
                       )

    to_del = []
    for t in ntickets:
        if not ntickets[t]['stillnew']:

            owner_id = sf.query("SELECT OwnerId from Case where Id = '"+str(ntickets[t]['uid'])+"'")['records'].pop().get('OwnerId', None)
            for email, user_id in ids.iteritems():
                if owner_id == user_id:
                    case_owner = engineers[email]
                    break
                else:
                    case_owner = None

            slack_send("Case assigned",
                       ":ticket:",
                       "A new ticket %s is assigned to %s" %
                       (ntickets[case['Id']]['title'], case_owner)
                       )

            to_del.append(t)
    for t in to_del:
        del ntickets[t]
    del to_del

    print("Sleeping 5 minutes...")
    sleep(300)
