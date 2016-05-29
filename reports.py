from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from datetime import datetime
import xlrd
import sys
from engineers import engineers

crew = []
schedule = []
day_schedule = []

parser = SafeConfigParser()
parser.read('salesforce.conf')

sf_url = parser.get('SalesForce', 'url')
sf_usr = parser.get('SalesForce', 'username')
sf_pwd = parser.get('SalesForce', 'password') 
sf_tkn = parser.get('SalesForce', 'token')

sf = Salesforce(custom_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)

time = datetime.now()
sf_engineers = []
active_cases = []
active_sev1s = []

rb = xlrd.open_workbook('Duty list 2016.xlsx')
sheet = rb.sheet_by_index(0)

day = datetime.now().strftime("%d")
daytime = sys.argv[1]

result = ''
n = 0

def duty(date, daytime):
  for i in sch():
    if i.get(date):
      if i[date].get(daytime):
        return i[date].get(daytime)

def nicename(name):
   for nn in engineers:
     if name in nn:
       return nn

def reverse_daytime(daytime):
    if daytime == 'day':
      reverse_d = 'night'
    else:
      reverse_d = 'day'
    return reverse_d

def sch():
    for rownum in range(sheet.nrows)[2:]:
      row = sheet.row_values(rownum)
      if row[2] == 'day' or row[2] == 'night':
        if row[1]:
          day_date = int(row[1])
        day_part = row[2]
        sched = row[3:len(crew)+3]
        day_crew = []
        for person,shift in zip(crew, sched):
          if shift:
            day_crew.append(person)
        schedule.append({day_date:{day_part:day_crew}})
    return schedule 

for e in sheet.row_values(1):
    if e and e not in 'Date':
      crew.append(e)

for engineer in duty(int(day), daytime) or []:
    if n < (len(duty(int(day), daytime)) - 2):
      delimeter = ', '
    elif n == (len(duty(int(day), daytime)) - 2):
      delimeter = ' and '
    elif n >= 1:
      delimeter = ' are on-shift next'
    else:
      delimeter = ' is on-shift next'
    n+=1
    result = result + nicename(engineer) + delimeter

for engineer in sf.query("SELECT name,id from User")['records']:
    sf_engineers.append({engineer['Id']: engineer['Name']})

for case in sf.query("SELECT CaseNumber,L2__c,Summary__c,SLA_resolution_time__c,status,OwnerID,Severity_Level__c,Subject,LastModifiedDate,LastModifiedById from Case where status = 'Open' or status = 'New' or status = 'Pending'")['records']:

    severity = case['Severity_Level__c']
    status = case['Status']
    L2 = case['L2__c']
    case_id = case['CaseNumber']
    owner_id = case['OwnerId']
    modified = case['LastModifiedDate'].split('.')[0]

# override empty subjects
    if case['Subject']:
        subject = case['Subject']
    else:
        subject = '(Empty Subject)'

    if case['Summary__c']:
        escalation_message = case['Summary__c']
    else:
        escalation_message = ''

    if owner_id and owner_id != '00GE0000002uhYhMAI' and owner_id != '00GE0000003YOIEMA4':
          case_owner = str([str(name[owner_id]) for name in sf_engineers if name.get(owner_id)])[2:-2]
    else:
          case_owner = '[UNASSIGNED]'

# process all new & open
    if status not in 'Pending' and severity not in 'Sev 1':
      case_meta = { 
          'id' : case_id,
          'status' : status,
          'severity_level' : severity,
          'subject' : subject,
          'responsible' : case_owner,
          }
      active_cases.append(case_meta)

# process recent SEV1's
    if severity in 'Sev 1' and (time - datetime.strptime(modified, "%Y-%m-%dT%H:%M:%S")).seconds < 60*60*12:
      sev1_meta = {
          'id' : case_id,
          'status' : status,
          'subject' : subject,
          'responsible' : case_owner,
          'message' : escalation_message,
          'l2': L2
          }
      active_sev1s.append(sev1_meta)

print 'Duty report,', reverse_daytime(daytime), datetime.now().date(), '\n'

if active_sev1s:
  print 'Sev1 cases:', '\n'
  for sev1 in active_sev1s:
    print '  L2:', sev1['l2']
    print ' ',', '.join([sev1['id'], sev1['status'], sev1['subject']])
    print '  Owned by', sev1['responsible'], '\n'
    if sev1['message']:
      print sev1['message'], '\n'
else:
    print 'Currently we have no SEV1 tickets'

if active_cases:
    print 'Active cases:', '\n'
    for c in active_cases:
      print ', '.join([c['id'], c['status'], c['subject'], c['responsible']])

if result:
    print '\n', result
else:
    print '\n', 'No European engineers scheduled for', datetime.now().date(), daytime
