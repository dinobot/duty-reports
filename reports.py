import httplib2
from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from datetime import datetime, timedelta
import xlrd
import sys
from jinja2 import Environment, PackageLoader
from engineers import engineers
import sqlite3
from lumpy import Mail
from unidecode import unidecode
from apiclient import discovery

from calendarapi import get_credentials


conn = sqlite3.connect('archive.db')
c = conn.cursor()

env = Environment(loader=PackageLoader('duty-reports', 'templates'))

crew = []
schedule = []
day_schedule = []

parser = SafeConfigParser()
parser.read('salesforce.conf')

sf_url = parser.get('SalesForce', 'url')
sf_usr = parser.get('SalesForce', 'username')
sf_pwd = parser.get('SalesForce', 'password') 
sf_tkn = parser.get('SalesForce', 'token')

sender_email = parser.get('EMail', 'sender')
reciever_email = parser.get('EMail', 'reciever')

calendar_id = parser.get('calendar', 'id')

sf = Salesforce(custom_url=sf_url,
                username=sf_usr,
                password=sf_pwd,
                security_token=sf_tkn)

time = datetime.now()
sf_engineers = []
active_cases = []
active_sev1s = []

rb = xlrd.open_workbook('Duty list 2016.xlsx')
sheet = rb.sheet_by_index(0)

day = datetime.now().strftime("%d")
daytime = sys.argv[1]
date = str(datetime.now().date())

next_on_duty = ''
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

def daynight(hour):
    if hour > 12:
      day = 1
    else:
      day = 0
    return day

def webexes():
    w = []
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)

    now = datetime.utcnow().isoformat()+'Z'
    then = (datetime.utcnow()+timedelta(hours=12)).isoformat()+'Z'

    eventsResult = service.events().list(
        calendarId=calendar_id, timeMin=now, singleEvents = True,
        timeMax=then,orderBy='startTime').execute()
    events = eventsResult.get('items', [])

    for event in events:
        time = event['start'].get('dateTime', '')[11:]
        if 'webex' in event.get('location', '').lower() or 'webex' in event['summary'].lower():
            w.append({'time': time,'title': event['summary']})
    return w

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
    next_on_duty = next_on_duty + nicename(engineer) + delimeter

for engineer in sf.query("SELECT name,id from User")['records']:
    sf_engineers.append({engineer['Id']: engineer['Name']})

for case in sf.query("SELECT Id,CaseNumber,L2__c,Summary__c,SLA_resolution_time__c,status,OwnerID,Severity_Level__c,Subject,LastModifiedDate,LastModifiedById,Launch_Pad_URL_1__c,Launch_Pad_URL_2__c,Launch_Pad_URL_3__c,Launch_Pad_URL_4__c  from Case where status = 'Open' or status = 'New' or status = 'Pending' or status = 'On Hold'")['records']:
    severity = case['Severity_Level__c']
    uuid = case['Id']
    status = case['Status']
    case_id = case['CaseNumber']
    owner_id = case['OwnerId']
    modified = case['LastModifiedDate'].split('.')[0]
    linked_bugs = []
    if case['Launch_Pad_URL_1__c']:
        for n in range(1,5):
            linked_bugs.append(case['Launch_Pad_URL_'+str(n)+'__c'])
    if case['L2__c']:
       queue = 'L2' 
    else:
       queue = 'L1'

# override empty subjects
    if case['Subject']:
        subject = unidecode(case['Subject'])
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
    if status in 'New' or status in 'Open' and severity not in 'Sev 1':
      case_meta = { 
          'id' : case_id,
          'status' : status,
          'severity_level' : severity,
          'subject' : subject,
          'responsible' : case_owner,
          'uuid': uuid,
          'bug': linked_bugs
          }
      active_cases.append(case_meta)

# process recent SEV1's
    if severity in 'Sev 1':
      sev1_meta = {
          'id' : case_id,
          'status' : status,
          'subject' : subject,
          'responsible' : case_owner,
          'message' : escalation_message,
          'queue': queue,
          'uuid': uuid,
          'bug': linked_bugs
          }
      active_sev1s.append(sev1_meta)


template = env.get_template('report.html')

message = template.render(urgent = active_sev1s,
                          url=sf_url,
                          ac=active_cases,
                          engineers = next_on_duty,
                          date = date,
                          shift = daytime,
                          webexes = webexes())
c.execute("INSERT INTO reports VALUES(null, ?, ?, ?)",  (date, message.replace('\n', ''), daynight(datetime.now().hour)))

conn.commit()
conn.close()

m = Mail(reciever_email, sender=sender_email, subject = 'Duty report, %s, %s' % (reverse_daytime(daytime), date), body=message, content = 'html')
m.send()
