import json
import time
import urllib.parse
from typing import Any
from enum import IntEnum, StrEnum

import pandas
import requests
from pandas import DataFrame, Timestamp
from tabulate import tabulate

import google_api
import energy_credentials
from openweather import api_key

base_url = 'https://consumer-api.data.n3rgy.com'
carbon_int_url = 'https://api.carbonintensity.org.uk'
octopus_url = 'https://api.octopus.energy/v1'
home_postcode = 'WA10'


def today():
    """Return a datetime object representing the start of today."""
    return pandas.to_datetime('today').to_period('d').start_time  # - pandas.to_timedelta(3, 'd')


def dmy(date, time=True):
    """Convert datetime into dd/mm/yyyy format, and optionally HH:MM."""
    return date.strftime('%d/%m/%Y' + (' %H:%M' if time else ''))


def ymd(date, time=False):
    """Convert datetime into yyyy-mm-dd format (ISO 8601), and optionally THH:MM."""
    return date.strftime('%Y-%m-%d' + ('T%H:%MZ' if time else ''))


def ymdhm(date):
    """Convert datetime into yyyymmddHHMM format."""
    return date.strftime('%Y%m%d%H%M')


def get_usage_data(remove_incomplete_rows=True):
    """Write data into the 'hourly' sheet with a new row for each day and columns for hours."""
    sheet_id = '1f6RRSEl0mOdQ6Mj4an_bmNWkE8tKDjofjMjKeWL9pY8'  # ⚡️ Energy bills
    sheet_name = 'Hourly'
    columns = google_api.get_data(sheet_id, sheet_name, '1:1')[0]
    column_a = google_api.get_data(sheet_id, sheet_name, 'A:A')
    column_a = [cell[0] if len(cell) > 0 else '' for cell in column_a]  # transpose, flatten
    assert column_a[0] == 'Date'
    assert column_a[1] == 'Hour'
    fill_top_row = len(column_a) - 1  # zero-based when we use the autoFill function - this is the last row of data
    new_data_row = fill_top_row + 2  # one-based when using update_cell function - this is the first empty row
    start_date = pandas.to_datetime(column_a[-1], dayfirst=True) + pandas.to_timedelta(1, 'd')
    if start_date >= today():  # no need to collect more data
        return

    sheet = google_api.spreadsheets.get(spreadsheetId=sheet_id).execute()
    grid_id = next(g['properties']['sheetId'] for g in sheet['sheets'] if g['properties']['title'] == sheet_name)

    def fill_request(start_column, column_count, row_count):
        """Define a 'fill down' action starting at the given column index (zero-based)."""
        print(f'Fill columns {start_column=}, {fill_top_row=}, {row_count=}')
        return {'autoFill': {'useAlternateSeries': False, 'sourceAndDestination': {
                                 'source': {'sheetId': grid_id, 'startRowIndex': fill_top_row,
                                            'endRowIndex': fill_top_row + 1,  # half-open
                                            'startColumnIndex': start_column,
                                            'endColumnIndex': start_column + column_count,
                                            }, 'dimension': 'ROWS', 'fillLength': row_count}}}

    fill_requests = []
    data_titles = 'gas', 'electricity', 'carbon intensity'
    all_fuel_data = [get_fuel_data(start_date, data_title, remove_incomplete_rows) for data_title in data_titles]
    print(all_fuel_data)
    # truncate all of them to size of the smallest, keeping only a whole number of days (i.e. 48 half-hourly periods)
    min_size = min(len(fuel_data) for fuel_data in all_fuel_data)
    if min_size == 0:
        empty_sets = ', '.join(title for title, data in zip(data_titles, all_fuel_data) if len(data) == 0)
        print(f'No new {empty_sets} data received')
        return False
    all_fuel_data = [fuel_data.head(min_size) for fuel_data in all_fuel_data]
    # check all dates are the same
    if len({tuple(fuel_data.axes[0].to_list()) for fuel_data in all_fuel_data}) > 1:
        print('Not all dates are identical in energy datasets')
        return False  # postpone data entry
    for fuel, fuel_data in zip(data_titles, all_fuel_data):
        fuel_column = columns.index(fuel.title()) + 1
        last_row = new_data_row + len(fuel_data) - 1
        fill_row_count = last_row - fill_top_row - 1
        update_range = google_api.get_range_spec(fuel_column, new_data_row, fuel_column + 47, last_row)
        google_api.update_cells(sheet_id, sheet_name, update_range, fuel_data.values.tolist())
        fill_col_count = 53 if fuel == 'carbon intensity' else 2  # fill 'carbon' columns too (elec use x intensity)
        fill_requests.append(fill_request(fuel_column + 47, fill_col_count, fill_row_count))
    # fill in date column
    update_range = google_api.get_range_spec(1, new_data_row, 1, last_row)
    new_dates = [[date] for date in dmy(pandas.to_datetime(fuel_data.index), False).tolist()]
    google_api.update_cells(sheet_id, sheet_name, update_range, new_dates)
    fill_requests.append(fill_request(1, 1, fill_row_count))  # BST helper column
    fill_requests.append(fill_request(253, 4, fill_row_count))  # Octopus Tracker rates (IT:IW)
    # Fill formulae from first row
    request_body = {'requests': [fill_requests]}
    google_api.spreadsheets.batchUpdate(spreadsheetId=sheet_id, body=request_body).execute(num_retries=5)
    # Get the summary cell to go in a toast
    summary = google_api.sheets.get(spreadsheetId=sheet_id, range='usageSummary').execute()['values'][0][0]
    # Add the minimum and maximum forecasted intensity for the next 2 days
    if (forecast := get_regional_intensity()) is not None:  # will be None if this API call fails
        for minmax in ('min', 'max'):
            row = forecast.iloc[getattr(forecast['intensity.forecast'], f'idx{minmax}')()]
            gen_mix = pandas.DataFrame.from_dict(row['generationmix'])
            highest = gen_mix.iloc[gen_mix['perc'].idxmax()]
            summary += f"\n{minmax.title()}: {row['intensity.forecast']} gCO₂e, " \
                       f"{row['to'].strftime('%a %H:%M')}, {highest['perc']:.0f}% {highest['fuel']}"

    return summary


