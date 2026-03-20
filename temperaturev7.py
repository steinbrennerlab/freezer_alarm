import os
import glob
import time
import socket
import smtplib
import json
import datetime
import logging
import traceback

# --- Configuration ---
CONFIG_DIR = '/home/pi/'
ADMIN_EMAIL = 'adam.steinbrenner@gmail.com'
SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SENDER_FROM = 'adam.steinbrenner@gmail.com'
POLL_INTERVAL = 60
ALARM_COOLDOWN = 300
MAX_CRC_RETRIES = 10
DIGEST_HOUR = 21
MONTHLY_DAY = 1
MONTHLY_HOUR = 9
HISTORY_SIZE = 10000
SENSOR_BASE = '/sys/bus/w1/devices/'
NETWORK_WAIT_INTERVAL = 10
NETWORK_MAX_RETRIES = 30  # 5 minutes of retries at boot

logging.basicConfig(
    filename=CONFIG_DIR + 'freezer_alarm.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)


class SensorError(Exception):
    pass


def load_config():
    """Read all JSON config files from CONFIG_DIR."""
    config = {}
    files = {
        'alarm_high': 'alarmset.txt',
        'alarm_low': 'alarmsetL.txt',
        'freezer_name': 'freezername.txt',
        'recipients': 'recipients.txt',
        'senders': 'senders.txt',
        'password': 'senderpassword.txt',
    }
    for key, fname in files.items():
        path = CONFIG_DIR + fname
        with open(path, 'r') as f:
            config[key] = json.load(f)
    return config


def find_sensor():
    """Locate the DS18B20 sensor device file. Raises SensorError if not found."""
    os.system('modprobe w1-gpio')
    os.system('modprobe w1-therm')
    devices = glob.glob(SENSOR_BASE + '28*')
    if not devices:
        raise SensorError('No DS18B20 sensor found at ' + SENSOR_BASE)
    return devices[0] + '/w1_slave'


def send_email(subject, body, recipients):
    """Send an email via SendGrid SMTP. Returns True on success, False on failure."""
    try:
        config = load_config()
        sender = config['senders'][0]
        password = config['password'][0]
        msg = 'From: {}\nSubject: {}\n\n{}'.format(SENDER_FROM, subject, body)
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(sender, password)
        for recipient in recipients:
            server.sendmail(sender, recipient, msg)
        server.quit()
        logging.info('Email sent: %s to %s', subject, recipients)
        return True
    except Exception as e:
        logging.error('Failed to send email: %s', e)
        return False


PLANT_AND_CATERPILLAR_ART = r"""
        _
       | |
   ____| |__
  /  ___    \     0 0 0 0
  | |   |   |    \|/|/|/|/
  | |   |   |     ^ ^ ^ ^
  | |___|   |    _/|_/|_/|_
  \________/    (___________) <-- caterpillar
     |  |
     |  |        ,---. ,---.
    _|  |_      ( o  o  o  o )
   (_    _)      \ ~ ~ ~ ~ /
     |__|         `---------'
     |  |           |   |
    /|  |\       __/     \__
   (_|  |_)     (   garden  )
"""


def send_reboot_email(recipients, freezer_name, temp_c, alarm_high, alarm_low):
    """Send a reboot notification email to all recipients."""
    subject = '#FreezerAlarm REBOOT'
    body = (
        'The Freezer Alarm system has just rebooted!\n\n'
        'The Raspberry Pi monitoring {freezer} has restarted and is now\n'
        'actively monitoring the freezer temperature.\n\n'
        'Current status:\n'
        '  - Temperature: {temp:.1f} C\n'
        '  - High alarm threshold: {high} C\n'
        '  - Low alarm threshold: {low} C\n\n'
        'The system checks the temperature every {interval} seconds and will\n'
        'send an alert if the temperature goes outside the safe range.\n\n'
        'No action is needed -- this is just a heads-up that the system\n'
        'restarted (e.g. after a power outage or maintenance).\n\n'
        '{art}'
    ).format(
        freezer=freezer_name, temp=temp_c,
        high=alarm_high, low=alarm_low,
        interval=POLL_INTERVAL, art=PLANT_AND_CATERPILLAR_ART,
    )
    send_email(subject, body, recipients)


def send_monthly_update(recipients, freezer_name, temp_c, alarm_high, alarm_low):
    """Send a monthly reminder email to all recipients."""
    subject = '#FreezerAlarm Monthly Update'
    body = (
        'Monthly reminder: the Freezer Alarm is alive and well!\n\n'
        'This is your friendly monthly update from the Raspberry Pi\n'
        'monitoring {freezer}.\n\n'
        'Current status:\n'
        '  - Temperature: {temp:.1f} C\n'
        '  - High alarm threshold: {high} C\n'
        '  - Low alarm threshold: {low} C\n\n'
        'NOTE: The temperature sensor is mounted on the wall of the\n'
        'freezer, not in the center. This means the reported temperature\n'
        'may be slightly warmer than the actual temperature at the center\n'
        'of the freezer. Keep this in mind when evaluating readings.\n\n'
        'The system checks the temperature every {interval} seconds,\n'
        '24 hours a day, 7 days a week. If anything goes wrong, you\n'
        'will receive an alert immediately.\n\n'
        '{art}'
    ).format(
        freezer=freezer_name, temp=temp_c,
        high=alarm_high, low=alarm_low,
        interval=POLL_INTERVAL, art=PLANT_AND_CATERPILLAR_ART,
    )
    send_email(subject, body, recipients)


def send_sensor_failure_alert(error_detail):
    """Send sensor failure alert to admin only."""
    subject = '#FreezerAlarm SENSOR FAILURE'
    body = 'The temperature sensor is not responding.\n\nError: {}'.format(error_detail)
    send_email(subject, body, [ADMIN_EMAIL])


def read_temp_raw(device_file):
    """Read raw lines from the sensor device file."""
    with open(device_file, 'r') as f:
        return f.readlines()


def read_temp(device_file):
    """Read temperature from sensor. Raises SensorError on failure."""
    for attempt in range(MAX_CRC_RETRIES):
        lines = read_temp_raw(device_file)
        if len(lines) >= 1 and lines[0].strip().endswith('YES'):
            break
        time.sleep(0.2)
    else:
        raise SensorError('CRC check failed after {} retries'.format(MAX_CRC_RETRIES))

    if len(lines) < 2:
        raise SensorError('Sensor returned incomplete data')

    equals_pos = lines[1].find('t=')
    if equals_pos == -1:
        raise SensorError('No temperature data in sensor output')

    temp_string = lines[1][equals_pos + 2:]
    temp_c = float(temp_string) / 1000.0
    return temp_c


def load_history():
    """Load temperature and time history from disk, with fallback to empty lists."""
    try:
        with open(CONFIG_DIR + 'temperaturelist.txt', 'r') as f:
            content = f.read().strip()
            temperaturelist = json.loads(content) if content else [0] * HISTORY_SIZE
    except (json.JSONDecodeError, FileNotFoundError):
        temperaturelist = [0] * HISTORY_SIZE

    try:
        with open(CONFIG_DIR + 'timelist.txt', 'r') as f:
            content = f.read().strip()
            timelist = json.loads(content) if content else [''] * HISTORY_SIZE
    except (json.JSONDecodeError, FileNotFoundError):
        timelist = [''] * HISTORY_SIZE

    return temperaturelist, timelist


def save_history(temperaturelist, timelist):
    """Write temperature and time history to disk."""
    try:
        with open(CONFIG_DIR + 'temperaturelist.txt', 'w') as f:
            json.dump(temperaturelist, f)
        with open(CONFIG_DIR + 'timelist.txt', 'w') as f:
            json.dump(timelist, f)
    except Exception as e:
        logging.error('Failed to save history: %s', e)


def wait_for_network():
    """Block until DNS resolution works, so emails don't fail at boot."""
    for attempt in range(NETWORK_MAX_RETRIES):
        try:
            socket.getaddrinfo(SMTP_HOST, SMTP_PORT)
            logging.info('Network is up')
            return
        except socket.gaierror:
            logging.info('Waiting for network (attempt %d)...', attempt + 1)
            time.sleep(NETWORK_WAIT_INTERVAL)
    logging.warning('Network not available after %d attempts, continuing anyway',
                    NETWORK_MAX_RETRIES)


def main():
    logging.info('Freezer alarm starting')
    wait_for_network()

    # Find sensor (retry with alerts on failure)
    device_file = None
    for attempt in range(5):
        try:
            device_file = find_sensor()
            logging.info('Sensor found: %s', device_file)
            break
        except SensorError as e:
            logging.error('Sensor search attempt %d failed: %s', attempt + 1, e)
            send_sensor_failure_alert(str(e))
            time.sleep(60)
    if device_file is None:
        logging.critical('Sensor not found after 5 attempts, exiting')
        return

    # Load config and history
    config = load_config()
    alarm_high = config['alarm_high']
    alarm_low = config['alarm_low']
    freezer_name = config['freezer_name'][0]
    recipients = config['recipients']
    temperaturelist, timelist = load_history()

    # Send reboot notification with a live temperature reading
    try:
        initial_temp = read_temp(device_file)
        send_reboot_email(recipients, freezer_name, initial_temp, alarm_high, alarm_low)
        logging.info('Reboot notification sent (temp: %.1f C)', initial_temp)
    except SensorError as e:
        logging.error('Could not read temp for reboot email: %s', e)
        send_reboot_email(recipients, freezer_name, float('nan'), alarm_high, alarm_low)

    # State tracking
    last_alarm_time = 0
    last_sensor_alert_time = 0
    last_digest_date = None
    last_monthly_date = None
    consecutive_failures = 0

    while True:
        try:
            temp_c = read_temp(device_file)
            consecutive_failures = 0
            logging.info('Temperature: %.1f C', temp_c)

            # High threshold alarm
            now = time.time()
            if temp_c >= alarm_high and (now - last_alarm_time) > ALARM_COOLDOWN:
                subject = '#FreezerAlarm'
                body = 'The temperature in the -80C freezer {} is {:.1f} C (high threshold: {} C)'.format(
                    freezer_name, temp_c, alarm_high)
                send_email(subject, body, recipients)
                last_alarm_time = now

            # Low threshold alarm
            if temp_c <= alarm_low and (now - last_alarm_time) > ALARM_COOLDOWN:
                subject = '#FreezerAlarm'
                body = 'The temperature in the -80C freezer {} is {:.1f} C (low threshold: {} C)'.format(
                    freezer_name, temp_c, alarm_low)
                send_email(subject, body, recipients)
                last_alarm_time = now

            # Daily digest at DIGEST_HOUR
            today = datetime.date.today()
            current_hour = datetime.datetime.now().hour
            if current_hour == DIGEST_HOUR and last_digest_date != today:
                subject = '#Freezer update'
                body = 'The temperature in the -80C freezer {} is {:.1f} C'.format(
                    freezer_name, temp_c)
                send_email(subject, body, [recipients[0]])
                last_digest_date = today

            # Monthly update on the 1st at MONTHLY_HOUR
            if (today.day == MONTHLY_DAY and current_hour == MONTHLY_HOUR
                    and last_monthly_date != today):
                send_monthly_update(recipients, freezer_name, temp_c,
                                    alarm_high, alarm_low)
                last_monthly_date = today

            # Update history
            del temperaturelist[0]
            del timelist[0]
            temperaturelist.append(temp_c)
            timelist.append(datetime.datetime.now().isoformat())
            save_history(temperaturelist, timelist)

        except SensorError as e:
            consecutive_failures += 1
            logging.error('Sensor read failed (%d consecutive): %s', consecutive_failures, e)
            now = time.time()
            if consecutive_failures >= 3 and (now - last_sensor_alert_time) > ALARM_COOLDOWN:
                send_sensor_failure_alert(str(e))
                last_sensor_alert_time = now

        except Exception as e:
            logging.error('Unexpected error: %s\n%s', e, traceback.format_exc())

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.critical('Fatal error: %s\n%s', e, traceback.format_exc())
        send_sensor_failure_alert('Script crashed: {}'.format(e))
        raise
