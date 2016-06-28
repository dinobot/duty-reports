from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from flask import Flask, redirect

parser = SafeConfigParser()
parser.read('salesforce.conf')

sf_url = parser.get('SalesForce', 'url')
sf_usr = parser.get('SalesForce', 'username')
sf_pwd = parser.get('SalesForce', 'password')
sf_tkn = parser.get('SalesForce', 'token')

sf = Salesforce(custom_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)

app = Flask(__name__)

@app.route('/case/<caseid>')
def hello_world(caseid):
    for case in sf.query("SELECT Id from Case where CaseNumber = '%d'" % int(caseid))['records']:
        url = sf_url + '/console#%2f' + case['Id'] 
    return redirect(url, code=301)

@app.errorhandler(500)
def err(e):
    return '<center><img src="http://pinkie.mylittlefacewhen.com/media/f/rsz/mlfw393_medium.png"></center>', 500

