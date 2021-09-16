import sys
import os
from traceback import format_exc
from datetime import datetime
import google_sheets
from update_phone_music import update_phone_music
sys.path.append(os.path.join(os.environ['UserProfile'], 'Documents', 'Scripts'))
from oracle_otl_check import oracle_otl_check


def dummy_task(param=None):
    open('this will fail', 'r')
    # raise RuntimeError(f'Dummy task failed, arg {param}')


def run_tasks():
    # Spreadsheet ID: https://docs.google.com/spreadsheets/d/XXX/edit#gid=0
    sheet_id = '1T9vTsd6mW0sw6MmVsMshbRBRSoDh7wo9xTxs9tqYr7c'  # Automation spreadsheet

    response = google_sheets.sheets.get(spreadsheetId=sheet_id, range='Sheet1!A:E').execute()
    data = response['values']
    assert data[0] == ['Function name', 'Parameters', 'Frequency', 'Last run', 'Last result']

    time_format = "%d/%m/%Y %H:%M"
    for i, values in enumerate(data[1:]):
        function_name = values[0]
        frequency = float(values[2])
        last_run = datetime.strptime(values[3], time_format) if len(values) > 3 else None
        now = datetime.now()
        if now - last_run

        if not last_run:
            print(function_name)
            try:
                exec(f'{function_name}()')
                result = 'Success'
            except Exception:
                result = '\n'.join(format_exc().split('\n')[4:])
            print(result)
            google_sheets.update_cell(sheet_id, 'Sheet1', f'D{i + 2}', now.strftime(time_format))
            google_sheets.update_cell(sheet_id, 'Sheet1', f'E{i + 2}', result)


if __name__ == '__main__':
    run_tasks()