def fill_old_carbon_data():
    """Fill in carbon data retrospectively."""
    sheet_id = '1f6RRSEl0mOdQ6Mj4an_bmNWkE8tKDjofjMjKeWL9pY8'  # ⚡️ Energy bills
    sheet_name = 'Hourly'
    columns = google_api.get_data(sheet_id, sheet_name, '1:1')[0]
    column_a = [cell[0] if len(cell) > 0 else '' for cell in (google_api.get_data(sheet_id, sheet_name, 'A:A'))]
    assert column_a[0] == 'Date'
    assert column_a[1] == 'Hour'
    start_date = pandas.to_datetime('2023-01-01 00:00')
    new_data_row = 528  # one-based when using update_cell function - this is the first empty row
    while start_date < today():
        print(start_date)

        data_titles = ['regional carbon intensity']
        all_fuel_data = [get_fuel_data(start_date, data_title) for data_title in data_titles]
        print(all_fuel_data)
        # check all dates are the same
        if len({tuple(fuel_data.axes[0].to_list()) for fuel_data in all_fuel_data}) > 1:
            return False  # postpone data entry
        for fuel, fuel_data in zip(data_titles, all_fuel_data):
            fuel_column = columns.index(fuel.title()) + 1
            last_row = new_data_row + len(fuel_data) - 1
            update_range = google_api.get_range_spec(fuel_column, new_data_row, fuel_column + 47, last_row)
            google_api.update_cells(sheet_id, sheet_name, update_range, fuel_data.values.tolist())

        start_date += pandas.to_timedelta(14, 'd')
        new_data_row += 14
        return


def get_fuel_data_n3rgy(start_date, fuel, remove_incomplete_rows=True):
    """Use the n3rgy API to get kWh data for gas or electricity."""
    print(f'Fetching {fuel} data beginning {dmy(start_date)}')
    if 'carbon intensity' in fuel:
        return get_co2_data(start_date, remove_incomplete_rows=remove_incomplete_rows)
    # last_date = start_date + pandas.to_timedelta(30, 'd')
    headers = {'Authorization': energy_credentials.mac_address}  # AUTH is my MAC code
    params = {'start': ymdhm(start_date), 'end': ymdhm(today())}
    url = f'{base_url}/{fuel}/consumption/1/?{urllib.parse.urlencode(params)}'
    print(url)
    response = requests.get(url, headers=headers)
    # print(response.json())
    df = pandas.json_normalize(response.json(), record_path='values')
    df.timestamp = pandas.to_datetime(df.timestamp)
    data = pandas.pivot_table(df, index=df.timestamp.dt.date, columns=df.timestamp.dt.time, values='value')
    data = data.dropna() if remove_incomplete_rows else data.fillna(-1)
    return data if data.shape[1] == 48 else pandas.DataFrame()  # must be n x 48 DataFrame


