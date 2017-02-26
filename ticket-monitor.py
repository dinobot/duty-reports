import httplib
import urllib
from time import sleep
from json import dumps, loads
from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from optparse import OptionParser
from unidecode import unidecode

# Adding command line parameters
oparser = OptionParser()
oparser.add_option('-c', '--config', dest='conffile',
                   help='path to config file', metavar='FILENAME')
(options, args) = oparser.parse_args()

# Reading and parsing configuration
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
poll_rate = int(parser.get('misc', 'monitor_poll_minutes'))
shift_url = parser.get('misc', 'shift_status_json_url')

# Wait times in minutes for Sev 1, 2, 3 and 4
# respectively before notifying again
sev_wait = [5, 20, 40, 80]

ntickets = {}

# Opening session with SalesForce
sf = Salesforce(custom_url=sf_url, username=sf_usr, password=sf_pwd,
                security_token=sf_tkn)


# A function for sending messages to Slack incoming hook
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


# Main loop for processing tickets
while True:
    # In case we don't find some known tickets in the list,
    # we mark them as not new anymore
    for t in ntickets:
        ntickets[t]['stillnew'] = False

    # Searching for all tickets with "New" status and processing
    for case in sf.query(("SELECT Id, Subject, Severity_Level__c, "
                          "CaseNumber, AccountId FROM Case WHERE "
                          "Status = 'New'"))['records']:
        if case['Id'] in ntickets:
            # If the ticket is already already known...

            if case['Severity_Level__c'] is not None:
                nsev = int(case['Severity_Level__c'][-1])
            else:
                print("%s is an alert and has no severity. Treating as Sev3" %
                      case['CaseNumber'])
                nsev = 3

            ntickets[case['Id']]['stillnew'] = True
            ntickets[case['Id']]['wait'] += poll_rate

            if ntickets[case['Id']]['wait'] >= sev_wait[nsev-1]:
                # The ticket was new for longer than it should have been.
                # Notifying again!

                print(("A Sev %d ticket is still new (%d min since last "
                       "notification), sending notification again (%s: %s)") %
                      (nsev,
                       ntickets[case['Id']]['wait'],
                       case['CaseNumber'],
                       case['Subject']))
                try:
                    # Trying to get information about current workload
                    # from another script and suggest engineers...

                    url = urllib.urlopen(shift_url)
                    stats = loads(url.read())
                    if len(stats) > 1:
                        del(stats['timestamp'])
                        suggest = ', '.join(sorted(stats, key=lambda k:
                                            len(stats[k]), reverse=False)[0:3])
                        message = ("<!here> %s #*%s* <%s|%s> is still New! "
                                   "Possible owners: %s") %\
                                  (case['Severity_Level__c'],
                                   case['CaseNumber'],
                                   ntickets[case['Id']]['url'],
                                   ntickets[case['Id']]['title'],
                                   suggest)
                except:
                    # If getting suggestion fails, sending simple notification

                    message = ("<!here> A %s ticket is still New! #*%s* "
                               "<%s|%s>") % (case['Severity_Level__c'],
                                             case['CaseNumber'],
                                             ntickets[case['Id']]['url'],
                                             ntickets[case['Id']]['title'])

                slack_send("New Ticket Warning",
                           ":warning:",
                           message
                           )

                ntickets[case['Id']]['wait'] = 0
            else:
                # The ticket has not been waiting enough
                # to be notified about again.

                print(("Still new ticket, but too early to notify again "
                       "(waited %d out of %d)... Sev %d, (%s: %s)") %
                      (ntickets[case['Id']]['wait'],
                       sev_wait[nsev-1],
                       nsev,
                       case['CaseNumber'],
                       case['Subject']))
        else:
            # If this is a new ticket we don't know yet about...

            if case['Subject'] is not None:        # Preventing TypeError crash
                print("Found new ticket, recording and notifying (%s: %s)" %
                      (case['CaseNumber'], case['Subject']))

                # Looking up the customer's name
                customer = None
                for account in sf.query(("SELECT Name FROM Account "
                                         "WHERE Id = '%s'") %
                                        case['AccountId'])['records']:
                    customer = account['Name']
                if customer is not None:
                    print("Determined customer: %s" % customer)

                # Recording some ticket info for later use
                ntickets[case['Id']] = {'title':
                                        unidecode(case['Subject']).
                                        translate(None, '{}["]'),
                                        'url': sf_url + '/console#%2f' +
                                        case['Id'],
                                        'wait': 0, 'stillnew': True,
                                        'uid': case['Id'],
                                        'customer': customer,
                                        'number': case['CaseNumber']}

                # Finally, sending notification
                slack_send("New Ticket Notification",
                           ":ticket:",
                           "A new %s ticket is here! #*%s* [_%s_] <%s|%s>" %
                           (case['Severity_Level__c'],
                            case['CaseNumber'],
                            ntickets[case['Id']]['customer'],
                            ntickets[case['Id']]['url'],
                            ntickets[case['Id']]['title'])
                           )
            else:
                continue

    # Searching for tickets that were moved from "New"
    to_del = []
    for t in ntickets:
        if not ntickets[t]['stillnew']:
            # Determining assignee name (user or group)
            owner_id = sf.query("SELECT OwnerId FROM Case WHERE Id = '%s'" %
                                str(ntickets[t]['uid'])
                                )['records'].pop().get('OwnerId', None)
            owner = None
            for user in sf.query("SELECT Name FROM User WHERE Id = '%s'" %
                                 owner_id)['records']:
                owner = user['Name']
            for group in sf.query("SELECT Name FROM Group WHERE Id = '%s'" %
                                  owner_id)['records']:
                owner = group['Name']

            print("%s is not new anymore. Removing and notifying" %
                  ntickets[t]['title'])

            # Sending notification about ticket being handled
            message = "Case #*%s* <%s|%s> moved FROM New (assigned to *%s*)" %\
                      (ntickets[t]['number'],
                       ntickets[t]['url'],
                       ntickets[t]['title'],
                       owner)
            slack_send("Case Handled",
                       ":ok:",
                       message
                       )

            to_del.append(t)

    # Finally, removing not "New" tickets from memory
    for t in to_del:
        del ntickets[t]
    del to_del

    print("Sleeping %d minutes..." % poll_rate)
    sleep(poll_rate * 60)
