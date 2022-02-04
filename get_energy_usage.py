import json
import urllib.parse

import pandas
import polling2
import requests
import selenium.common
from webbot import Browser
from time import sleep

from google_sheets import update_cell, get_data
from energy_credentials import email, password, customer_number
from openweather import api_key

base_url = 'https://www.shellenergy.co.uk'


def poll(target, arg=None, ignore_exceptions=(selenium.common.exceptions.NoSuchElementException, ),
         check_success=polling2.is_truthy, **kwargs):
    """Poll with some default values and a single argument."""
    print(f'Polling {target.__name__} for {arg}' + (f', {kwargs}' if kwargs else ''))
    return polling2.poll(target, args=(arg, ), kwargs=kwargs, step=1, max_tries=50, check_success=check_success,
                         ignore_exceptions=ignore_exceptions)


def dmy(date):
    """Convert datetime into dd/mm/yyyy format."""
    return date.strftime('%d/%m/%Y %H:%M')


def ymd(date):
    """Convert datetime into yyyy-mm-dd format."""
    return date.strftime('%Y-%m-%d')


def actual_or_forecast(intensity):
    """Return actual intensity, or forecast if no actual one exists."""
    return intensity['actual'] or intensity['forecast']


def get_usage_data():
    web = energy_login()
    # Do last week first, then this week
    last_monday = pandas.to_datetime('today').to_period('w').start_time - pandas.to_timedelta(1, 'w')
    update_usage(get_temp_data(), last_monday, 'Gas 🔥', web)
    update_usage(get_co2_data(last_monday), last_monday, 'Electricity ⚡️', web)
    web.driver.quit()


def update_usage(extra_data, last_monday, sheet_name, web):
    sheet_id = '1f6RRSEl0mOdQ6Mj4an_bmNWkE8tKDjofjMjKeWL9pY8'  # ⚡️ Energy bills
    sheet_data = get_data(sheet_id, sheet_name, 'A:D')
    assert sheet_data[0] == ['date', 'reading', 'kWh', extra_data['name']]
    date_list = [row[0] for row in sheet_data]
    last_row = len(sheet_data) + 1
    fuel = sheet_name.split(' ')[0].lower()
    for monday in (last_monday, last_monday + pandas.to_timedelta(1, 'w')):
        for time, reading in get_kwh_data(monday, fuel, web):
            data_value = extra_data.get(time, None)
            if time not in date_list:  # new data point
                update_cell(sheet_id, sheet_name, f'A{last_row}', time)
                update_row = last_row
                last_row += 1
                action = 'append'
            else:
                update_row = date_list.index(time)
                row = sheet_data[update_row]
                no_change = float(row[2]) == reading and len(row) > 3 and float(row[3]) == data_value
                action = 'no change' if no_change else 'update'
                update_row += 1  # rows are 1-based in Sheets
            print(time, reading, data_value, action)
            if action != 'no change':
                sleep(3)  # Sheets API rate limit: 60 calls/min
                update_cell(sheet_id, sheet_name, f'C{update_row}', reading)
                if data_value:
                    update_cell(sheet_id, sheet_name, f'D{update_row}', data_value)


def energy_login():
    """Log in to energy provider website."""
    print('Logging in')
    web = Browser(showWindow=True)
    web.go_to(f'{base_url}/my/energy/gas')
    web.type(email, 'email')
    web.type(password, 'password')
    web.click('Log in')
    poll(web.exists, 'My week')
    return web


def get_kwh_data(start_date, fuel, web):
    """Use the energy provider API to get kWh data for gas or electricity."""
    print(f'Fetching {fuel} usage data for week beginning {dmy(start_date)}')
    # The API only seems to return results when start_date is Monday and end_date is Sunday
    last_date = start_date + pandas.to_timedelta(6, 'd')
    week = pandas.date_range(start_date, last_date)
    params = {'startdate': ymd(start_date), 'enddate': ymd(last_date), 'customerNumber': customer_number,
              'isDualFuel': 'true', 'fuelType': fuel}
    web.go_to(f'{base_url}/my/energy/api/usage?{urllib.parse.urlencode(params)}')
    data = json.loads(web.driver.find_element_by_xpath('/*').text)
    if not (data['ok'] and data['usageData']['isAvailable']):
        print(f'No data for {fuel}')
        return []
    hourly_data = data['usageData']['data']['hourlyValues']['cost']
    # Some 'readings' are placeholders: only use ones marked 'ACTUAL'
    kwh_data = [[reading['usage'] for reading in hours if reading['type'] == 'ACTUAL'] for hours in hourly_data]
    return [(dmy(date + hour * pandas.to_timedelta(1, 'h')), reading)
            for date, day in zip(week, kwh_data)
            for hour, reading in enumerate(day)]


def get_temp_data():
    """Use the OpenWeather API to fetch the last five days' worth of hourly temperatures."""
    temp_data = {}
    today = pandas.to_datetime('today').to_period('d').start_time
    for date in pandas.date_range(today - pandas.to_timedelta(5, 'd'), today):
        params = {'lat': 53.460, 'lon': -2.766, 'dt': int(date.timestamp()), 'appid': api_key, 'units': 'metric'}
        url = f'https://api.openweathermap.org/data/2.5/onecall/timemachine?{urllib.parse.urlencode(params)}'
        hourly_data = json.loads(requests.get(url).text)['hourly']
        for hour, weather in enumerate(hourly_data):
            temp_data[dmy(date + pandas.to_timedelta(hour, 'h'))] = weather['temp']
    temp_data['name'] = 'mid temp'
    return temp_data


def get_co2_data(start_date):
    """Use the Carbon Intensity API to fetch two weeks' worth of CO₂ intensities."""
    one_day = pandas.to_timedelta(1, 'd')
    end_date = start_date + one_day * 14
    # TODO: deal with daylight saving change?
    url = f'https://api.carbonintensity.org.uk/intensity/{ymd(start_date)}T00:00Z/{ymd(end_date)}T00:00Z'
    co2_data = json.loads(requests.get(url).text)['data']

    # This comes in half-hour intervals: average over an hour to match up with the hourly usage data
    def hour_avg(i):
        """Return the average of the intensities at position i and i + 1."""
        return (actual_or_forecast(co2_data[i]['intensity']) + actual_or_forecast(co2_data[i + 1]['intensity'])) / 2

    # start at second point: first one is always half an hour behind start time requested
    co2_data = {dmy(pandas.to_datetime(co2_data[i]['from'])): hour_avg(i) for i in range(1, len(co2_data) - 1, 2)}
    co2_data['name'] = 'gCO₂e/kWh'
    return co2_data


if __name__ == '__main__':
    get_usage_data()
