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
    res[engineers[k]] = []
    for case in sf.query("SELECT Id, CaseNumber from Case where (OwnerId = '"+ids[k]+"') and status != 'Closed' and status != 'Solved' and status != 'Ignored' and status != 'Completed' and status != 'Converted'")['records']:
      res[engineers[k]].append('<'+sf_url+'/console#%2f'+case['Id']+'|'+case['CaseNumber']+'>')

  res['timestamp'] = now
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
  @app.route('/json')
  def handle():
    return os.environ['JSON_RESULT']

  @app.route('/', methods=['GET'])
  def application():

    def gt(dt_str):
      dt, _, us= dt_str.partition(".")
      dt= datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
      us= int(us.rstrip("Z"), 10)
      return dt + timedelta(microseconds=us)

    data = json.loads(os.environ['JSON_RESULT'])
    stamp = gt(data['timestamp'])
    l2 = data['l2']

    del data['l2']
    del data['timestamp']

    payload  = ''
    extra = ''

    for k in sorted(data, key=lambda k: len(data[k]), reverse=False):
      payload += k+' : '+', '.join(data[k])+'  `'+str(len(data[k]))+'`'+str('\n')

    for e in sorted(l2, key=lambda e: len(l2[e]), reverse=False):
      extra += e+' : '+', '.join(l2[e])+'  `'+str(len(l2[e]))+'`'+str('\n')

    if stamp < datetime.utcnow()-timedelta(minutes=5):
      return 'app cache outdated', 500

    r = {}
    r['response_type'] = 'in_channel'
    if l2:
      r['text'] = '*#   L1:   # * \n' + payload + '*#   L2:   # * \n' + extra
    else:
      r['text'] = '*#   L1:   # * \n' + payload

    return json.dumps(r), 200, {'Content-Type': 'application/json'}

  app.run(host='127.0.0.1', port=5002)
