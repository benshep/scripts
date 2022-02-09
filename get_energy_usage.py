import json
import urllib.parse

import pandas
import polling2
import requests
import selenium.common
from webbot import Browser
from time import sleep
from itertools import groupby

import google_sheets
from energy_credentials import email, password, customer_number
from openweather import api_key

base_url = 'https://www.shellenergy.co.uk'


def poll(target, arg=None, ignore_exceptions=(selenium.common.exceptions.NoSuchElementException, ),
         check_success=polling2.is_truthy, **kwargs):
    """Poll with some default values and a single argument."""
    print(f'Polling {target.__name__} for {arg}' + (f', {kwargs}' if kwargs else ''))
    return polling2.poll(target, args=(arg, ), kwargs=kwargs, step=1, max_tries=50, check_success=check_success,
                         ignore_exceptions=ignore_exceptions)


def dmy(date, time=True):
    """Convert datetime into dd/mm/yyyy format."""
    return date.strftime('%d/%m/%Y' + (' %H:%M' if time else ''))


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
    # update_usage(get_temp_data(), last_monday, 'Gas 🔥', web)
    # update_usage(get_co2_data(last_monday), last_monday, 'Electricity ⚡️', web)
    update_usage_hourly_sheet(get_temp_data(flatten=False), last_monday, 'gas', web)
    update_usage_hourly_sheet(get_co2_data(last_monday, flatten=False), last_monday, 'electricity', web)
    web.driver.quit()


def update_usage_hourly_sheet(extra_data, last_monday, fuel, web):
    """Write data into the 'hourly' sheet with a new row for each day and columns for hours."""
    sheet_id = '1f6RRSEl0mOdQ6Mj4an_bmNWkE8tKDjofjMjKeWL9pY8'  # ⚡️ Energy bills
    sheet_name = 'Hourly'
    columns = google_sheets.get_data(sheet_id, sheet_name, '1:1')[0]
    fuel_column = columns.index(fuel.title() + ' [pence]') + 1
    data_column = columns.index('Temperature [°C]' if fuel == 'gas' else 'Carbon intensity [gCO₂e/kWh]') + 1
    column_a = [cell[0] if len(cell) > 0 else '' for cell in (google_sheets.get_data(sheet_id, sheet_name, 'A:A'))]
    assert column_a[0] == 'Date'
    assert column_a[1] == 'Hour'
    new_data_row = len(column_a) + 1  # one-based when using update_cell function - this is the first empty row
    fill_top_row = 3  # zero-based when we use the autoFill function - this is the first row of data
    assert not pandas.isnull(pandas.to_datetime(column_a[fill_top_row]))  # ensure this row starts with a date
    rows_of_data = len(column_a) - fill_top_row
    for monday in (last_monday, last_monday + pandas.to_timedelta(1, 'w')):
        for date, readings in get_fuel_data(monday, fuel, web, flatten=False):
            if not readings:  # no data
                continue
            data_value = extra_data.get(date, None)
            if date in column_a:
                update_row = column_a.index(date) + 1  # rows are 1-based in Sheets
                action = 'update'
            else:  # new data point
                google_sheets.update_cell(sheet_id, sheet_name, f'A{new_data_row}', date)
                update_row = new_data_row
                new_data_row += 1
                action = 'append'
                rows_of_data += 1
            update_range = google_sheets.get_range_spec(fuel_column, update_row, fuel_column + 23, update_row)
            print(date, action, readings, data_value)
            sleep(3)  # Sheets API rate limit: 60 calls/min
            google_sheets.update_cells(sheet_id, sheet_name, update_range, [readings])
            if data_value:
                update_range = google_sheets.get_range_spec(data_column, update_row, data_column + 23, update_row)
                google_sheets.update_cells(sheet_id, sheet_name, update_range, [data_value])
    # Fill formulae from previous row
    sheet = google_sheets.spreadsheets.get(spreadsheetId=sheet_id).execute()
    grid_id = next(grid['properties']['sheetId'] for grid in sheet['sheets'] if grid['properties']['title'] == sheet_name)
    def fill_request(start_column):
        """Define a 'fill down' action starting at the given column index (zero-based)."""
        print(f'Fill columns {start_column=}, {fill_top_row=}, {rows_of_data=}')
        return {'autoFill': {'useAlternateSeries': False,
                                   'sourceAndDestination': {
                                       'source': {'sheetId': grid_id,
                                           'startRowIndex': fill_top_row,
                                           'endRowIndex': fill_top_row + 1,  # half-open
                                           'startColumnIndex': start_column,
                                           'endColumnIndex': start_column + 27,  # fill 28 columns (24h + 2 either side)
                                       }, 'dimension': 'ROWS', 'fillLength': rows_of_data - 1}}}
    request_body = {'requests': [fill_request(fuel_column + 23),  # kWh columns (convert to zero-based)
                                 fill_request(data_column + 23)]}  # data columns (i.e. CO₂ values for electricity)
    google_sheets.spreadsheets.batchUpdate(spreadsheetId=sheet_id, body=request_body).execute(num_retries=5)


