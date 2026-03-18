import smtplib
import json
import logging

CONFIG_DIR = '/home/pi/'

logging.basicConfig(
    filename=CONFIG_DIR + 'freezer_reset.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)

try:
    with open(CONFIG_DIR + 'senders.txt', 'r') as f:
        senders = json.load(f)
    with open(CONFIG_DIR + 'senderpassword.txt', 'r') as f:
        password = json.load(f)
    server = smtplib.SMTP('smtp.sendgrid.net', 587)
    try:
        server.starttls()
        server.login(senders[0], password[0])
    finally:
        server.quit()
    logging.info('SMTP connectivity check passed')
except Exception as e:
    logging.error('SMTP connectivity check failed: %s', e)
