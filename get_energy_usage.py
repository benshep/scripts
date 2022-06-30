import json
import urllib.parse

import pandas
import requests

import google_sheets
from energy_credentials import mac_address
from openweather import api_key
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!

base_url = 'https://consumer-api.data.n3rgy.com'


def today():
    return pandas.to_datetime('today').to_period('d').start_time  # + pandas.to_timedelta(1, 'd')


def dmy(date, time=True):
    """Convert datetime into dd/mm/yyyy format."""
    return date.strftime('%d/%m/%Y' + (' %H:%M' if time else ''))


def ymd(date):
    """Convert datetime into yyyy-mm-dd format."""
    return date.strftime('%Y-%m-%d')


def ymdhm(date):
    """Convert datetime into yyyymmddHHMM format."""
    return date.strftime('%Y%m%d%H%M')


def get_usage_data():
    """Write data into the 'hourly' sheet with a new row for each day and columns for hours."""
    sheet_id = '1f6RRSEl0mOdQ6Mj4an_bmNWkE8tKDjofjMjKeWL9pY8'  # ⚡️ Energy bills
    sheet_name = 'Hourly'
    columns = google_sheets.get_data(sheet_id, sheet_name, '1:1')[0]
    column_a = [cell[0] if len(cell) > 0 else '' for cell in (google_sheets.get_data(sheet_id, sheet_name, 'A:A'))]
    assert column_a[0] == 'Date'
    assert column_a[1] == 'Hour'
    new_data_row = len(column_a) + 1  # one-based when using update_cell function - this is the first empty row
    fill_top_row = 3  # zero-based when we use the autoFill function - this is the first row of data
    start_date = max(pandas.to_datetime(column_a[fill_top_row:], dayfirst=True)) + pandas.to_timedelta(1, 'd')
    if start_date >= today():  # no need to collect more data
        return

    sheet = google_sheets.spreadsheets.get(spreadsheetId=sheet_id).execute()
    grid_id = next(
        grid['properties']['sheetId'] for grid in sheet['sheets'] if grid['properties']['title'] == sheet_name)

    def fill_request(start_column, column_count, row_count):
        """Define a 'fill down' action starting at the given column index (zero-based)."""
        print(f'Fill columns {start_column=}, {fill_top_row=}, {row_count=}')
        return {'autoFill': {'useAlternateSeries': False,
                             'sourceAndDestination': {
                                 'source': {'sheetId': grid_id,
                                            'startRowIndex': fill_top_row,
                                            'endRowIndex': fill_top_row + 1,  # half-open
                                            'startColumnIndex': start_column,
                                            'endColumnIndex': start_column + column_count,
                                            }, 'dimension': 'ROWS', 'fillLength': row_count}}}

    fill_requests = []
    for fuel in 'gas', 'electricity':
        fuel_column = columns.index(fuel.title()) + 1
        fuel_data = get_fuel_data(start_date, fuel)
        assert fuel_data.size % 48 == 0  # we want a whole number of days (i.e. 48 half-hourly points)
        last_row = new_data_row + len(fuel_data) - 1
        update_range = google_sheets.get_range_spec(fuel_column, new_data_row, fuel_column + 47, last_row)
        google_sheets.update_cells(sheet_id, sheet_name, update_range, fuel_data.values.tolist())
        fill_requests.append(fill_request(fuel_column + 47, 2, last_row - fill_top_row - 1))
    # fill in date column
    update_range = google_sheets.get_range_spec(1, new_data_row, 1, last_row)
    new_dates = [[date] for date in dmy(pandas.to_datetime(fuel_data.index), False).tolist()]
    google_sheets.update_cells(sheet_id, sheet_name, update_range, new_dates)

    co2_data = get_co2_data(start_date)
    assert len(co2_data) == len(fuel_data)
    data_column = columns.index('Carbon intensity [gCO₂e/kWh]') + 1
    fill_requests.append(fill_request(data_column + 47, 53, last_row - fill_top_row - 1))
    update_range = google_sheets.get_range_spec(data_column, new_data_row, data_column + 47, last_row)
    google_sheets.update_cells(sheet_id, sheet_name, update_range, co2_data.values.tolist())

    # Fill formulae from first row
    request_body = {'requests': [fill_requests]}
    google_sheets.spreadsheets.batchUpdate(spreadsheetId=sheet_id, body=request_body).execute(num_retries=5)

    summary = google_sheets.sheets.get(spreadsheetId=sheet_id, range='usageSummary').execute()['values'][0][0]
    print(summary)
    if today().dayofweek == 1:  # notify once a week, on Tuesdays
        Pushbullet(api_key).push_note('⚡ Energy usage', summary)


def get_fuel_data(start_date, fuel):
    """Use the n3rgy API to get kWh data for gas or electricity."""
    print(f'Fetching {fuel} usage data beginning {dmy(start_date)}')
    # last_date = start_date + pandas.to_timedelta(30, 'd')
    headers = {'Authorization': mac_address}  # AUTH is my MAC code
    params = {'start': ymdhm(start_date), 'end': ymdhm(today())}
    url = f'{base_url}/{fuel}/consumption/1/?{urllib.parse.urlencode(params)}'
    print(url)
    response = requests.get(url, headers=headers)
    # print(response.json())
    df = pandas.json_normalize(response.json(), record_path='values')
    df.timestamp = pandas.to_datetime(df.timestamp)
    return pandas.pivot_table(df, index=df.timestamp.dt.date, columns=df.timestamp.dt.time, values='value').dropna()


def get_temp_data():
    """Use the OpenWeather API to fetch the last five days' worth of hourly temperatures."""
    temp_data = {}
    for date in pandas.date_range(today() - pandas.to_timedelta(5, 'd'), today() - pandas.to_timedelta(1, 'd')):
        params = {'lat': 53.460, 'lon': -2.766, 'dt': int(date.timestamp()), 'appid': api_key, 'units': 'metric'}
        url = f'https://api.openweathermap.org/data/2.5/onecall/timemachine?{urllib.parse.urlencode(params)}'
        hourly_data = json.loads(requests.get(url).text)['hourly']
        for hour, weather in enumerate(hourly_data):
            temp_data[dmy(date + pandas.to_timedelta(hour, 'h'))] = weather['temp']
    temp_data['name'] = 'mid temp'
    return temp_data


def get_co2_data(start_date):
    """Use the Carbon Intensity API to fetch CO₂ intensity data."""
    url = f'https://api.carbonintensity.org.uk/intensity/{ymd(start_date)}T00:30Z/{ymd(today())}T00:00Z'
    df = pandas.json_normalize(requests.get(url).json(), record_path='data')
    df['from'] = pandas.to_datetime(df['from'])
    df['intensity'] = df['intensity.actual'].fillna(df['intensity.forecast'])
    pivot = pandas.pivot_table(df, index=df['from'].dt.date, columns=df['from'].dt.time, values='intensity')
    return pivot.fillna('')


if __name__ == '__main__':
    get_usage_data()
