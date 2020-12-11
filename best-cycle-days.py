#!python3
# -*- coding: utf-8 -*-
import requests
import json
from datetime import datetime, timedelta
import win32com.client
from ftp import ftp

today = datetime.today()
days_left = 2 ** (max(-1, 3 - today.weekday()) % 5 + 1) - 1  # 0b11111 for Fri-Sun, 0b01111 for Mon, etc
next_week = today + timedelta(days=9)
am, pm = '07:00', '16:00'
good_wind = {am: ('W', 'WNW', 'NW', 'NNW', 'N', 'NNE', 'NE'), pm: ('ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW')}
bad_weather_types = ('rain', 'snow', 'sleet', 'hail', 'drizzle')

# get last activity from Google Sheet
tsv_url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vSlaVqOG-r1OKnew5q5xwGUjV8R7wvvwehUwl4Y3dTV5m-vGA2xFx714Xd7YNNtG_pV5rXi0zUwNQgb/pub?gid=494572448&single=true&output=tsv'
date, activity = requests.get(tsv_url).content.decode('utf-8').replace('\xa0', ' ').split('\t')
print(date)
# is it a commute today?
cycled_today = (activity.startswith('Home to work') or activity.startswith('Work to home')) \
               and datetime.strptime(date, '%d %b %y') == today

# get meetings from Outlook calendar
appointments = win32com.client.Dispatch('Outlook.Application').GetNamespace('MAPI').GetDefaultFolder(9).Items
appointments.Sort("[Start]")
appointments.IncludeRecurrences = True
date_format = "%d/%m/%Y"
restriction = "[Start] >= '{}' AND [End] <= '{}'".format(today.strftime(date_format), next_week.strftime(date_format))
end_day_mtgs = []
yyyymmdd = '%Y-%m-%d'
for appointmentItem in appointments.Restrict(restriction):
    try:
        start = datetime.fromtimestamp(appointmentItem.Start.timestamp())
        end = datetime.fromtimestamp(appointmentItem.End.timestamp())
        if (start.hour <= 8 or end.hour >= 16) and not appointmentItem.AllDayEvent and appointmentItem.BusyStatus == 2:  # busy
            end_day_mtgs.append((start.strftime(yyyymmdd), appointmentItem.Subject.strip(), start, end))
    except OSError:  # appointments with weird dates!
        pass

days = []
unique_days = set()
response = json.loads(requests.get('https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/2650272').content)
for day in response['forecasts']:
    for hour in day['detailed']['reports']:
        time = hour['timeslot']
        local_date = hour['localDate']
        date = datetime.strptime(local_date, yyyymmdd)
        if time in (am, pm) and date.weekday() < 5 and next_week > date > today:  # Monday-Friday
            wind = int(hour['windSpeedMph'])
            wind_dir = hour['windDirectionAbbreviation']
            rain = int(hour['precipitationProbabilityInPercent'])
            weather_type = hour['weatherTypeText'].lower()
            wind_badness = 3 if wind > 18 else 2 if wind > 12 else 1
            if wind_dir in good_wind[time] and wind_badness > 1:  # significant tail(ish) wind?
                wind_badness -= 1
            rain_badness = 3 if rain > 60 else 2 if rain > 30 else 1
            badness = wind_badness * rain_badness
            stars = 3 if badness < 2 else 2 if badness < 3 else 1 if badness < 5 else 0
            days.append((local_date, time, stars, wind, wind_dir, rain, weather_type))
            print(local_date, time, wind, rain, wind_dir, stars * '*')
            unique_days.add(local_date)

page = '<html><head><title>Cycle days</title></head><body>'
combos = [0b10101, 0b10010, 0b10001, 0b01010, 0b01001, 0b00101, 0b10000, 0b01000, 0b00100, 0b00010, 0b00001]
total_stars = {}
stars_days = {}
is_this_week = True
hhmm = '%H:%M'
ddd_ddmm = '%a %d/%m'
for day in sorted(list(unique_days)):
    date = datetime.strptime(day, yyyymmdd)
    weekday = date.weekday()
    summary = ''
    appts = ' '.join(['<br>{}-{} {}'.format(start.strftime(hhmm), end.strftime(hhmm), subject) for d, subject, start, end in end_day_mtgs if d == day])
    for local_date, time, stars, wind, wind_dir, rain, weather_type in days:
        if local_date == day:
            summary += '<br>' + ('am: ' if time == am else 'pm: ') + f'{wind} mph {wind_dir}, {rain}%  '
            for bad_weather_type in bad_weather_types:
                if bad_weather_type in weather_type:
                    summary += weather_type
                    break
    stars = min([stars for ld, t, stars, w, wd, r, wt in days if ld == day])
    page += '<p><b>{}</b> {} {} {}</p>'.format(date.strftime(ddd_ddmm), '&#9670;' * stars, summary, appts)
    if is_this_week:
        stars += 0.5 if weekday in (0, 2) else 0  # bonus for Mon, Wed
        stars -= 2 if cycled_today else 0
        stars -= 1 if appts else 0  # penalty for late meeting
        stars -= 0.1 * (weekday - today.weekday() - 1)  # later forecasts get slight penalty
        stars_days[2 ** (4 - weekday)] = stars
    print(date.strftime(ddd_ddmm), '*' * min([stars for ld, t, stars, w, wd, r, wt in days if ld == day]), summary, appts)
    if weekday == 4:
        is_this_week = False  # stop at Friday
        page += '<hr>'
    # is_this_week = is_this_week and weekday < 4  # stop at Friday

print(stars_days)
for combo in combos:
    if days_left | combo == days_left:
        total_stars[combo] = sum([stars for day, stars in stars_days.items() if day & combo])
        print(f'{combo:05b}', total_stars[combo])
max_stars = max(total_stars.values())
weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
for combo, stars in total_stars.items():
    if stars == max_stars:
        best_combo = ', '.join([day for day, use in zip(weekdays, list(f'{combo:05b}')) if use == '1'])
        break

updateTime = datetime.now().strftime('%a %d/%m at %H:%M')
open('temp.html', 'w').write(f'<p>Best: {best_combo}<br>Updated {updateTime}</p>{page}</body></html>')
ftp.storlines('STOR index.html', open('temp.html', 'rb'))
