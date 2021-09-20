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


def run_tasks():
    # Spreadsheet ID: https://docs.google.com/spreadsheets/d/XXX/edit#gid=0
    sheet_id = '1T9vTsd6mW0sw6MmVsMshbRBRSoDh7wo9xTxs9tqYr7c'  # Automation spreadsheet

    response = google_sheets.sheets.get(spreadsheetId=sheet_id, range='Sheet1!A:E').execute()
    data = response['values']
    assert data[0] == ['Function name', 'Parameters', 'Period', 'Last run', 'Last result']

    time_format = "%d/%m/%Y %H:%M"
    for i, values in enumerate(data[1:]):
        function_name = values[0]
        parameters = values[1]
        now = datetime.now()
        last_run_str = values[3] if len(values) > 3 else None
        last_result = values[4] if len(values) > 4 else None
        if last_run_str and last_result == 'Success':
            last_run = datetime.strptime(last_run_str, time_format)
            time_since_run = now - last_run
            days_since_run = time_since_run.total_seconds() / (24 * 60 * 60)
            period = float(values[2])
            time_to_run = days_since_run > period
        else:  # never been run
            time_to_run = True
        if not time_to_run:
            continue

        google_sheets.update_cell(sheet_id, 'Sheet1', f'D{i + 2}', now.strftime(time_format))
        print(function_name, parameters)
        try:
            exec(f'{function_name}({parameters})')
            result = 'Success'
        except Exception:
            result = '\n'.join(format_exc().split('\n')[4:])
        print(result)
        google_sheets.update_cell(sheet_id, 'Sheet1', f'E{i + 2}', result)


if __name__ == '__main__':
    run_tasks()
