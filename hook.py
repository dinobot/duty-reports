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

#sf = Salesforce(custom_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)

kvs = {}

app = Flask(__name__)

@app.route('/', methods=['GET'])
def application():
    caseid = request.args.get('text', '')
    if caseid in kvs:
        url = kvs[caseid].get('url')
        title = kvs[caseid].get('title')
        severity = kvs[caseid].get('severity')
        customer = kvs[caseid].get('customer')
    else:
        sf = Salesforce(custom_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)
        for case in sf.query("SELECT Id, Subject, Severity_Level__c, AccountId from Case where CaseNumber = '%d'" % int(caseid))['records']:
          title = case['Subject']
          customer = sf.account.get(case['AccountId'])['Name']
          severity = case['Severity_Level__c']
          url = sf_url + '/console#%2f' + case['Id']
          kvs[caseid] = {'id': case['Id'],
                         'title': title,
                         'customer': customer,
                         'severity': severity,
                         'url': url}

    return '{"response_type": "in_channel", "attachments": [{"title": "'+title+'", "title_link": "'+url+'","fields": [{"title": "'+customer+'", "value":"'+severity+'"}]}]}', 200, {'Content-Type': 'application/json'}

@app.errorhandler(500)
def err(e):
    return 'no such case, sorry', 500

app.run(host='127.0.0.1', port=5001)
