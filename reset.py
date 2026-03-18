import smtplib
import os
try:
    server = smtplib.SMTP('smtp.sendgrid.net',587)
    server.starttls()
    server.login("apikey","SG.ZjHsBDUIQnCHidh")
except:
    #os.system("sudo reboot")
