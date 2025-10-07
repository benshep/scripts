import contextlib
import subprocess
import sys
import os
import inspect
import cryptography.utils
import warnings
warnings.filterwarnings('ignore', category=cryptography.utils.CryptographyDeprecationWarning)
from time import sleep
from traceback import format_exc, extract_tb
from datetime import datetime, timedelta
from platform import node

import psutil
import google_api  # pip install google-api-python-client
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!
from folders import docs_folder

with contextlib.suppress(ImportError):
    from rich import print  # rich-text printing
    from rich.traceback import install  # rich tracebacks

    install()

# 'home' tasks
from change_wallpaper import change_wallpaper
from update_phone_music import update_phone_music
from copy_60_minutes import copy_60_minutes
from get_youtube_playlists import get_youtube_playlists
from get_energy_usage import get_usage_data
from bitrot import check_folders_for_bitrot
from erase_trailers import erase_trailers
from rugby_fixtures import update_saints_calendar
from concerts import update_gig_calendar, find_new_releases
from mersey_gateway import log_crossings

at_home = docs_folder is None  # no work documents
if not at_home:
    # 'work' tasks
    sys.path.append(os.path.join(docs_folder, 'Scripts'))
    from package_updates import find_new_python_packages
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
    from page_changes import check_page_changes, live_update

# Spreadsheet ID: https://docs.google.com/spreadsheets/d/XXX/edit#gid=0
sheet_id = '1T9vTsd6mW0sw6MmVsMshbRBRSoDh7wo9xTxs9tqYr7c'  # Automation spreadsheet
sheet_name = 'Sheet1'

start_dir = os.getcwd()
import_dict = {func: inspect.getfile(func) for func in locals().values() if inspect.isfunction(func)}
imports = {file: os.path.getmtime(file) for file in import_dict.values() if 'envs' not in file}  # my code, not library stuff
imports[__file__] = os.path.getmtime(__file__)  # this file too


def update_cell(row, col, string):
    google_api.update_cell(sheet_id, sheet_name, f'{col}{row}', string)


