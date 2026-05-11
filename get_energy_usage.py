import asyncio
import json
import math
import os
import time
import urllib.parse
from contextlib import suppress
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum

import aiohttp
import numpy
import pandas
import requests
from requests.structures import CaseInsensitiveDict
import wcwidth
from progress.bar import Bar

with suppress(ImportError):
    from rich import print

import energy_credentials
import google_api
from openweather import api_key


def today() -> pandas.Timestamp:
    """Return a datetime object representing the start of today."""
    return pandas.to_datetime('today').to_period('D').start_time  # - pandas.to_timedelta(3, 'd')


base_url = 'https://consumer-api.data.n3rgy.com'
carbon_int_url = 'https://api.carbonintensity.org.uk'
octopus_url = 'https://api.octopus.energy/v1'
glowmarkt_url = 'https://api.glowmarkt.com/api/v0-1/'
home_postcode = 'WA10'
rich_output = print.__module__ == 'rich'
bars = "▁▂▃▄▅▆▇"  # one fewer bar (left out █) to avoid clashes between rows
colours = {'Gas': 'orange_red1', 'Solar': 'bright_yellow', 'Hydro': 'blue', 'Wind': 'bright_cyan', 'Misc': 'cyan',
           'Imports': 'grey50', 'Biomass': '#895129', 'Nuclear': 'yellow', 'PSH': "dodger_blue1"}
icons = CaseInsensitiveDict({'Gas': '🔥', 'Solar': '☀️', 'Hydro': '💧', 'Wind': '💨', 'Misc': '➿',
                             'Imports': '🌍', 'Biomass': '🪵', 'Nuclear': '☢️', 'PSH': '🏞️'})
records = CaseInsensitiveDict({'Wind': 23.880, 'Solar': 14.035, 'Gas': 27.868, 'Nuclear': 9.342, 'Coal': 26.044,
                               'lastUpdated': today() - timedelta(days=1)})


def dmy(date: datetime, time: bool = True):
    """Convert datetime into dd/mm/yyyy format, and optionally HH:MM."""
    return date.strftime('%d/%m/%Y' + (' %H:%M' if time else ''))


def ymd(date: datetime, time: bool = False):
    """Convert datetime into yyyy-mm-dd format (ISO 8601), and optionally THH:MM:SS."""
    return date.strftime('%Y-%m-%d' + ('T%H:%M:00' if time else ''))


def ymdhm(date: datetime):
    """Convert datetime into yyyymmddHHMM format."""
    return date.strftime('%Y%m%d%H%M')


def get_usage_data(remove_incomplete_rows: bool = True) -> None | str | datetime:
    return asyncio.run(get_usage_data_async(remove_incomplete_rows=remove_incomplete_rows))


