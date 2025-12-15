import importlib
import importlib.util
import os
import subprocess
import sys
import warnings
from threading import Thread
from types import ModuleType

import cryptography.utils
from rpyc import ThreadedServer

warnings.filterwarnings('ignore', category=cryptography.utils.CryptographyDeprecationWarning)
from datetime import datetime, timedelta
start_time = datetime.now()
from time import sleep
from traceback import format_exc, extract_tb
from platform import node

import psutil
import google_api  # pip install google-api-python-client
from rich import print  # rich-text printing
from rich.traceback import install  # rich tracebacks
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!
from folders import docs_folder


# Spreadsheet ID: https://docs.google.com/spreadsheets/d/XXX/edit#gid=0
sheet_id = '1T9vTsd6mW0sw6MmVsMshbRBRSoDh7wo9xTxs9tqYr7c'  # Automation spreadsheet
sheet_name = 'Sheet1'

install()  # rich text


def lazy_import(name: str) -> ModuleType:
    """Import a module with the given name."""
    spec = importlib.util.find_spec(name)
    loader = importlib.util.LazyLoader(spec.loader)
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    module.mod_time = os.path.getmtime(module.__file__)
    return module


def update_cell(row, col, string):
    google_api.update_cell(sheet_id, sheet_name, f'{col}{row}', string)


def run_tasks():
    # 'home' tasks
    task_dict = {  # function: module
        'change_wallpaper': lazy_import('change_wallpaper'),
        'update_phone_music': lazy_import('update_phone_music'),
        'copy_60_minutes': lazy_import('copy_60_minutes'),
        'get_youtube_playlists': lazy_import('get_youtube_playlists'),
        'get_usage_data': lazy_import('get_energy_usage'),
        'check_folders_for_bitrot': lazy_import('bitrot'),
        'erase_trailers': lazy_import('erase_trailers'),
        'update_saints_calendar': lazy_import('rugby_fixtures'),
        'update_gig_calendar': lazy_import('concerts'),
        'find_new_releases': lazy_import('concerts'),
        'log_crossings': lazy_import('mersey_gateway'),
    }

    at_home = docs_folder is None  # no work documents
    if not at_home:
        # 'work' tasks
        sys.path.append(os.path.join(docs_folder, 'Scripts'))
        task_dict |= {
            'find_new_python_packages': lazy_import('package_updates'),
            'annual_leave_check': lazy_import('oracle_staff_check'),
            'otl_submit': lazy_import('oracle_staff_check'),
            'leave_cross_check': lazy_import('group'),
            'run_otl_calculator': lazy_import('group'),
            'todos_from_notes': lazy_import('todos_from_notes'),
            'get_payslips': lazy_import('get_payslips'),
            'get_bookings': lazy_import('catering_bookings'),
            'check_page_changes': lazy_import('page_changes'),
            'live_update': lazy_import('page_changes'),
            'update_energy_data': lazy_import('energy_data'),
        }
        port = 18862
        print(f'Starting server, {port=}')
        server = ThreadedServer(lazy_import('outlook').OutlookService,
                                port=port, protocol_config={'allow_public_attrs': True})
        thread = Thread(target=server.start)
        thread.daemon = True
        thread.start()
    # track changes to this file too
    run_tasks_mod_time = os.path.getmtime(__file__)

    start_dir = os.getcwd()
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
        print('Fetching data from spreadsheet', datetime.now() - start_time)
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

            function_name = properties.get('Function name')
            function = getattr(task_dict[function_name], function_name)
            parameters = properties.get('Parameters', '')
            if parameters.startswith('@'):  # run on a particular computer
                if parameters[1:] != node():  # but not this one
                    continue
                parameters = ''
            else:
                try:
                    parameters = float(parameters)
                except ValueError:  # it's not a float, assume string
                    pass

            last_result = properties.get('Last result')
            now = datetime.now()
            next_run = properties.get('Next run')
            last_run_time = datetime.strptime(properties.get('Last run'), time_format)
            if next_run == 'on change':
                # look for changes in files
                newest_mod_time = max(os.path.getmtime(file) for file in function.file_list)
                if datetime.fromtimestamp(newest_mod_time) <= last_run_time:
                    continue
                else:
                    last_triggered = newest_mod_time  # to update in last run column
            else:  # run on a schedule
                last_triggered = now.strftime(time_format)
                next_run_time = datetime.strptime(next_run, time_format)
            if next_run_time > now and last_result in ('Success', 'Postponed') and function_name not in force_run:
                next_task_time = min(next_task_time, next_run_time)
                continue

            if last_result == 'Running' and now - last_run_time < timedelta(hours=2):
                print(f'{function_name} already running since {last_run_time} - skipping for now')
                continue  # running on other PC for <2 hours - let it continue

            update_cell(i + 2, get_column('Last run'), last_triggered)
            update_cell(i + 2, get_column('Machine'), node())
            update_cell(i + 2, get_column('Last result'), 'Running')

            icon = properties.get('Icon', '')
            set_window_title(f'{icon} {function_name}')
            print('\n', last_triggered, function_name, parameters)
            try:
                return_value = function() if parameters == '' else function(parameters)
            except Exception as exception:  # something went wrong with the task!
                return_value = exception
                exception_type, exception_value, exception_traceback = sys.exc_info()
                result = format_exc()

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
            if next_run != 'on change':  # scheduled task: set next run time
                next_run_str = next_run_time.strftime(time_format)
                print('Next run time:', next_run_str)
                update_cell(i + 2, get_column('Next run'), next_run_str)
            print(result)
            update_cell(i + 2, get_column('Last result'), result)

        if node() == 'eddie':
            break  # just run once on cron

        force_run = []  # only force run for first loop
        # Sleep up to 5 minutes more than needed to avoid race conditions (two computers trying to do task at same time)
        next_task_time += timedelta(seconds=hash(node()) % 300)
        next_time_str = next_task_time.strftime("%H:%M")
        print(f'Waiting until {next_time_str}')
        set_window_title(f'{title_toast} ⌛️ {next_time_str}')
        while datetime.now() < next_task_time:
            sleep(300)

            # restart code
            force_run = []  # only force run for one loop
            for function, module in task_dict.items():
                new_mod_time = os.path.getmtime(module.__file__)
                time_since_modified = datetime.now() - datetime.fromtimestamp(new_mod_time)
                if new_mod_time != module.mod_time and time_since_modified > timedelta(minutes=15):
                    force_run += [func for func, mod in task_dict.items() if mod == module]
                    importlib.reload(module)
                    task_dict[function].mod_time = new_mod_time
            if force_run:
                print(f'\nChange detected in functions', *force_run)
                break  # don't wait until next scheduled run

            if run_tasks_mod_time != os.path.getmtime(__file__):
                set_window_title('🔁 Restarting')
                os.chdir(start_dir)
                # force rerunning those functions
                subprocess.Popen([sys.executable, sys.argv[0]])
                exit()


def set_window_title(text: str) -> None:
    """Set the title of the Python command window (Windows only)."""
    if sys.platform == 'win32':
        os.system(f'title {text}')


if __name__ == '__main__':
    run_tasks()