def run_tasks():
    column_names = ['Icon', 'Function name', 'Parameters', 'Period', 'Work', 'Home',
                    'Last run', 'Machine', 'Last result', 'Next run']

    def get_column(name):
        return google_api.get_column(column_names.index(name) + 1)

    last_col = google_api.get_column(len(column_names))
    time_format = "%d/%m/%Y %H:%M"
    period_col = column_names.index('Period')
    pushbullet = Pushbullet(api_key)

    title_toast = ''
    # first argument: comma-separated list of functions to run (because they were modified)
    force_run = [] if len(sys.argv) < 2 else sys.argv[1].split(',')
    while True:
        print('Fetching data from spreadsheet')
        try:
            headers, *data = google_api.get_data(sheet_id, sheet_name, f'A:{last_col}')
        except Exception as e:
            print(e)
            sleep(60)
            continue
        assert headers == column_names
        min_period = min(float(row[period_col]) for row in data)
        next_task_time = datetime.now() + timedelta(days=7)  # set a long time off, reduce as we go through task list
        battery = psutil.sensors_battery()
        if battery is not None and not battery.power_plugged:
            print('No tasks will run on battery power. Closing.')
            sleep(10)
            exit()

        location = 'Home' if at_home else 'Work'
        for i in range(len(data)):
            try:
                values = google_api.get_data(sheet_id, sheet_name, f'A{i + 2}:{last_col}{i + 2}')[0]
            except Exception as e:
                print(e)
                break
            properties = dict(zip(column_names, values))
            if properties.get(location, False) != 'TRUE':
                continue
            last_result = properties.get('Last result')
            now = datetime.now()
            next_run_time = datetime.strptime(properties.get('Next run'), time_format)
            function_name = properties.get('Function name')
            if next_run_time > now and last_result in ('Success', 'Postponed') and function_name not in force_run:
                next_task_time = min(next_task_time, next_run_time)
                continue
            last_run_time = datetime.strptime(properties.get('Last run'), time_format)
            if last_result == 'Running' and now - last_run_time < timedelta(hours=2):
                print(f'{function_name} already running since {last_run_time} - skipping for now')
                continue  # running on other PC for <2 hours - let it continue

            now_str = now.strftime(time_format)
            update_cell(i + 2, get_column('Last run'), now_str)
            update_cell(i + 2, get_column('Machine'), node())
            update_cell(i + 2, get_column('Last result'), 'Running')

            parameters_raw = properties.get('Parameters', '')
            if parameters_raw.startswith('@'):  # run on a particular computer
                if parameters_raw[1:] != node():  # but not this one
                    continue
                parameters = ''
            else:
                try:
                    parameters = float(parameters_raw)
                except ValueError:  # it's not a float, assume string
                    parameters = f'"{parameters_raw}"' if parameters_raw else ''  # wrap in quotes to send to function

            icon = properties.get('Icon', '')
            set_window_title(f'{icon} {function_name}')
            print('')
            print(now_str, function_name, parameters)
            try:
                return_value = eval(f'{function_name}({parameters})')
            except Exception as exception:  # something went wrong with the task!
                return_value = exception
                exception_type, exception_value, exception_traceback = sys.exc_info()
                error_lines = format_exc().split('\n')
                result = '\n'.join(error_lines[4:])

            period = float(properties.get('Period', 1))  # default: once per day
            next_run_time = now + timedelta(days=period)
            next_task_time = min(next_task_time, next_run_time)
            match return_value:
                case False:  # postpone until next scheduled run
                    result = 'Postponed'
                case datetime():  # postpone until specific time
                    result = 'Postponed'
                    next_run_time = return_value
                case '' | None | True:  # success but no toast
                    result = 'Success'
                case str():  # success and toast summarising actions
                    result = 'Success'
                    print(return_value)
                    if len(return_value) >= 15:  # toast for long messages, otherwise title bar
                        pushbullet.push_note(f'{icon} {function_name}', return_value)
                    else:
                        title_toast = return_value  # note: only works for one per loop, use sparingly!
                case Exception():  # something went wrong with the task
                    next_run_time = now + timedelta(days=min_period)  # try again soon
                    split = last_result.split(' ')
                    fail_count = int(split[1]) + 1 if split[0] == 'Failure' else 1
                    if fail_count % 10 == 0:
                        # output e.g. ValueError in task.py:module:47 -> import.py:module:123
                        quick_trace = ' → '.join(
                            ':'.join([os.path.split(frame.filename)[-1], frame.name, str(frame.lineno)])
                            for frame in extract_tb(exception_traceback)[2:4])  # the first two will be inside run_tasks
                        note_text = f'{function_name} failed {fail_count} times on {node()}\n' + \
                            f'{exception_type.__name__} in {quick_trace}\n' + \
                            str(exception_value)
                        if fail_count == 20:
                            update_cell(i + 2, get_column(location), 'FALSE')  # disable it here
                            note_text += f'\nDisabled at {location.lower()}'
                        pushbullet.push_note('👁️ run_tasks', note_text)
                    print(result)  # the exception traceback
                    result = f'Failure {fail_count}'

            next_task_time = min(next_task_time, next_run_time)
            next_run_str = next_run_time.strftime(time_format)
            print('Next run time:', next_run_str)
            update_cell(i + 2, get_column('Next run'), next_run_str)
            print(result)
            update_cell(i + 2, get_column('Last result'), result)

        force_run = []  # only force run for first loop
        # Sleep up to 5 minutes more than needed to avoid race conditions (two computers trying to do task at same time)
        next_task_time += timedelta(seconds=hash(node()) % 300)
        next_time_str = next_task_time.strftime("%H:%M")
        print(f'Waiting until {next_time_str}')
        set_window_title(f'{title_toast} ⌛️ {next_time_str}')
        while datetime.now() < next_task_time:
            sleep(60)

        # restart code
        for file, mod_time in imports.items():
            if mod_time != os.path.getmtime(file):
                functions = ','.join([func.__name__ for func, filename in import_dict.items() if filename == file])
                set_window_title('🔁 Restarting')
                print(f'Change detected in {file}, functions {functions}\nRestarting\n\n')
                os.chdir(start_dir)
                # force rerunning those functions
                subprocess.Popen([sys.executable, sys.argv[0], functions])
                exit()


def set_window_title(text: str) -> None:
    """Set the title of the Python command window (Windows only)."""
    if sys.platform == 'win32':
        os.system(f'title {text}')


if __name__ == '__main__':
    run_tasks()