def get_fuel_data(start_date, fuel, remove_incomplete_rows=True):
    """Use the Octopus API to get kWh data for gas or electricity."""
    print(f'Fetching {fuel} data beginning {dmy(start_date)}')
    if 'carbon intensity' in fuel:
        return get_co2_data(start_date, remove_incomplete_rows=remove_incomplete_rows)

    # https://www.guylipman.com/octopus/api_guide.html#s3
    # spreadsheet expects *end* times going from 00:00 to 23:30 - shift requested time back by half an hour
    half_hour = pandas.to_timedelta(30, 'min')
    start_date -= half_hour
    end_date = today() - half_hour
    params = {'page_size': (end_date - start_date).days * 48, 'period_from': ymd(start_date, True),
              'period_to': ymd(end_date, True), 'order_by': 'period'}
    url = '/'.join([octopus_url, fuel + '-meter-points', energy_credentials.mpan[fuel], 'meters',
                    energy_credentials.meter_serial_number[fuel], 'consumption', '?']) + urllib.parse.urlencode(params)
    # print(url)
    response = requests.get(url, auth=(energy_credentials.octopus_api_key, ''))
    json = response.json()
    # print(json)
    if json['count'] == 0:  # no results
        return []
    df = pandas.json_normalize(json, record_path='results')
    df.interval_end = pandas.to_datetime(df.interval_end, utc=True)
    data = pandas.pivot_table(df, index=df.interval_end.dt.date, columns=df.interval_end.dt.time, values='consumption')
    data = data.dropna() if remove_incomplete_rows else data.fillna(-1)
    return data if data.shape[1] == 48 else pandas.DataFrame()  # must be n x 48 DataFrame


def get_temp_data() -> dict[str, str]:
    """Use the OpenWeather API to fetch the last five days' worth of hourly temperatures."""
    temp_data = {}
    for date in pandas.date_range(today() - pandas.to_timedelta(5, 'd'),
                                  today() - pandas.to_timedelta(1, 'd')):
        params = {'lat': 53.460, 'lon': -2.766, 'dt': int(date.timestamp()), 'appid': api_key, 'units': 'metric'}
        url = f'https://api.openweathermap.org/data/2.5/onecall/timemachine?{urllib.parse.urlencode(params)}'
        json_data = json.loads(requests.get(url).text)
        print(json_data)
        hourly_data = json_data['hourly']
        for hour, weather in enumerate(hourly_data):
            temp_data[dmy(date + pandas.to_timedelta(hour, 'h'))] = weather['temp']
    temp_data['name'] = 'mid temp'
    return temp_data


class RegionId(IntEnum):
    """Region names as defined by the Carbon Intensity API.
    See https://carbon-intensity.github.io/api-definitions/#region-list"""
    north_scotland = 1
    south_scotland = 2
    north_west_england = 3
    north_east_england = 4
    yorkshire = 5
    north_wales = 6
    south_wales = 7
    west_midlands = 8
    east_midlands = 9
    east_england = 10
    south_west_england = 11
    south_england = 12
    london = 13
    south_east_england = 14
    england = 15
    scotland = 16
    wales = 17


