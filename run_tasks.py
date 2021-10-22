import sys
import os
from time import sleep
from traceback import format_exc
from datetime import datetime, timedelta
from platform import node

import psutil

import google_sheets
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!

from change_wallpaper import change_wallpaper
from update_phone_music import update_phone_music
from copy_60_minutes import copy_60_minutes
from update_jabs_data import update_jabs_data
from get_youtube_playlists import get_youtube_playlists
sys.path.append(os.path.join(os.environ['UserProfile'], 'Documents', 'Scripts'))
from oracle_staff_check import otl_check, annual_leave_check
from get_budget_data import get_budget_data
from enter_otl_timecard import enter_otl_timecard
from check_leave_dates import check_leave_dates
from fill_availability import fill_availability
from check_on_site_support import check_on_site_support


# Spreadsheet ID: https://docs.google.com/spreadsheets/d/XXX/edit#gid=0
sheet_id = '1T9vTsd6mW0sw6MmVsMshbRBRSoDh7wo9xTxs9tqYr7c'  # Automation spreadsheet
sheet_name = 'Sheet1'


def update_cell(row, col, string):
    google_sheets.update_cell(sheet_id, sheet_name, f'{col}{row}', string)


def run_tasks():
    column_names = ['Function name', 'Parameters', 'Period', 'Last run', 'Machine', 'Last result']

    def get_column(name):
        return google_sheets.get_column(column_names.index(name) + 1)

    last_col = google_sheets.get_column(len(column_names))
    time_format = "%d/%m/%Y %H:%M"
    failures = []
    period_col = column_names.index('Period')
    while True:
        print('Fetching data from spreadsheet')
        response = google_sheets.sheets.get(spreadsheetId=sheet_id, range=f'{sheet_name}!A:{last_col}').execute()
        data = response['values']
        assert data[0] == column_names
        min_period = min(float(row[period_col]) for row in data[1:])
        toast = ''
        next_task_time = datetime.now() + timedelta(days=min_period)
        battery = psutil.sensors_battery()
        if battery is None or battery.power_plugged:
            for i, values in enumerate(data[1:]):
                n_values = len(values)
                col_index = column_names.index('Last run')
                last_run_str = values[col_index] if n_values > col_index else None
                col_index = column_names.index('Last result')
                last_result = values[col_index] if n_values > col_index else None
                check_when_run = last_run_str and last_result == 'Success'
                now = datetime.now()
                if check_when_run:
                    last_run = datetime.strptime(last_run_str, time_format)
                    period = float(values[period_col])
                    next_run_time = last_run + timedelta(days=period)
                    time_to_run = next_run_time <= now
                else:  # never been run, or failed last time
                    time_to_run = True
                if not time_to_run:
                    next_task_time = min(next_task_time, next_run_time)
                    continue

                now_str = now.strftime(time_format)
                update_cell(i + 2, get_column('Last run'), now_str)
                update_cell(i + 2, get_column('Machine'), node())
                update_cell(i + 2, get_column('Last result'), 'Running')
                function_name = values[0]
                parameters = values[1]
                os.system(f'title ➡️ {function_name}')  # set title of window
                print(function_name, parameters)
                try:
                    exec(f'{function_name}({parameters})')
                    result = 'Success'
                except Exception:
                    error_lines = format_exc().split('\n')
                    result = '\n'.join(error_lines[4:])
                    failures.append(function_name)
                    toast = ', '.join(failures) if len(failures) > 1 else f'{function_name}: {result}'

                print(result)
                update_cell(i + 2, get_column('Last result'), result)

            if toast:
                Pushbullet(api_key).push_note(f'👁️ Failed tasks {node()}', toast)
        else:
            print('On battery, not running any tasks')

        sleep_duration = max(0.0, (next_task_time - datetime.now()).total_seconds())
        os.system(f'title ⌛️ {next_task_time.strftime("%H:%M")}')  # set title of window
        sleep(sleep_duration)


if __name__ == '__main__':
    run_tasks()