async def get_usage_data_async(remove_incomplete_rows: bool = True) -> None | str | datetime:
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
    start_date = pandas.to_datetime(column_a[-1], dayfirst=True) + pandas.to_timedelta(1, 'day')
    if start_date >= today():  # no need to collect more data
        return None

    sheet = google_api.spreadsheets.get(spreadsheetId=sheet_id).execute()
    grid_id = next(grid['properties']['sheetId']
                   for grid in sheet['sheets']
                   if grid['properties']['title'] == sheet_name)

    def fill_request(start_column: int, column_count: int, row_count: int):
        """Define a 'fill down' action starting at the given column index (zero-based)."""
        # print(f'Fill columns {start_column=}, {fill_top_row=}, {row_count=}')
        return {'autoFill': {'useAlternateSeries': False, 'sourceAndDestination': {
            'source': {'sheetId': grid_id, 'startRowIndex': fill_top_row,
                       'endRowIndex': fill_top_row + 1,  # half-open
                       'startColumnIndex': start_column,
                       'endColumnIndex': start_column + column_count,
                       }, 'dimension': 'ROWS', 'fillLength': row_count}}}

    fill_requests = []
    data_titles = {'gas': '#feac0a', 'electricity': '#00f0ff', 'carbon intensity': '#20AF24'}
    max_title_len = max(len(title) for title in data_titles)
    all_fuel_data = await asyncio.gather(*[get_fuel_data(start_date, data_title) for data_title in data_titles])
    # use fillna when data seems to be permanently missing - we can get incomplete days and fill in the gaps manually
    all_fuel_data = [fuel_data.dropna() if remove_incomplete_rows else fuel_data.fillna(-1)
                     for fuel_data in all_fuel_data]

    # truncate all of them to size of the smallest, keeping only a whole number of days (i.exception. 48 half-hourly periods)
    min_size = min(len(fuel_data) for fuel_data in all_fuel_data)
    tomorrow = datetime.now() + timedelta(days=1)
    if min_size == 0:
        empty_sets = ', '.join(title for title, data in zip(data_titles, all_fuel_data) if len(data) == 0)
        print(f'No new {empty_sets} data received')
        return tomorrow

    all_fuel_data = [fuel_data.head(min_size) for fuel_data in all_fuel_data]

    # check all dates are the same
    if len({tuple(fuel_data.axes[0].to_list()) for fuel_data in all_fuel_data}) > 1:
        print('Not all dates are identical in energy datasets')
        return tomorrow  # postpone data entry

    # pretty-print nice bar graphs to the console
    for (title, colour), fuel_data in zip(data_titles.items(), all_fuel_data):
        if len(fuel_data) > 0:
            print(title.ljust(max_title_len), end='\n' if len(fuel_data) > 1 else ' ')
            vmax = fuel_data.values.max()
            vmin = fuel_data.values.min()
            idx = round((len(bars) - 1) * (fuel_data - vmin) / (vmax - vmin))
            blocks = pandas.DataFrame.map(idx, lambda x: bars[int(x)])
            for date, block_row, data_row in zip(fuel_data.index, blocks.values, fuel_data.values):
                day_usage = f'{min(data_row):.0f}-{max(data_row):.0f} gCO₂e/kWh' if title == 'carbon intensity' else f'{sum(data_row):.1f} kWh'
                sparkline = ''.join(block_row)
                if rich_output:
                    sparkline = f'[{colour}]{sparkline}[/{colour}]'
                print(date.strftime('%a %d %b'), sparkline, day_usage)

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
    fill_requests.append(fill_request(254, 4, fill_row_count))  # Octopus Tracker rates (IU:IX)
    # Fill formulae from last populated row
    for request in Bar('Filling formulae in spreadsheet', max=len(fill_requests)).iter(fill_requests):
        request_body = {'requests': [[request]]}
        google_api.spreadsheets.batchUpdate(spreadsheetId=sheet_id, body=request_body).execute(num_retries=5)
    # Get the summary cell to go in a toast (but sometimes it's blank if nothing interesting to report!)
    summary_range = google_api.sheets.get(spreadsheetId=sheet_id, range='usageSummary').execute()
    summary = summary_range.get('values', [['']])[0][0]
    # Add the minimum and maximum forecasted intensity for the next 2 days
    if not summary or (forecast := get_regional_intensity()) is None:  # will be None if this API call fails
        return summary
    for minmax, icon in zip(('min', 'max'), ('🟢', '🔴')):
        block_row = forecast.iloc[getattr(forecast['intensity.forecast'], f'idx{minmax}')()]
        gen_mix = pandas.DataFrame.from_dict(block_row['generationmix'])
        highest = gen_mix.iloc[gen_mix['perc'].idxmax()]
        fuel = highest['fuel']
        summary += f"\n{icon} {block_row['intensity.forecast']} gCO₂e, " \
                   f"{block_row['to'].strftime('%a %H:%M')}, {icons.get(fuel, fuel)} {highest['perc']:.0f}%"
    return summary


def fill_old_carbon_data() -> bool | None:
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
        return None


