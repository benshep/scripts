import datetime
import time
from urllib.parse import urlencode

import requests

from locations import home, bike_shed
from openweather import api_key

api_url = 'https://api.openweathermap.org/data/3.0/onecall/timemachine?'


def one_day():
    date = datetime.datetime(2023, 8, 24, 7, 30, 0)
    unix_time = int(time.mktime(date.timetuple()))
    query = urlencode({'lat': home['latitude'], 'lon': home['longitude'],
                       'dt': unix_time, 'appid': api_key, 'units': 'metric'})
    url = f'{api_url}{query}'
    # REMEMBER: free up to 1000 API calls per day
    r = requests.get(url)
    response = r.json()
    data = response['data'][0]
    overview = data['weather'][0]
    print(date.strftime('%d/%m/%y %H:%M'),
          data['temp'],
          overview['main'],
          overview['description'],
          data['wind_deg'],
          data['wind_speed'] * 3600 / 1609.34,  # convert m/s to mph
          # data['sunrise'] < data['dt'] < data['sunset'],
          sep='\t')


def loop_days():
    date = datetime.datetime(2024, 11, 19, 12, 0, 0)

    request_count = 0
    while date <= datetime.datetime.now():
        # if date.weekday() > 4 or date.hour < 8:  # skip evenings and weekends
        #     continue
        unix_time = int(time.mktime(date.timetuple()))
        url = f'{api_url}lat={bike_shed["latitude"]}&lon={bike_shed["longitude"]}&dt={unix_time}&appid={api_key}'
        # REMEMBER: free up to 1000 API calls per day
        r = requests.get(url)
        request_count += 1
        if request_count >= 1000:
            break
        response = r.json()
        data = response['data'][0]
        # print(data)
        print(date.strftime('%d/%m/%y %H:%M'), '', '',  # leave two blank columns to match spreadsheet layout
              data['temp'], data['wind_speed'], data['wind_deg'],  # data['sunrise'] < data['dt'] < data['sunset'],
              data['weather'][0]['main'], data['weather'][0]['description'], sep='\t')
        date += datetime.timedelta(hours=24)

    print(f'{request_count=}')


def loop_hours():
    date = datetime.datetime(2023, 8, 24, 0, 0, 0)

    request_count = 0
    while request_count < 48:
        # while date <= datetime.datetime.now():
        # if date.weekday() > 4 or date.hour < 8:  # skip evenings and weekends
        #     continue
        unix_time = int(time.mktime(date.timetuple()))
        url = f'{api_url}lat={bike_shed["latitude"]}&lon={bike_shed["longitude"]}&dt={unix_time}&appid={api_key}'
        # REMEMBER: free up to 1000 API calls per day
        r = requests.get(url)
        request_count += 1
        if request_count >= 1000:
            break
        response = r.json()
        data = response['data'][0]
        # print(data)
        print(date.strftime('%d/%m/%y %H:%M'), data['clouds'], data['temp'], data['wind_speed'], data['wind_deg'],
              # data['sunrise'] < data['dt'] < data['sunset'],
              data['weather'][0]['main'], data['weather'][0]['description'], sep='\t')
        date += datetime.timedelta(minutes=30)

    print(f'{request_count=}')


if __name__ == '__main__':
    loop_days()
