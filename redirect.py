from ConfigParser import SafeConfigParser
from simple_salesforce import Salesforce
from flask import Flask, redirect

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

@app.route('/case')
def lalala():
    return '<head><link rel="icon" type="image/x-icon"  href="'+favicn+'"></head><script type="text/javascript">function go(caseId) {window.location = window.location.href + "/" + caseId;return false;}</script><form method="post" onsubmit="return go(this.caseId.value);">Case number: <input type="text" name="caseId"><input type="submit" value="Go"></form>'

@app.route('/case/<caseid>')
def application(caseid):
    if caseid in kvs:
        url = sf_url + '/console#%2f' + kvs[caseid]
    else:
        sf = Salesforce(custom_url=sf_url, username=sf_usr, password=sf_pwd, security_token=sf_tkn)
        for case in sf.query("SELECT Id from Case where CaseNumber = '%d'" % int(caseid))['records']:
          kvs[caseid] = case['Id']
          url = sf_url + '/console#%2f' + case['Id']
    return redirect(url, code=301)

@app.errorhandler(500)
def err(e):
    return '<head><style> html, body {margin:0;padding:0;} #footer {position:fixed;right:0;bottom:0;margin:0;width 75%} #footer img {width:100%;} </style></head> <center><h1>500 internal error</h1></center> <div id="footer"> <img src="http://pinkie.mylittlefacewhen.com/media/f/rsz/mlfw393_medium.png"></div>', 500
