import contextlib
import sys
import os
import inspect
from time import sleep
from traceback import format_exc
from datetime import datetime, timedelta
from platform import node

import psutil
import google_sheets
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!

with contextlib.suppress(ImportError):
    from rich import print  # rich-text printing
    from rich.traceback import install  # rich tracebacks

    install()
from change_wallpaper import change_wallpaper
from update_phone_music import update_phone_music
from copy_60_minutes import copy_60_minutes
from update_jabs_data import update_jabs_data
from get_youtube_playlists import get_youtube_playlists
from get_energy_usage import get_usage_data
from bitrot import check_folders_for_bitrot
from erase_trailers import erase_trailers

sys.path.append(os.path.join(os.environ['UserProfile'], 'STFC', 'Documents', 'Scripts'))
from oracle_staff_check import annual_leave_check, otl_submit
from get_budget_data import get_budget_data
from check_leave_dates import check_leave_dates
from fill_availability import fill_availability
from check_on_site_support import check_on_site_support
from events_to_spreadsheet import events_to_spreadsheet, set_pc_unlocked_flag
from get_access_data import check_prev_week
from todos_from_notes import todos_from_notes
from get_payslips import get_payslips
from catering_bookings import get_bookings
from package_updates import find_new_python_packages

# restart code
# imported_files = set(inspect.getfile(f) for _, f in locals().items() if inspect.isfunction(f))
# print(imported_files)
# start_dir = os.getcwd()
# mod_time = os.path.getmtime(__file__)
# for i in range(10):
#     print(i)
#     sleep(10)
#     if mod_time != os.path.getmtime(__file__):
#         print('Restarting')
#         os.chdir(start_dir)
#         subprocess.Popen([sys.executable] + sys.argv)
#         exit()

# Spreadsheet ID: https://docs.google.com/spreadsheets/d/XXX/edit#gid=0
sheet_id = '1T9vTsd6mW0sw6MmVsMshbRBRSoDh7wo9xTxs9tqYr7c'  # Automation spreadsheet
sheet_name = 'Sheet1'


def update_cell(row, col, string):
    google_sheets.update_cell(sheet_id, sheet_name, f'{col}{row}', string)


def run_tasks():
    column_names = ['Icon', 'Function name', 'Parameters', 'Period', 'Enabled',
                    'Last run', 'Machine', 'Last result', 'Next run']

    def get_column(name):
        return google_sheets.get_column(column_names.index(name) + 1)

    last_col = google_sheets.get_column(len(column_names))
    time_format = "%d/%m/%Y %H:%M"
    period_col = column_names.index('Period')
    pushbullet = Pushbullet(api_key)
    while True:
        print('Fetching data from spreadsheet')
        try:
            data = google_sheets.get_data(sheet_id, sheet_name, f'A:{last_col}')
        except Exception as e:
            print(e)
            sleep(60)
            continue
        assert data[0] == column_names
        min_period = min(float(row[period_col]) for row in data[1:])
        next_task_time = datetime.now() + timedelta(days=min_period)
        battery = psutil.sensors_battery()
        if battery is None or battery.power_plugged:
            failures = set()
            toast = ''
            for i, values in enumerate(data[1:]):
                properties = dict(zip(column_names, values))
                if properties.get('Enabled', False) != 'TRUE':
                    continue
                last_result = properties.get('Last result')
                now = datetime.now()
                next_run_time = datetime.strptime(properties.get('Next run'), time_format)
                if next_run_time > now and last_result == 'Success':
                    next_task_time = min(next_task_time, next_run_time)
                    continue

                now_str = now.strftime(time_format)
                update_cell(i + 2, get_column('Last run'), now_str)
                update_cell(i + 2, get_column('Machine'), node())
                update_cell(i + 2, get_column('Last result'), 'Running')
                function_name = properties.get('Function name')
                parameters_raw = properties.get('Parameters', '')
                icon = properties.get('Icon', '')
                try:
                    parameters = float(parameters_raw)
                except ValueError:  # it's not a float, assume string
                    parameters = f'"{parameters_raw}"' if parameters_raw else ''  # wrap in quotes to send to function
                os.system(f'title ➡️ {icon} {function_name}')  # set title of window
                print('')
                print(now_str, function_name, parameters)
                # return_value can be:
                # False: postpone until next scheduled run
                # datetime: postpone until then
                # empty string, None, or True: success but no toast
                # string: toast summarising actions
                try:
                    return_value = eval(f'{function_name}({parameters})')
                    if isinstance(return_value, datetime):
                        next_run_time = return_value
                    else:
                        period = float(properties.get('Period', 1))  # default: once per day
                        next_run_time = now + timedelta(days=period)
                    next_run_str = next_run_time.strftime(time_format)
                    print('Next run time:', next_run_str)
                    update_cell(i + 2, get_column('Next run'), next_run_str)
                    # sometimes we don't want to run the function now, but don't need to notify failure
                    if return_value is False:
                        result = 'Postponed'
                    else:
                        result = 'Success'
                        if isinstance(return_value, str) and return_value:
                            # function returns a non-empty string: toast with summary of what it's done
                            pushbullet.push_note(f'{icon} {function_name}', return_value)
                except Exception:
                    error_lines = format_exc().split('\n')
                    result = '\n'.join(error_lines[4:])
                    failures.add(function_name)
                    toast = ', '.join(failures) if len(failures) > 1 else f'{function_name}: {result}'

                print(result)
                update_cell(i + 2, get_column('Last result'), result)

            if toast:
                pushbullet.push_note(f'👁️ Failed tasks {node()}', toast)
        else:
            print('On battery, not running any tasks')

        try:
            set_pc_unlocked_flag()
        except Exception as e:
            print(e)
            sleep(60)
            continue

        # Sleep up to 5 minutes more than needed to avoid race conditions (two computers trying to do task at same time)
        next_task_time += timedelta(seconds=hash(node()) % 300)
        next_time_str = next_task_time.strftime("%H:%M")
        print(f'Waiting until {next_time_str}')
        os.system(f'title ⌛️ {next_time_str}')  # set title of window
        while datetime.now() < next_task_time:
            sleep(60)


if __name__ == '__main__':
    run_tasks()
