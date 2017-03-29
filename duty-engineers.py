import httplib2
from apiclient import discovery
from datetime import datetime, timedelta
from calendarapi import get_credentials
from engineers import engineers, ids, l2
from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from flask import Flask, request
import json
import time
from flask_apscheduler import APScheduler
import os

import logging
logging.basicConfig()

parser = SafeConfigParser()
parser.read('salesforce.conf')

sf_url = parser.get('SalesForce', 'url')
sf_usr = parser.get('SalesForce', 'username')
sf_pwd = parser.get('SalesForce', 'password')
sf_tkn = parser.get('SalesForce', 'token')

cal_id = parser.get('calendar', 'id')

credentials = get_credentials()
http = credentials.authorize(httplib2.Http())
service = discovery.build('calendar', 'v3', http=http)

class Config(object):
    JOBS = [
        {
            'id': 'job1',
            'func': 'duty-engineers:async_job',
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

  eventsResult = service.events().list(
      calendarId=cal_id, timeMin=now, singleEvents = True,
      timeMax=then,orderBy='startTime',
      timeZone="UTC").execute()
  events = eventsResult.get('items', [])
  kvs = []
  for event in events:
    if 'shift' in event['summary']:
      key = event['attendees'].pop()['email']
      if key not in kvs:
        kvs.append(key)

  res = {}
  l1_crew = {}
  l2_crew = {}

  for e in l2:
    e_day = datetime.now(l2[e]['tz']).strftime('%A')
    e_hour = int(datetime.now(l2[e]['tz']).strftime('%H'))

    if (e_day != 'Sunday' or e_day != 'Saturday'):
      if (e_hour >= 9) and (e_hour <= 17 ):
        l2_crew[e] = []
        for c in sf.query("SELECT Id, CaseNumber from Case where (OwnerId = '"+l2[e]['uid']+"') and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted'")['records']:
          l2_crew[e].append('<'+sf_url+'/console#%2f'+c['Id']+'|'+c['CaseNumber']+'>')

  for k in kvs:
    l1_crew[engineers[k]] = []
    for case in sf.query("SELECT Id, CaseNumber from Case where (OwnerId = '"+ids[k]+"') and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted'")['records']:
      l1_crew[engineers[k]].append('<'+sf_url+'/console#%2f'+case['Id']+'|'+case['CaseNumber']+'>')

  res['timestamp'] = now
  res['l1'] = l1_crew
  res['l2'] = l2_crew
  os.environ['JSON_RESULT'] = str(json.dumps(res))

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

  @app.route('/json')
  def handle():
    return os.environ['JSON_RESULT']

  @app.route('/extra', methods=['GET'])
  def l2_stats():
    data = json.loads(os.environ['JSON_RESULT'])
    l2_stats = data['l2']
    extra = ''
    stamp = gt(data['timestamp'])

    if not l2_stats:
      extra = 'No engineers on-duty: L2 escalations team available only at 9:00-17:00 MSK/EEST/PDT'
    else:
      for e in sorted(l2_stats, key=lambda e: len(l2_stats[e]), reverse=False):
        extra +='*'+e+'*'+' : '+', '.join(l2_stats[e])+'  `'+str(len(l2_stats[e]))+'`'+str('\n')

    if stamp < datetime.utcnow()-timedelta(minutes=5):
      return 'app cache outdated', 500

    r = {}
    r['response_type'] = 'in_channel'
    r['text'] = extra

    return json.dumps(r), 200, {'Content-Type': 'application/json'}

  @app.route('/', methods=['GET'])
  def application():

    data = json.loads(os.environ['JSON_RESULT'])
    l1_stats = data['l1']
    stamp = gt(data['timestamp'])

    payload  = ''

    for k in sorted(l1_stats, key=lambda k: len(l1_stats[k]), reverse=False):
      payload += '*'+k+'*'+' : '+', '.join(l1_stats[k])+'  `'+str(len(l1_stats[k]))+'`'+str('\n')

    if stamp < datetime.utcnow()-timedelta(minutes=5):
      return 'app cache outdated', 500

    r = {}
    r['response_type'] = 'in_channel'
    r['text'] = payload

    return json.dumps(r), 200, {'Content-Type': 'application/json'}

  app.run(host='127.0.0.1', port=5002)
