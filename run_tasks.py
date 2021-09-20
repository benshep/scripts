import sys
import os
from traceback import format_exc
from datetime import datetime
import google_sheets

from change_wallpaper import change_wallpaper
from update_phone_music import update_phone_music
from copy_60_minutes import copy_60_minutes
from update_jabs_data import update_jabs_data
sys.path.append(os.path.join(os.environ['UserProfile'], 'Documents', 'Scripts'))
from oracle_otl_check import oracle_otl_check
from get_budget_data import get_budget_data
from enter_otl_timecard import enter_otl_timecard
from check_leave_dates import check_leave_dates
from fill_availability import fill_availability


# Spreadsheet ID: https://docs.google.com/spreadsheets/d/XXX/edit#gid=0
sheet_id = '1T9vTsd6mW0sw6MmVsMshbRBRSoDh7wo9xTxs9tqYr7c'  # Automation spreadsheet
sheet_name = 'Sheet1'


def update_cell(row, col, string):
    google_sheets.update_cell(sheet_id, sheet_name, f'{col}{row}', string)


def run_tasks():
    response = google_sheets.sheets.get(spreadsheetId=sheet_id, range=f'{sheet_name}!A:E').execute()
    data = response['values']
    assert data[0] == ['Function name', 'Parameters', 'Period', 'Last run', 'Last result']

    time_format = "%d/%m/%Y %H:%M"
    seconds_per_day = 24 * 60 * 60
    for i, values in enumerate(data[1:]):
        n_values = len(values)
        last_run_str = values[3] if n_values > 3 else None
        last_result = values[4] if n_values > 4 else None
        check_when_run = last_run_str and last_result == 'Success'
        now = datetime.now()
        if check_when_run:
            last_run = datetime.strptime(last_run_str, time_format)
            time_since_run = now - last_run
            seconds_since_run = time_since_run.total_seconds()
            days_since_run = seconds_since_run / seconds_per_day
            period = float(values[2])
            time_to_run = days_since_run > period
        else:  # never been run, or failed last time
            time_to_run = True
        if not time_to_run:
            continue

        now_str = now.strftime(time_format)
        update_cell(i + 2, 'D', now_str)
        function_name = values[0]
        parameters = values[1]
        print(function_name, parameters)
        try:
            exec(f'{function_name}({parameters})')
            result = 'Success'
        except Exception:
            error_lines = format_exc().split('\n')
            result = '\n'.join(error_lines[4:])
        print(result)
        update_cell(i + 2, 'E', result)


if __name__ == '__main__':
    run_tasks()
