import httplib2
from apiclient import discovery
from datetime import datetime, timedelta
from calendarapihelper import get_credentials
from engineers import engineers, ids, l2
from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from flask import Flask, request
import json
import time
from flask_apscheduler import APScheduler
import os
import xlrd

import logging
logging.basicConfig()

parser = SafeConfigParser()
parser.read('salesforce.conf')

sf_url = parser.get('SalesForce', 'url')
sf_usr = parser.get('SalesForce', 'username')
sf_pwd = parser.get('SalesForce', 'password')
sf_tkn = parser.get('SalesForce', 'token')

sch_cal_id_us = parser.get('calendar', 'schedule_us')
sch_cal_id_eu = parser.get('calendar', 'schedule_eu')
onc_cal_id = parser.get('calendar', 'on-call-sch')

credentials = get_credentials()
http = credentials.authorize(httplib2.Http())
service = discovery.build('calendar', 'v3', http=http)

class Config(object):
    JOBS = [
        {
            'id': 'job1',
            'func': 'shift_handle:async_job',
            'trigger': 'interval',
            'seconds': 90
        }
    ]

    SCHEDULER_API_ENABLED = True

def async_job():
  sf = Salesforce(instance_url=sf_url,
                  username=sf_usr,
                  password=sf_pwd,
                  security_token=sf_tkn)

  now  = (datetime.utcnow()).isoformat()+'Z'
  then = (datetime.utcnow()+timedelta(minutes=1)).isoformat()+'Z'

  sheet = xlrd.open_workbook('l2.xlsx').sheet_by_index(2)

  shifts_eu = service.events().list(
      calendarId=sch_cal_id_eu, timeMin=now, singleEvents = True,
      timeMax=then,orderBy='startTime',
      timeZone="UTC").execute()

  shifts_us = service.events().list(
      calendarId=sch_cal_id_us, timeMin=now, singleEvents = True,
      timeMax=then,orderBy='startTime',
      timeZone="UTC").execute()

  oncall = service.events().list(
      calendarId=onc_cal_id, timeMin=now, singleEvents = True,
      timeMax=then,orderBy='startTime',
      timeZone="UTC").execute()

  result = {}
  l1_crew = {}
  l2_crew = {}
  l2_off = {}
  crew_keys = []
  on_duty_l1 = []
  on_duty_l2 = ''
  l2_unassigned = []
  l1_unassigned = []
  l1_off = {}
  l2_all = {}

  for event in shifts_eu.get('items',[]):
    if 'shift' in event['summary'].lower():
      key = event['attendees'].pop()['email']
      if key not in crew_keys:
        crew_keys.append(key)

  for event in shifts_us.get('items',[]):
    if 'shift' in event['summary'].lower():
      key = event['attendees'].pop()['email']
      if key not in crew_keys:
        crew_keys.append(key)

  for event in oncall.get('items',[]):
   if 'l1 on call' in event['summary'].lower():
      for e in engineers.values():
         if e in event['summary']:
           on_duty_l1.append(e)

  for e in l2:
    e_day = datetime.now(l2[e]['tz']).strftime('%A')
    e_hour = int(datetime.now(l2[e]['tz']).strftime('%H'))

    if (e_day != 'Sunday' and e_day != 'Saturday'):
      if (e_hour >= 9) and (e_hour <= 17):
        l2_crew[e] = []
        for c in sf.query("SELECT Id, CaseNumber, AccountCRorMW__c from Case where (OwnerId = '"+l2[e]['uid']+"') and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted' and status != 'Auto-Solved'")['records']:
          if not c['AccountCRorMW__c']:
            l2_crew[e].append('<'+sf_url+'/console#%2f'+c['Id']+'|'+c['CaseNumber']+'>')

  for e in l2:
    if e not in l2_crew.keys():
      l2_off[e] = []
      for c in sf.query("SELECT Id, CaseNumber, AccountCRorMW__c from Case where (OwnerId = '"+l2[e]['uid']+"') and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted' and status != 'Auto-Solved'")['records']:
        if not c['AccountCRorMW__c']:
          l2_off[e].append('<'+sf_url+'/console#%2f'+c['Id']+'|'+c['CaseNumber']+'>')

  print engineers.keys()
  print crew_keys
  for k in engineers.keys():
      if k in crew_keys:
        print k
        if not l1_crew.get(engineers[k], None):
          l1_crew[engineers[k]] = []
        for case in sf.query("SELECT Id, CaseNumber, AccountCRorMW__c from Case where (OwnerId = '"+ids[k]+"') and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted' and status != 'Auto-Solved'")['records']:
          if not case['AccountCRorMW__c']:
            l1_crew[engineers[k]].append('<'+sf_url+'/console#%2f'+case['Id']+'|'+case['CaseNumber']+'>')
      else:
        if not l1_off.get(engineers[k], None):
          l1_off[engineers[k]] = []
        for case in sf.query("SELECT Id, CaseNumber, AccountCRorMW__c from Case where (OwnerId = '"+ids[k]+"') and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted' and status != 'Auto-Solved'")['records']:
          if not case['AccountCRorMW__c']:
            l1_off[engineers[k]].append('<'+sf_url+'/console#%2f'+case['Id']+'|'+case['CaseNumber']+'>')

  for case in sf.query("SELECT Id, CaseNumber from Case where OwnerId = '00GE0000003YOIEMA4' and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted' and status != 'Auto-Solved'")['records']:
    l1_unassigned.append('<'+sf_url+'/console#%2f'+case['Id']+'|'+case['CaseNumber']+'>')

  for case in sf.query("SELECT Id, CaseNumber from Case where OwnerId = '00GE0000003YOIFMA4' and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted' and status != 'Auto-Solved'")['records']:
    l2_unassigned.append('<'+sf_url+'/console#%2f'+case['Id']+'|'+case['CaseNumber']+'>')

  for i in xrange(sheet.nrows):
    if isinstance(sheet.row_values(i)[0], float):
      start = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + int(sheet.row_values(i)[0]) -2)
      end = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + int(sheet.row_values(i)[1]) -2)
      if start <= datetime.now() <= end:
        on_duty_l2+= str(sheet.row_values(i)[2])

  result['timestamp'] = now
  result['l1'] = l1_crew
  result['l2'] = l2_crew
  result['od1'] = on_duty_l1
  result['od2'] = on_duty_l2
  result['l1u'] = l1_unassigned
  result['l2u'] = l2_unassigned
  result['offl1'] = l1_off
  result['offl2'] = l2_off
  os.environ['JSON_RESULT'] = str(json.dumps(result))