def get_fuel_data_n3rgy(start_date: pandas.Timestamp, fuel: str,
                        remove_incomplete_rows: bool = True) -> pandas.DataFrame:
    """Use the n3rgy API to get kWh data for gas or electricity."""
    print(f'Fetching {fuel} data beginning {dmy(start_date)}')
    if 'carbon intensity' in fuel:
        return get_co2_data(start_date, remove_incomplete_rows=remove_incomplete_rows)
    # last_date = start + pandas.to_timedelta(30, 'd')
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


async def get_fuel_data(start_date: pandas.Timestamp, fuel: str,
                        remove_incomplete_rows: bool = True) -> pandas.DataFrame:
    """Use the Glowmarkt API to get kWh data for gas or electricity."""
    print(f'Fetching {fuel} data beginning {dmy(start_date)}')
    if 'carbon intensity' in fuel:
        return get_co2_data(start_date, remove_incomplete_rows=remove_incomplete_rows)

    # spreadsheet expects *end* times going from 00:00 to 23:30 - shift requested time back by half an hour
    half_hour = pandas.to_timedelta(30, 'min')
    start_date -= half_hour
    end_date = today() - half_hour
    # if use_n3rgy:
    #     params = {'start': ymdhm(start_date), 'end': ymdhm(today())}
    #     url = f'{base_url}/{source}/consumption/1/?{urllib.parse.urlencode(params)}'
    #     auth = aiohttp.BasicAuth(energy_credentials.mac_address, '')
    #     record_path = 'values'
    # else:  # Octopus
    #     params = {'page_size': (end_date - start_date).days * 48, 'period_from': ymd(start_date, True) + 'Z',
    #               'period_to': ymd(end_date, True) + 'Z', 'order_by': 'period'}
    #     url = '/'.join([octopus_url, source + '-meter-points', energy_credentials.mpan[source], 'meters',
    #                     energy_credentials.meter_serial_number[source], 'consumption', '?']) + urllib.parse.urlencode(
    #         params)
    #     auth = aiohttp.BasicAuth(energy_credentials.octopus_api_key, '')
    #     record_path = 'results'
    # print(url)
    # async with aiohttp.ClientSession() as session:
    #     async with session.get(url, auth=auth) as response:
    #         response_json = await response.json()
    response_json = await get_readings(start_date, fuel)
    # print(response_json)
    data = response_json  # array of [timestamp, reading]
    if not data:  # response_json['count'] == 0:  # no results
        return pandas.DataFrame()
    df = pandas.DataFrame(data, columns=['Timestamp', 'Reading'])
    df.index = pandas.to_datetime(df['Timestamp'], unit='s') + half_hour  # turn into *end* times
    pivot = pandas.pivot_table(df, index=df.index.date, columns=df.index.time, values='Reading')
    pivot = pivot.dropna() if remove_incomplete_rows else pivot.fillna(-1)
    return pivot if pivot.shape[1] == 48 else pandas.DataFrame()  # must be n x 48 DataFrame


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


