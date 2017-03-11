from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from flask import Flask, request

parser = SafeConfigParser()
parser.read('salesforce.conf')

sf_url = parser.get('SalesForce', 'url')
sf_usr = parser.get('SalesForce', 'username')
sf_pwd = parser.get('SalesForce', 'password')
sf_tkn = parser.get('SalesForce', 'token')
favicn = parser.get('www', 'favicon')

#sf = Salesforce(instance_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)

kvs = {}

def prepare_json_data(json_data):
    json_data_string = ''
    for c in json_data:
      if c in '{}["]':
        c = ' '
      json_data_string = json_data_string + c
    return json_data_string

app = Flask(__name__)

@app.route('/', methods=['GET'])
def application():
    caseid = request.args.get('text', '')
    if caseid in kvs:
        url = sf_url + '/console#%2f' + kvs[caseid].get('id')
        title = kvs[caseid].get('title')
    else:
        sf = Salesforce(instance_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)
        for case in sf.query("SELECT Id, Subject from Case where CaseNumber = '%d'" % int(caseid))['records']:
          kvs[caseid] = {'id': case['Id'], 'title': prepare_json_data(case['Subject'])}
          url = sf_url + '/console#%2f' + case['Id']
          title = prepare_json_data(case['Subject'])
    return '{"response_type": "in_channel", "attachments": [{"title": "'+title+'","title_link": "'+url+'",}]}', 200, {'Content-Type': 'application/json'}

@app.errorhandler(500)
def err(e):
    return 'no such case, sorry', 500

app.run(host='127.0.0.1', port=5001)
