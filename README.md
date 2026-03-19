# Freezer Alarm (Raspberry Pi)

A Raspberry Pi-based temperature alarm for -80C lab freezers. A small temperature sensor plugs into the Pi, and if the freezer gets too warm (or too cold), the system automatically sends email alerts to your lab. It also sends a daily "all is well" status email at 9 PM so you know the system is running.

Originally developed by the [Alonso-Stepanova Lab](https://github.com/Alonso-Stepanova-Lab/Freezer_Alarm_Raspberry_pi). This fork has been cleaned up for reliability -- the main improvement is that the system now emails you if the sensor itself fails, rather than crashing silently.

## What you need

- **Raspberry Pi** (any model with GPIO pins -- a Pi Zero W works fine)
- **DS18B20 temperature sensor** (waterproof probe version recommended for freezers)
- **4.7k ohm resistor** (pulls the data line high -- the sensor won't work without it)
- **Jumper wires** to connect the sensor to the Pi
- **A Gmail account** with an App Password for sending emails
- **Python 3** (pre-installed on most Raspberry Pi OS images)

## Step 1: Wire the sensor

The DS18B20 has three wires:

| Wire color | Connects to |
|-----------|-------------|
| Red | 3.3V power (GPIO pin 1) |
| Black | Ground (GPIO pin 6) |
| Yellow/White (data) | GPIO 4 (pin 7) |

Connect the **4.7k ohm resistor between the red wire (3.3V) and the yellow/data wire**. This is called a "pull-up resistor" and is required for the sensor to communicate.

A wiring diagram can be found in many DS18B20 + Raspberry Pi tutorials online.

## Step 2: Enable the 1-Wire interface

1. Open a terminal on your Pi (or SSH in)
2. Run `sudo raspi-config`
3. Go to **Interface Options** -> **1-Wire** -> **Enable**
4. Reboot: `sudo reboot`

## Step 3: Verify the sensor is working

After reboot, run these commands:

```bash
sudo modprobe w1-therm
ls /sys/bus/w1/devices/
```

You should see a folder starting with `28-` (e.g., `28-00000abcdef`). That's your sensor. Now read it:

```bash
cat /sys/bus/w1/devices/28-*/w1_slave
```

You should see output like:
```
73 01 4b 46 7f ff 0d 10 41 : crc=41 YES
73 01 4b 46 7f ff 0d 10 41 t=23187
```

- The first line should end with `YES` (meaning the data checksum is valid)
- `t=23187` means 23.187 degrees C (the value is in thousandths of a degree)

If you don't see the `28-` folder, check your wiring and make sure 1-Wire is enabled.

## Step 4: Set up Gmail App Password

The alarm sends emails through Gmail's SMTP server. You'll need to create an "App Password" so the Pi can log in without your real password.

1. Go to [myaccount.google.com](https://myaccount.google.com) and sign in
2. Go to **Security** -> **2-Step Verification** (enable it if you haven't already)
3. At the bottom of the 2-Step Verification page, click **App passwords**
4. Name it "Freezer Alarm" and click **Create**
5. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`) -- you'll only see it once

## Step 5: Copy files to the Pi

Copy these files to `/home/pi/`:

```bash
cd /home/pi
git clone https://github.com/steinbrennerlab/freezer_alarm.git
cp freezer_alarm/*.py freezer_alarm/*.sh freezer_alarm/*.txt /home/pi/
```

## Step 6: Configure the alarm

Edit these files in `/home/pi/`. Each file is a single line of JSON.

**`senderpassword.txt`** -- Your Gmail App Password from Step 4:
```
["abcd efgh ijkl mnop"]
```

**`senders.txt`** -- The Gmail address that sends the alerts:
```
["yourlab@gmail.com"]
```

**`recipients.txt`** -- Email addresses that receive alerts (one array, comma-separated):
```
["labmember1@gmail.com","labmember2@university.edu"]
```

**`freezername.txt`** -- A name for your freezer (used in email subjects):
```
["Room-123-Freezer"]
```

**`alarmset.txt`** -- High temperature threshold in Celsius. If the freezer gets warmer than this, an alarm is sent. For a -80C freezer, `-18` is a reasonable default (the sensor is often in the top of the freezer):
```
-18
```

**`alarmsetL.txt`** -- Low temperature threshold in Celsius. If the reading drops below this, an alarm is sent. This also catches sensor errors that report very low values:
```
-85
```

## Step 7: Set up automatic startup

The alarm needs to start automatically when the Pi boots, and the connectivity watchdog should run twice a day.

```bash
sudo crontab -e
```

If asked to choose an editor, pick `nano` (option 1). Add these three lines at the bottom:

```
@reboot sudo python3 /home/pi/temperaturev7.py
0 8 * * * sudo python3 /home/pi/reset.py
0 20 * * * sudo python3 /home/pi/reset.py
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter` in nano).

Reboot to start the alarm:

```bash
sudo reboot
```

## Step 8: Verify it's running

After the Pi reboots, SSH in and check:

```bash
# Check the process is running
ps aux | grep temperaturev7

# Check the log for recent readings
tail -20 /home/pi/freezer_alarm.log
```

You should see log lines like:
```
2025-01-15 14:30:00,123 INFO Temperature: -76.3 C
```

## How it works

| What | Details |
|------|---------|
| Reads sensor | Every 60 seconds |
| Temperature alarm | Emails all recipients if temp goes above the high threshold or below the low threshold. 5-minute cooldown between alerts so you don't get flooded. |
| Daily digest | Sends a status email at 9 PM to the first recipient, so you know the system is alive |
| Sensor failure | If the sensor fails 3 reads in a row, emails the admin (set `ADMIN_EMAIL` in `temperaturev7.py`) |
| Connectivity check | `reset.py` runs at 8 AM and 8 PM via cron to verify the email connection still works |
| Logging | All activity is logged to `/home/pi/freezer_alarm.log` |

## Files

| File | Purpose |
|------|---------|
| `temperaturev7.py` | Main monitoring script (runs continuously after boot) |
| `reset.py` | SMTP connectivity watchdog (runs via cron) |
| `launcher.sh` | Alternative way to start the monitor at boot |
| `temperaturelist.txt` | Rolling history of temperature readings (auto-generated) |
| `timelist.txt` | Rolling history of timestamps (auto-generated) |
| Config files (`*.txt`) | See Step 6 above |

## Troubleshooting

**No `28-` folder in `/sys/bus/w1/devices/`**
- Check that 1-Wire is enabled (`sudo raspi-config` -> Interface Options -> 1-Wire)
- Check wiring: data wire to GPIO 4, pull-up resistor between data and 3.3V
- Try `sudo modprobe w1-gpio && sudo modprobe w1-therm`, then check again

**Sensor reads `85000` (85.0 C)**
- This is the DS18B20 power-on default. It means the sensor hasn't completed a real reading yet. Usually resolves on the next poll. If persistent, check wiring.

**Sensor reads `-127000` (-127.0 C)**
- The sensor is disconnected or the data wire has a bad connection. Check wiring.

**Not getting emails**
- Check `/home/pi/freezer_alarm.log` for SMTP errors
- Verify your Gmail App Password is correct in `senderpassword.txt`
- Check that `senders.txt` contains your Gmail address
- Make sure 2-Step Verification is enabled on the Gmail account

**Script not running after reboot**
- Check crontab: `sudo crontab -l`
- Check for errors: `tail -50 /home/pi/freezer_alarm.log`