def get_co2_data(start: pandas.Timestamp, geography: str | int | RegionId = home_postcode,
                 remove_incomplete_rows: bool = True, do_pivot: bool = True,
                 end: pandas.Timestamp | None = None) -> pandas.DataFrame:
    """Use the Carbon Intensity API to fetch regional or national CO₂ intensity data.
    :param start: date/time for the start of the period.
    :param end: date/time for the end of the period. A maximum of 14 days will be returned (API limit).
    If end is None, return as much data as possible.
    :param do_pivot: Return a DataFrame where the rows are days and the columns hours. Ignores remove_incomplete_rows.
    :param geography: Can be a postcode or one of the region IDs. Leave geography blank to get national data.
    :param remove_incomplete_rows: Specify False to fill in -1 values where there are data gaps."""
    if end is None:
        end = today()  # - pandas.to_timedelta(1, 'day')
    end = min(end, start + pandas.to_timedelta(13, 'day'))  # can't get more than 14 days at a time
    if end <= start:
        return pandas.DataFrame()
    if geography:
        area = 'regional/'
        suffix = f'/postcode/{geography}' if isinstance(geography, str) else f'/regionid/{geography}'
    else:
        area, suffix = '', ''
    url = f'{carbon_int_url}/{area}intensity/{ymd(start, time=True)}Z/{ymd(end, time=True)}Z{suffix}'
    # print(url)
    json = get_json(url)
    # print(json)
    # path is data.data for regional
    df = pandas.json_normalize(json, record_path=['data', 'data'] if geography else ['data'])
    df['to'] = pandas.to_datetime(df['to'])
    # use 'actual' value where available with national. For regional, we only see 'forecast' values
    df['intensity'] = df['intensity.forecast'] if geography else df['intensity.actual'].fillna(df['intensity.forecast'])
    if do_pivot:
        pivot = pandas.pivot_table(df, index=df['to'].dt.date, columns=df['to'].dt.time, values='intensity')
        # Add an extra day (sometimes necessary when data is missing)
        # pivot.loc[pivot.index[0] + pandas.to_timedelta(1, 'd')] = [pandas.NA] * 48
        # pivot = pivot.sort_index()

        # use fillna when data seems to be permanently missing - we can get incomplete days and fill in the gaps manually
        return pivot.dropna() if remove_incomplete_rows else pivot.fillna(-1)
    else:
        df.set_index('to', inplace=True)  # index is the *end* time of each period
        # Add the generation mix as well, why not?
        # print(df['generationmix'])
        gen_mix = pandas.DataFrame([
            {item['fuel']: item['perc'] for item in row}
            for row in df['generationmix']], index=df.index)
        # print(gen_mix)
        return pandas.concat([df['intensity'], gen_mix], axis=1)


def get_json(url: str, retries: int = 3):
    """Attempt to fetch JSON data from a URL, retrying a number of times (default 3)."""
    attempt = 0
    while attempt < retries:
        json = requests.get(url).json()
        if 'error' not in json:
            break
        attempt += 1
        print(f'Failed to get data from {url=} on {attempt=}')
    else:
        raise ValueError(f'Bad response from server after {retries=}: {json["error"]}')
    return json


def get_regional_intensity(start_time: pandas.Timestamp | str = 'now',
                           postcode: str = home_postcode) -> pandas.DataFrame:
    """Use the Carbon Intensity API to fetch the regional CO₂ intensity forecast."""
    start_time = ymd(pandas.to_datetime(start_time), time=True)
    json = get_json(f'{carbon_int_url}/regional/intensity/{start_time}Z/fw48h/postcode/{postcode}')
    try:
        df = pandas.json_normalize(json, record_path=['data', 'data'])  # path is data.data for regional
    except KeyError:  # problem with JSON, maybe forecasts not working?
        return None
    df['to'] = pandas.to_datetime(df['to'])
    return df


def get_old_data_avg() -> None:
    """Get the two-week average of carbon data."""
    start_date = today() - pandas.to_timedelta(7, 'D')  # to align to previous dataset
    start_date = pandas.to_datetime('2024-09-20')
    geographies = ['OX11', 'EH9', 'IV1', '']  # blank = national
    while start_date < today():
        avg = [get_co2_data(start_date, geography=geography).mean().mean()  # average of whole DataFrame
               for geography in geographies]
        print(start_date, '', '', *avg, sep='\t')
        start_date += pandas.to_timedelta(14, 'D')


def get_regions_data_avg() -> None:
    """Get the two-week average of carbon data for all regions."""
    start_date = pandas.to_datetime('2025-01-01')
    while start_date < today():
        mean_data = [get_co2_data(start_date, geography=region).mean().mean()
                     for region in range(min(RegionId), max(RegionId) + 1)]

        print(start_date, *mean_data, sep='\t')
        start_date += pandas.to_timedelta(14, 'd')


