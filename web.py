from flask import Flask, request, render_template, redirect,\
url_for, flash, make_response, session, Markup, jsonify
from ruuvitag_sensor.ruuvitag import RuuviTag
from pygal.style import DarkGreenBlueStyle
from pygal.style import Style
from datetime import datetime
import config as cfg
import time
import requests
import sqlite3
import pygal

custom_style = Style(

    background = '#171717',
    plot_background = '#171717',
    foreground = 'rgba(255, 255, 255, 0.9)',
    foreground_strong = 'rgba(255, 255, 255, 0.9)',
    foreground_subtle = 'rgba(255, 255, 255, 0.6)',
    opacity = '.55',
    opacity_hover = '.9',
    transition = '250ms ease-in',
    colors = (
        '#FF7A14', '#EE1ACA', '#247fab', '#7dcf30',
        '#247fab', '#7dcf30', '#247fab', '#fff')
)

app = Flask(__name__)

def __datetime(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')

def sec2humanTime(sec):
	if sec<60:
		result = '{} seconds'.format(sec)
	elif sec>=60 and sec <3600:
		result = '{} minutes'.format(round(sec/60,2))
	elif sec>=3600:
		result = '{} hours'.format(round(sec/3600,2))
	return result	

def convCel(temp):
	if temp>70:
		temp = temp - cfg.kelvin_substract
	ret = round(9.0/5.0 * temp + 32,2)
	return ret

def coolAgainstTime(temp,sec):

	if sec>=900 and  sec<=1799:
		time_frame = ' °F per 15 mins'
		divisor     = sec/900 
	if sec>=1800 and sec<=3599:
		time_frame = ' °F per 30 mins'
		divisor    = sec/1800
	if sec>=3600:
		time_frame = ' °F per Hour'
		divisor    = sec/3600
	else: 
		time_fram = ' °F per Min'
		divisor   = sec/60

	amount = round(temp/divisor,2)
	return str(amount)+time_frame


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


@app.route('/',methods=['GET','POST'])
def main_page():
	if request.method == "POST":
		selected_report = request.form['selected_report']
		days_data       = request.form['days_data']
	else:
		selected_report = 'temp_over_time'
		days_data       = '1'

	if days_data=='1':
		time_name = '24 Hours'
	elif days_data=='3':
		time_name = '72 Hours'
	else:
		time_name = '7 Days'


	weather_url  = 'https://api.openweathermap.org/data/2.5/weather?zip={},us&appid={}'.format(cfg.zip_code,cfg.weather_api_key)
	r            = requests.get(weather_url)
	outside_temp = convCel(r.json()['main']['temp'])
	outside_hum  = r.json()['main']['humidity']

	results = {}

	for name, mac in cfg.sensors.items():
		sensor   = RuuviTag(mac)
		state    = sensor.update()
		temp     = convCel(sensor.state['temperature'])
		humidity = sensor.state['humidity']
		results.update({name:{'temp':temp,'humidity':humidity}})

	current_temp_diff = round(results['ac_return']['temp'] - results['ac_vent']['temp'],2)

	#setting color based on value
	if current_temp_diff>=13 and current_temp_diff<16:
		current_temp_html = '<span style="color:orange;">{}</span>'.format(current_temp_diff)
	elif current_temp_diff>=16:
		current_temp_html = '<span style="color:green;">{}</span>'.format(current_temp_diff)
	else:
		current_temp_html = '<span style="color:red;">{}</span>'.format(current_temp_diff)

	db_sensors = [x[0] for x in DBQuery("SELECT DISTINCT SENSOR_NAME FROM TEMP_HISTORY WHERE DATE_READ > datetime('now','-{} day')".format(days_data))]

	min_max_temps = {}
	for s in db_sensors:
		max_hum  = DBQuery("SELECT MAX(HUMIDITY) FROM TEMP_HISTORY WHERE SENSOR_NAME='{}' AND DATE_READ > datetime('now','-{} day')".format(s,days_data),True)
		min_hum  = DBQuery("SELECT MIN(HUMIDITY) FROM TEMP_HISTORY WHERE SENSOR_NAME='{}' AND DATE_READ > datetime('now','-{} day')".format(s,days_data),True)
		avg_hum  = round(DBQuery("SELECT AVG(HUMIDITY) FROM TEMP_HISTORY WHERE SENSOR_NAME='{}' AND DATE_READ > datetime('now','-{} day')".format(s,days_data),True),2)
		max_temp = DBQuery("SELECT MAX(TEMP) FROM TEMP_HISTORY WHERE SENSOR_NAME='{}' AND DATE_READ > datetime('now','-{} day')".format(s,days_data),True)
		min_temp = DBQuery("SELECT MIN(TEMP) FROM TEMP_HISTORY WHERE SENSOR_NAME='{}' AND DATE_READ > datetime('now','-{} day')".format(s,days_data),True)
		avg_temp = round(DBQuery("SELECT AVG(TEMP) FROM TEMP_HISTORY WHERE SENSOR_NAME='{}' AND DATE_READ > datetime('now','-{} day')".format(s,days_data),True),2)
		min_max_temps.update({s:{
									'max_temp':max_temp,
									'min_temp':min_temp,
									'avg_temp':avg_temp,
									'max_humidity':max_hum,
									'min_humidity':min_hum,
									'avg_humidity':avg_hum
										}
									})

	m_m = ['MAX','MIN','AVG']
	min_max_diff = {}
	for m in m_m:
		q_min_max_diff = """
					SELECT {}(t1.TEMP - (
										SELECT 	t2.TEMP 
										FROM 	TEMP_HISTORY AS t2 
										WHERE 	t1.DATE_READ=t2.DATE_READ 
												AND t2.SENSOR_NAME='ac_vent'
												))
					FROM 	TEMP_HISTORY AS t1 
					WHERE 	t1.SENSOR_NAME='ac_return'
							AND DATE_READ > datetime('now','-{} day')
					""".format(m,days_data)
		temp = round(DBQuery(q_min_max_diff,True),2)
		min_max_diff.update({m:temp})

	#DETERMINING LAST TOTAL RUNTIME
	ac_return_ids= [x[0] for x in DBQuery("SELECT ID FROM TEMP_HISTORY WHERE SENSOR_NAME='ac_return' AND DATE_READ > datetime('now','-{} day') ORDER BY DATE_READ DESC".format(days_data))]
	count     = 1
	last_date = ''
	continuous_ids = []
	for i in ac_return_ids:
		if count==1:
			last_date = DBQuery('SELECT DATE_READ FROM TEMP_HISTORY WHERE ID = {}'.format(i),True)
			continuous_ids.append(i)
			count+=1
		else:
			cur_date = DBQuery('SELECT DATE_READ FROM TEMP_HISTORY WHERE ID = {}'.format(i),True)
			delta = __datetime(last_date) - __datetime(cur_date)
			delta = delta.total_seconds()
			#print(last_date,cur_date)
			#print(delta)
			last_date = cur_date
			continuous_ids.append(i)
			if delta>=330:
				break
	run_start_date = DBQuery("SELECT MAX(DATE_READ) FROM TEMP_HISTORY WHERE ID IN ({})".format(','.join([str(x) for x in continuous_ids])),True)
	run_end_date   = DBQuery("SELECT MIN(DATE_READ) FROM TEMP_HISTORY WHERE ID IN ({})".format(','.join([str(x) for x in continuous_ids])),True)
	max_ac_return  = DBQuery("SELECT MAX(TEMP) FROM TEMP_HISTORY WHERE SENSOR_NAME='ac_return' AND DATE_READ='{}'".format(run_end_date),True)
	min_ac_return  = DBQuery("SELECT MIN(TEMP) FROM TEMP_HISTORY WHERE SENSOR_NAME='ac_return' AND DATE_READ='{}'".format(run_start_date),True)

	run_delta  = __datetime(run_start_date) - __datetime(run_end_date)
	run_delta  = run_delta.total_seconds()
	ac_runtime = sec2humanTime(run_delta)

	total_degrees_cooled = max_ac_return - min_ac_return

	print(run_delta,total_degrees_cooled)
	print(run_start_date,run_end_date)

	degrees_over_time = coolAgainstTime(total_degrees_cooled,run_delta)


	if selected_report=='temp_over_time':
		chart = pygal.Line(style=custom_style,x_label_rotation=20)
		chart.title = 'Tempature Over {}'.format(time_name)

		labels = [x[0] for x in DBQuery("SELECT DISTINCT strftime('%m/%d %Hhrs %Mmins',DATE_READ) FROM TEMP_HISTORY WHERE SENSOR_NAME='attic' AND DATE_READ > datetime('now','-{} day')".format(days_data))]
		chart.x_labels = labels

		for s in db_sensors:
			sensor_name  = s 
			sensor_temps = [x[0] for x in DBQuery("SELECT TEMP FROM TEMP_HISTORY WHERE SENSOR_NAME='{}' AND DATE_READ > datetime('now','-{} day')".format(sensor_name,days_data))]
			chart.add(sensor_name,sensor_temps)
	elif selected_report=='diff_over_time':
		chart = pygal.Line(fill=True, interpolate='cubic', style=custom_style)
		chart.title = 'Tempature Differential Over {}'.format(time_name)
		labels = [x[0] for x in DBQuery("SELECT DISTINCT strftime('%m/%d %Hhrs',DATE_READ) FROM TEMP_HISTORY WHERE SENSOR_NAME='attic' AND DATE_READ > datetime('now','-{} day')".format(days_data))]
		chart.x_labels = labels
		data_query = """
					SELECT t1.TEMP - (
										SELECT 	t2.TEMP 
										FROM 	TEMP_HISTORY AS t2 
										WHERE 	t1.DATE_READ=t2.DATE_READ 
												AND t2.SENSOR_NAME='ac_vent'
												) 
					FROM 	TEMP_HISTORY AS t1 
					WHERE 	t1.SENSOR_NAME='ac_return'
							AND DATE_READ > datetime('now','-{} day')
					""".format(days_data)
		sensor_temps = [x[0] for x in DBQuery(data_query)]
		chart.add('Temp Diff',sensor_temps)


	graph_data = chart.render_data_uri()
	post_url   = url_for('main_page')

	return render_template('pygal_reports.html',graph_data=graph_data,outside_temp=outside_temp,
							outside_hum=outside_hum,results=results,min_max_temps=min_max_temps,
							current_temp_html=current_temp_html,post_url=post_url,
							selected_report=selected_report,min_max_diff=min_max_diff,
							days_data=days_data,ac_runtime=ac_runtime,degrees_over_time=degrees_over_time)

if __name__ == '__main__':
	app.debug = True
	TEMPLATES_AUTO_RELOAD = True
	app.secret_key = '\x96\x8f\x05E]\xfe\xf6\xa6|\xcbY\xa9\xa0\xb9\xd0\xca\x7f[\xe8\xfc\x8c\xab}^'
	app.run(host='127.0.0.1', port=5010, debug=True)