async_job()
print('app ready!')

if __name__ == '__main__':
  app = Flask(__name__)
  app.config.from_object(Config())
  scheduler = APScheduler()
  scheduler.init_app(app)
  scheduler.start()

  def gt(dt_str):
    dt, _, us= dt_str.partition(".")
    dt= datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
    us= int(us.rstrip("Z"), 10)
    return dt + timedelta(microseconds=us)

  def dict2message(d, oncall=None):
    message = ''
    for e in sorted(d, key=lambda e: len(d[e]), reverse=False):
      message +='*'+e+'*'+' : '+', '.join(d[e])+'  `'+str(len(d[e]))+'`'+str('\n')
    return message + 'On-call engineer : *' + ', '.join(oncall) + '*\n' if oncall else message

  def process_l2(l2_stats, l2_on_duty):
    if l2_stats:
      extra = dict2message(l2_stats)
    elif l2_on_duty:
      extra = l2_on_duty+' is on duty. \n The remaining team will be available soon.'
    else:
      extra  = 'No engineers on-duty: L2 escalations team available only at 9:00-17:00 MSK/EEST/PDT'
    return extra

  @app.route('/json')
  def l1_handle():
    return str(json.dumps(json.loads(os.environ['JSON_RESULT'])['l1']))

  @app.route('/jsonl2')
  def l2_handle():
    return str(json.dumps(json.loads(os.environ['JSON_RESULT'])['l2']))

  @app.route('/', methods=['GET'])
  def summary():
    data = json.loads(os.environ['JSON_RESULT'])
    stamp = gt(data['timestamp'])

    l1_unpr = ', '.join(data['l1u'])
    l2_unpr = ', '.join(data['l2u'])
    p1 = 'Unassigned: '+l1_unpr+'\n' + dict2message(data['l1'], data['od1']) if l1_unpr else dict2message(data['l1'], data['od1'])
    p2 = 'Unassigned: '+l2_unpr+'\n' + process_l2(data['l2'], data['od2']) if l2_unpr else process_l2(data['l2'], data['od2'])

    if stamp < datetime.utcnow()-timedelta(minutes=5):
      return 'app cache outdated', 500

    r = {}
    r['response_type'] = 'in_channel'
    r['text'] = '`# L1: #`\n'+p1 + '`# L2: #`\n'+ p2

    return json.dumps(r), 200, {'Content-Type': 'application/json'}

  @app.route('/extra', methods=['GET'])
  def l2_stats():
    data = json.loads(os.environ['JSON_RESULT'])
    l2_stats = data['l2']
    l2_on_duty = data['od2']
    stamp = gt(data['timestamp'])
    prefix = ', '.join(data['l2u'])

    extra = process_l2(l2_stats, l2_on_duty)

    if stamp < datetime.utcnow()-timedelta(minutes=5):
      return 'app cache outdated', 500

    r = {}
    r['response_type'] = 'in_channel'
    r['text'] = 'Unassigned: '+prefix+'\n' + extra if prefix else extra

    return json.dumps(r), 200, {'Content-Type': 'application/json'}

  @app.route('/general', methods=['GET'])
  def l1_stats():
    data = json.loads(os.environ['JSON_RESULT'])
    l1_stats = data['l1']
    l1_oncall = data['od1']
    stamp = gt(data['timestamp'])
    prefix = ', '.join(data['l1u'])

    payload = dict2message(l1_stats, l1_oncall)

    if stamp < datetime.utcnow()-timedelta(minutes=5):
      return 'app cache outdated', 500

    r = {}
    r['response_type'] = 'in_channel'
    r['text'] = 'Unassigned: '+prefix+'\n' + payload if prefix else payload

    return json.dumps(r), 200, {'Content-Type': 'application/json'}

  @app.route('/all_l1', methods=['GET'])
  def l1_all():
    data = json.loads(os.environ['JSON_RESULT'])
    all_stats = data['l1'].copy()
    all_stats.update(data['offl1'])
    payload = dict2message(all_stats)
    stamp = gt(data['timestamp'])
    prefix = ', '.join(data['l1u'])

    if stamp < datetime.utcnow()-timedelta(minutes=5):
      return 'app cache outdated', 500

    stamp = gt(data['timestamp'])

    r = {}
    r['response_type'] = 'in_channel'
    r['text'] = 'Unassigned: '+prefix+'\n' + payload if prefix else payload

    return json.dumps(r), 200, {'Content-Type': 'application/json'}

  @app.route('/all_l2', methods=['GET'])
  def l2_all():
    data = json.loads(os.environ['JSON_RESULT'])
    all_l2 = data['l2'].copy()
    all_l2.update(data['offl2'])
    payload = dict2message(all_l2)
    stamp = gt(data['timestamp'])
    prefix = ', '.join(data['l2u'])

    if stamp < datetime.utcnow()-timedelta(minutes=5):
      return 'app cache outdated', 500

    r = {}
    r['response_type'] = 'in_channel'
    r['text'] = 'Unassigned: '+prefix+'\n' + payload if prefix else payload

    return json.dumps(r), 200, {'Content-Type': 'application/json'}

  app.run(host='127.0.0.1', port=5002)
