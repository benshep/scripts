import sys, os
from traceback import format_exc
from datetime import datetime
from google_sheets import update_cells, sheets
from update_phone_music import update_phone_music
sys.path.append(os.path.join(os.environ['UserProfile'], 'Documents', 'Scripts'))
from oracle_otl_check import oracle_otl_check

def run_tasks():
    # Spreadsheet ID: https://docs.google.com/spreadsheets/d/XXX/edit#gid=0
    sheet_id = '1T9vTsd6mW0sw6MmVsMshbRBRSoDh7wo9xTxs9tqYr7c'  # Automation spreadsheet

    response = sheets.get(spreadsheetId=sheet_id, range='Sheet1!A:E').execute()
    data = response['values']
    assert data[0] == ['Function name', 'Parameters', 'Frequency', 'Last run', 'Last result']

    for i, values in enumerate(data[1:]):
        function_name = values[0]
        frequency = float(values[2])
        last_run = values[3] if len(values) > 3 else None
        if not last_run:
            print(function_name)
            try:
                exec(f'{function_name}()')
                result = ''
            except Exception:
                result = '\n'.join(format_exc().split('\n')[1:])
            print(result)
            cell = f'Sheet1!E{i + 2}'
            payload = {'values': [[result]], 'majorDimension': "ROWS", 'range': cell}
            sheets.update(spreadsheetId=sheet_id, range=cell, valueInputOption='USER_ENTERED', body=payload).execute()


if __name__ == '__main__':
    run_tasks()