def get_mix(start_time: str = 'now', postcode: str = home_postcode) -> pandas.DataFrame:
    """Return the regional energy mix for a 48h period."""
    data = get_regional_intensity(start_time, postcode)
    return pandas.DataFrame.from_dict([
        {'to': end_datetime, 'intensity': intensity, **{mix_dict['source']: mix_dict['perc']
                                                        for mix_dict in generation_mix
                                                        }}
        for end_datetime, intensity, generation_mix in
        zip(data['to'], data['intensity.forecast'], data['generationmix'])])


def refresh_glowmarkt_token() -> str:
    """Authenticate with the Glowmarkt API and return a valid token."""
    url = glowmarkt_url + 'auth'
    headers = {'Content-Type': 'application/json',
               'applicationId': energy_credentials.glowmarkt['applicationId']}
    credentials = energy_credentials.glowmarkt['auth']  # username and password
    response = requests.post(url, json=credentials, headers=headers)
    return response.json()['token']


async def glowmarkt_call(path: str) -> dict:
    """Request information from the Glowmarkt API."""
    url = glowmarkt_url + path
    # print(url)
    headers = {'Content-Type': 'application/json',
               'applicationId': energy_credentials.glowmarkt['applicationId'],
               'token': energy_credentials.glowmarkt['token']}
    # response = requests.get(url, headers=headers)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            response_json = await response.json()
    # print(response_json)
    return response_json


async def get_virtual_entities() -> dict:
    """Request virtual entities from the Glowmarkt API."""
    return await glowmarkt_call('virtualentity')


async def get_resources(entity_id: str) -> dict:
    """Request information about a virtual entity's resources from the Glowmarkt API."""
    return await glowmarkt_call(f'virtualentity/{entity_id}/resources')


def dont_quote_colons(string: str, safe: str = '/', encoding=None, errors=None):
    """Quote a string in a URL, but the colon character is marked as 'safe' and won't be quoted."""
    return urllib.parse.quote(string, safe + ':', encoding, errors)


class ReadingPeriod(StrEnum):
    """The aggregation level in which the data is to be returned (ISO 8601)."""
    minute = 'PT1M'  # only electricity
    half_hour = 'PT30M'
    hour = 'PT1H'
    day = 'P1D'
    week = 'P1W'  # starting Monday
    month = 'P1M'
    year = 'P1Y'


async def get_readings(start_date: pandas.Timestamp, fuel: str,
                       period: ReadingPeriod = ReadingPeriod.half_hour) -> list[list]:
    """Request information about a virtual entity's resources from the Glowmarkt API."""
    end_date = min(today(), start_date + timedelta(days=7))
    params = {'from': ymd(start_date, time=True),
              'to': ymd(end_date, time=True),
              'period': period,
              'offset': 0,  # to UTC, exception.g. BST = -60, EST = +300
              'function': 'sum'  # sum = total reading per period
              }
    resource_id = energy_credentials.glowmarkt[f'{fuel} consumption']
    query = urllib.parse.urlencode(params, quote_via=dont_quote_colons)
    readings_response, last_time_response = await asyncio.gather(
        # https://api.glowmarkt.com/api-docs/v0-1/resourcesys/#/
        glowmarkt_call(f'resource/{resource_id}/readings?{query}'),
        glowmarkt_call(f'resource/{resource_id}/last-time')
    )
    data = readings_response['data']  # array of [timestamp, reading]
    # Timestamps where no data is received yet are still listed!
    # Filter those out using the response from the last-time query
    last_timestamp = last_time_response['data']['lastTs']
    print('Last reading time for', fuel, datetime.fromtimestamp(last_timestamp))
    return [[timestamp, kwh] for timestamp, kwh in data if timestamp <= last_timestamp]


async def loop_refresh_readings():
    """Refresh readings every minute to check when they get updated."""
    # 23/4: got readings after 13:37, last-time changed ~2h before that
    while True:
        readings = await get_readings(today() - pandas.Timedelta(days=1), 'electricity')
        print(datetime.now(),
              'from', datetime.fromtimestamp(readings[0][0]),
              'to', datetime.fromtimestamp(readings[-1][0]),
              'total', sum([kwh for _, kwh in readings]))
        # j = await glowmarkt_call(f'resource/{resource_id}/catchup')
        # assert j['status'] == 'OK'
        time.sleep(60)


