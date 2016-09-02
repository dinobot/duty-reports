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
        url = sf_url + '/console#%2f' + kvs[caseid]
    else:
        sf = Salesforce(custom_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)
        for case in sf.query("SELECT Id from Case where CaseNumber = '%d'" % int(caseid))['records']:
          kvs[caseid] = case['Id']
          url = sf_url + '/console#%2f' + case['Id']
    return '{"response_type": "in_channel", "attachments": [{"title": "'+caseid+'","title_link": "'+url+'",}]}', 200, {'Content-Type': 'application/json'}

@app.errorhandler(500)
def err(e):
    return 'no such case, sorry', 500

app.run(host='0.0.0.0', port=5001)