def update_usage(extra_data, last_monday, sheet_name, web):
    """Write data into the 'electricity' and 'gas' worksheets with a new row for each hour."""
    sheet_id = '1f6RRSEl0mOdQ6Mj4an_bmNWkE8tKDjofjMjKeWL9pY8'  # ⚡️ Energy bills
    sheet_data = google_sheets.get_data(sheet_id, sheet_name, 'A:D')
    assert sheet_data[0] == ['date', 'reading', 'price', extra_data['name']]
    date_list = [row[0] for row in sheet_data]
    last_row = len(sheet_data) + 1
    fill_top_row = len(sheet_data) - 1  # zero-based when we use the autoFill function
    rows_appended = 0
    fuel = sheet_name.split(' ')[0].lower()
    for monday in (last_monday, last_monday + pandas.to_timedelta(1, 'w')):
        for time, reading in get_fuel_data(monday, fuel, web):
            data_value = extra_data.get(time, None)
            if time not in date_list:  # new data point
                google_sheets.update_cell(sheet_id, sheet_name, f'A{last_row}', time)
                update_row = last_row
                last_row += 1
                action = 'append'
                rows_appended += 1
            else:
                update_row = date_list.index(time)
                row = sheet_data[update_row]
                no_change = float(row[2]) == reading and len(row) > 3 and float(row[3]) == data_value
                action = 'no change' if no_change else 'update'
                update_row += 1  # rows are 1-based in Sheets
            print(time, reading, data_value, action)
            if action != 'no change':
                sleep(3)  # Sheets API rate limit: 60 calls/min
                google_sheets.update_cell(sheet_id, sheet_name, f'C{update_row}', reading)
                if data_value:
                    google_sheets.update_cell(sheet_id, sheet_name, f'D{update_row}', data_value)
    # Fill formulae from previous row
    request_body = {'requests': [{'autoFill': {'useAlternateSeries': False,
                                   'sourceAndDestination': {
                                       'source': {'sheetId': 34507986 if fuel == 'gas' else 1280998411,  # how to get this?
                                           'startRowIndex': fill_top_row,
                                           'endRowIndex': fill_top_row + 1,  # half-open
                                           'startColumnIndex': 4,  # kWh
                                           'endColumnIndex': 10 if fuel == 'gas' else 8,  # kWh/month
                                       }, 'dimension': 'ROWS', 'fillLength': rows_appended}}}]}
    google_sheets.spreadsheets.batchUpdate(spreadsheetId=sheet_id, body=request_body).execute(num_retries=5)


def energy_login():
    """Log in to energy provider website."""
    print('Logging in')
    web = Browser(showWindow=False)
    web.go_to(f'{base_url}/my/energy/gas')
    web.type(email, 'email')
    web.type(password, 'password')
    web.click('Log in')
    poll(web.exists, 'My week')
    return web


def get_fuel_data(start_date, fuel, web, flatten=True):
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
    # TODO: these are NOT in kWh but in pence! Need to translate to kWh using spreadsheet
    kwh_data = [[reading['usage'] for reading in hours if reading['type'] == 'ACTUAL'] for hours in hourly_data]
    return [(dmy(date + hour * pandas.to_timedelta(1, 'h')), reading)
            for date, day in zip(week, kwh_data)
            for hour, reading in enumerate(day)] if flatten else zip([dmy(date, time=False) for date in week], kwh_data)


def get_temp_data(flatten=True):
    """Use the OpenWeather API to fetch the last five days' worth of hourly temperatures."""
    temp_data = {}
    today = pandas.to_datetime('today').to_period('d').start_time
    for date in pandas.date_range(today - pandas.to_timedelta(5, 'd'), today):
        params = {'lat': 53.460, 'lon': -2.766, 'dt': int(date.timestamp()), 'appid': api_key, 'units': 'metric'}
        url = f'https://api.openweathermap.org/data/2.5/onecall/timemachine?{urllib.parse.urlencode(params)}'
        hourly_data = json.loads(requests.get(url).text)['hourly']
        if flatten:
            for hour, weather in enumerate(hourly_data):
                temp_data[dmy(date + pandas.to_timedelta(hour, 'h'))] = weather['temp']
        else:
            temp_data[dmy(date, time=False)] = [weather['temp'] for weather in hourly_data]
    temp_data['name'] = 'mid temp'
    return temp_data


def get_co2_data(start_date, flatten=True):
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
    co2_data = [(dmy(pandas.to_datetime(co2_data[i]['from'])), hour_avg(i)) for i in range(1, len(co2_data) - 1, 2)]
    if not flatten:  # roll up hourly data into a list for each day
        grouped = groupby(co2_data, lambda point: point[0][:10])  # just the date part
        co2_data = [(date, [point[1] for point in points]) for date, points in grouped]
    co2_data = dict(co2_data)
    co2_data['name'] = 'gCO₂e/kWh'
    return co2_data


if __name__ == '__main__':
    # auto_fill_test()
    get_usage_data()