def get_live_generation(source: str | None = None) -> str:
    """Fetch the live generation data for a given fuel.
    :param source: the fuel type to fetch - Gas Solar Coal Hydro Wind Misc Imports PSH Biomass Nuclear. Supply None to return largest."""
    global records
    url = 'https://www.energydashboard.co.uk/api/latest/generation'
    response = requests.get(url)
    data = response.json()
    generation_values = data['fiveMinuteData']['generationValues']
    highest_gw = 0
    biggest_source = ''
    terminal_width, _ = os.get_terminal_size()
    sparkline = ''
    if records['lastUpdated'] < today():
        try:
            records = get_generation_records()
        except Exception as exception:
            print('Failed to update records', exception)
    total_raw = 0
    total_clipped = 0
    for source_name, info in generation_values.items():
        raw_width = info['percentage'] * terminal_width / 100
        # add or take away a bit (cascade rounding, ish) to make overall width add up to exactly terminal_width
        width = int(raw_width + total_raw - total_clipped)
        total_raw += raw_width
        change_colour = rich_output and source_name in colours
        bar = icons.get(source_name, source_name)
        if total := info['total']:
            bar += f' {total} GW'
            if total > highest_gw:
                highest_gw = total
                biggest_source = source_name
            if source_name in records:
                bar += f' 🏆 {records[source_name]} GW'
        bar = wcwidth.clip(wcwidth.ljust(bar, width, ' ' if rich_output else '*'), 0, width)
        clipped_width = wcwidth.width(bar)
        total_clipped += clipped_width
        if change_colour:
            colour = colours[source_name]
            bar = f'[black on {colour}]{bar}[/black on {colour}]'
        sparkline += bar
    # print(total_raw, total_clipped)
    print(sparkline)
    source = source or biggest_source
    total = generation_values[source]['total']
    broken = source in records and total > records[source]
    label = '🏆 ' if broken else ''
    return f'{icons.get(source, source)} {label}{total:.2f} GW'


def get_generation_records() -> CaseInsensitiveDict:
    """Fetch the energy generation records from energydashboard.co.uk."""
    url = 'https://www.energydashboard.co.uk/records'
    response = requests.get(url)
    text = response.text
    script_node = '<script id="__NEXT_DATA__" type="application/json">'
    script_index = text.find(script_node)
    script_json = text[script_index + len(script_node):]
    end_index = script_json.find('</script>')
    script_json = script_json[:end_index]
    data = json.loads(script_json)
    page_props = data['props']['pageProps']
    new_records = CaseInsensitiveDict({record['source']: record['record']['source_mw'] / 1000
                                       for record in page_props['generationSummaries']})
    new_records['lastUpdated'] = today()
    return new_records


if __name__ == '__main__':
    # print(get_usage_data(remove_incomplete_rows=True))
    # print(get_regional_intensity())
    # get_old_data_avg()
    # while True:
    #     print(tabulate(get_mix(pandas.to_datetime('now') - pandas.to_timedelta(36, 'h'), 'NG2'), headers='keys'))
    #     time.sleep(30 * 60)
    start = pandas.to_datetime('today').to_period('D').start_time - pandas.to_timedelta(2, 'D')
    # print(asyncio.run(get_fuel_data(start, 'electricity', remove_incomplete_rows=False)))
    # print(get_fuel_data_n3rgy(start, 'gas', remove_incomplete_rows=False))
    # print(get_temp_data())
    # print(asyncio.run(get_virtual_entities()))
    # print(asyncio.run(get_resources(energy_credentials.glowmarkt["entity"])))
    # j = asyncio.run(get_readings(start, 'electricity', ReadingPeriod.half_hour))
    # print(get_live_generation())
    # print(get_generation_records())
    # asyncio.run(loop_refresh_readings())
    print(get_co2_data(start, 'WA4', do_pivot=False))