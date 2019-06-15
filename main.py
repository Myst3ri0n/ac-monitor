from ruuvitag_sensor.ruuvitag import RuuviTag
from pathlib import Path
from time import sleep
import config as cfg
import requests
import sqlite3
import time

kelvin_substract = 273.15


def DBQuery(q,fo=False):
	conn = sqlite3.connect('data.db')
	conn.text_factory = str
	cur = conn.cursor()
	cur.execute(q)
	conn.commit()
	if fo==True:
		results = cur.fetchone()[0]
	else:
		results = cur.fetchall()
	conn.close()
	return results

try: 
	DBQuery('SELECT * FROM TEMP_HISTORY;')
except:
	setup_queries = str(Path('setup_queries.sql').resolve())
	install_sql = open(setup_queries,'r')
	sql=''
	for l in install_sql:
		sql=sql+l
	sql =sql.split(';')
	
	for s in sql:
		DBQuery(s)


def convCel(temp):
	if temp>70:
		temp = temp - kelvin_substract
	ret = round(9.0/5.0 * temp + 32,2)
	return ret

def now_date_time():

	return (time.strftime("%Y-%m-%d %H:%M:%S"))

sensors = {
			'attic' : 'C4:5A:47:36:64:39',
			'ac_vent' : 'CC:3B:84:F3:E2:BE',
			'ac_return' : 'CE:FD:60:8D:18:A5'
			}

results = {}

while True:

	date_time    = now_date_time()
	weather_url  = 'https://api.openweathermap.org/data/2.5/weather?zip={},us&appid={}'.format(cfg.zip_code,cfg.weather_api_key)
	try:
		r            = requests.get(weather_url)
		outside_temp = convCel(r.json()['main']['temp'])
		outside_hum  = r.json()['main']['humidity']
	except:
		continue

	results.update({'outside':{'temp':outside_temp,'humidity':outside_hum}})

	for name, mac in sensors.items():
		sensor   = RuuviTag(mac)
		state    = sensor.update()
		temp     = convCel(sensor.state['temperature'])
		humidity = sensor.state['humidity']
		#print(sensor.state)
		results.update({name:{'temp':temp,'humidity':humidity}})

	temp_diff = results['ac_return']['temp'] - results['ac_vent']['temp'] 

	print('Date Read: ',date_time)

	for sensor, data in results.items():
		temp = data['temp']
		hum  = data['humidity']

		print(sensor,' Temp:',temp,'Humidity:',humidity)

		if temp_diff>10:
			print("Data Logged...")
			query = """
						INSERT INTO TEMP_HISTORY(DATE_READ,SENSOR_NAME,TEMP,HUMIDITY) 
						VALUES('{}','{}','{}','{}');
					""".format(date_time,sensor,temp,hum)
			DBQuery(query)
		else:
			print("Data Not Logged...")
	print('\n')
	sleep(300)