def get_co2_data(start_date: Timestamp, geography: str | int | RegionId = home_postcode,
                 remove_incomplete_rows: bool = True) -> DataFrame:
    """Use the Carbon Intensity API to fetch regional or national CO₂ intensity data.
    :param geography: Can be a postcode or one of the region IDs.
    Leave geography blank to get national data.
    :param remove_incomplete_rows: Specify False to fill in -1 values where there are data gaps."""
    end_date = min(today(), start_date + pandas.to_timedelta(14, 'd'))  # can't get more than 14 days at a time
    end_date -= pandas.to_timedelta(1, 'd')
    if geography:
        area = 'regional/'
        suffix = f'/postcode/{geography}' if isinstance(geography, str) else f'/regionid/{geography}'
    else:
        area, suffix = '', ''
    url = f'{carbon_int_url}/{area}intensity/{ymd(start_date)}T00:00Z/{ymd(end_date)}T23:30Z{suffix}'
    # print(url)
    json = get_json(url)
    # print(json)
    # path is data.data for regional
    df = pandas.json_normalize(json, record_path=['data', 'data'] if geography else ['data'])
    df['to'] = pandas.to_datetime(df['to'])
    # use 'actual' value where available with national. For regional, we only see 'forecast' values
    df['intensity'] = df['intensity.forecast'] if geography else df['intensity.actual'].fillna(df['intensity.forecast'])
    pivot = pandas.pivot_table(df, index=df['to'].dt.date, columns=df['to'].dt.time, values='intensity')
    # Add an extra day (sometimes necessary when data is missing)
    # pivot.loc[pivot.index[0] + pandas.to_timedelta(1, 'd')] = [pandas.NA] * 48
    # pivot = pivot.sort_index()

    # use fillna when data seems to be permanently missing - we can get incomplete days and fill in the gaps manually
    return pivot.dropna() if remove_incomplete_rows else pivot.fillna(-1)


def get_json(url, retries=3):
    """Attempt to fetch JSON data from a URL, retrying a number of times (default 3)."""
    while (attempt := 0) < retries:
        json = requests.get(url).json()
        if 'error' not in json:
            break
        attempt += 1
        print(f'Failed to get data from {url=} on {attempt=}')
    else:
        raise ValueError(f'Bad response from server after {retries=}: {json["error"]}')
    return json


def get_regional_intensity(start_time='now', postcode=home_postcode):
    """Use the Carbon Intensity API to fetch the regional CO₂ intensity forecast."""
    start_time = ymd(pandas.to_datetime(start_time), time=True)
    json = get_json(f'{carbon_int_url}/regional/intensity/{start_time}/fw48h/postcode/{postcode}')
    try:
        df = pandas.json_normalize(json, record_path=['data', 'data'])  # path is data.data for regional
    except KeyError:  # problem with JSON, maybe forecasts not working?
        return None
    df['to'] = pandas.to_datetime(df['to'])
    return df


def get_old_data_avg():
    """Get the two-week average of carbon data."""
    start_date = today() - pandas.to_timedelta(7, 'd')  # to align to previous dataset
    start_date = pandas.to_datetime('2025-01-01')
    while start_date < today():
        # start_date -= pandas.to_timedelta(14, 'd')
        # data = get_co2_data(start_date, postcode='OX11')
        # south = data.mean().mean()  # average of whole DataFrame
        data = get_co2_data(start_date, geography=RegionId.south_scotland)
        scotland = data.mean().mean()  # average of whole DataFrame
        # data = get_co2_data(start_date, postcode='')  # national
        # national = data.mean().mean()  # average of whole DataFrame
        print(start_date, '', '',
              # south,
              scotland,
              # national,
              sep='\t')
        start_date += pandas.to_timedelta(14, 'd')
        # return


def get_regions_data_avg():
    """Get the two-week average of carbon data for all regions."""
    start_date = pandas.to_datetime('2025-01-01')
    while start_date < today():
        mean_data = [get_co2_data(start_date, geography=region).mean().mean()
                     for region in range(min(RegionId), max(RegionId) + 1)]

        print(start_date, *mean_data, sep='\t')
        start_date += pandas.to_timedelta(14, 'd')


def get_mix(start_time='now', postcode=home_postcode):
    """Return the regional energy mix for a 48h period."""
    data = get_regional_intensity(start_time, postcode)
    return pandas.DataFrame.from_dict([
        {'to': end_datetime, 'intensity': intensity, **{mix_dict['fuel']: mix_dict['perc']
                                for mix_dict in generation_mix
                                }}
        for end_datetime, intensity, generation_mix in
        zip(data['to'], data['intensity.forecast'], data['generationmix'])])


if __name__ == '__main__':
    # print(get_usage_data(remove_incomplete_rows=False))
    # print(get_regional_intensity())
    get_old_data_avg()
    # while True:
    #     print(tabulate(get_mix(pandas.to_datetime('now') - pandas.to_timedelta(36, 'h'), 'NG2'), headers='keys'))
    #     time.sleep(30 * 60)
    # start = pandas.to_datetime('today').to_period('d').start_time - pandas.to_timedelta(5, 'd')
    # print(get_fuel_data(start, 'gas', remove_incomplete_rows=False))
    # print(get_temp_data())