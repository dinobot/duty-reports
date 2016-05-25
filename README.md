# duty-reports

script requres:
- patched library simple_salesforce. The library is available here: https://github.com/dinobot/simple-salesforce 
- Duty list 2016.xlsx
- engineers.py
- salesfoce.conf: portal url, salesforce username, salesforce account password (may be different from SSO password if you are using one), security token (available in settings of salesforce account). 

usage: 

python reports.py [day || night]

You need to specify shift for which you are making report (for day shift or for night shift next from yours)
