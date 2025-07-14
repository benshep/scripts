# Workflow:
#  - insert memory card with photos
#  - script runs
import os
import subprocess
import sys
from collections import Counter
from shutil import move  # safer than os.rename across different filesystems
from datetime import datetime, date, timedelta
from time import sleep
from typing import Generator
from send2trash import send2trash

from folders import user_profile
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!
from copy_60_minutes import get_pushes  # TODO: put in its own file

nzp = '#' if sys.platform == 'win32' else '-'  # character for no zero padding in dates - platform-specific!
script_start = datetime.now() - timedelta(hours=1)
pushbullet = Pushbullet(api_key)
pics_folder = os.path.join(user_profile, 'Pictures')
temp_folder = os.path.join(pics_folder, str(script_start.year), script_start.strftime('%m-%d %H%M moved by Eddie'))
app_title = '📷 Move photos'


# Run stuff on USB insert: https://askubuntu.com/questions/25071/how-to-run-a-script-when-a-specific-flash-drive-is-mounted

class InvalidResponse(Exception):
    pass


def organise_photos():
    """Move pictures, prompt for descriptions, organise into folders."""
    taken_dates = move_photos_to_temp_folder()
    year_lookup = get_year_lookup(taken_dates)
    for _ in range(60):  # wait an hour?
        sleep(60)
        if not (responses := get_response(year_lookup)):
            continue
        if min(taken_dates) < min(date_value for date_value, _ in responses):
            pushbullet.push_note(app_title, 'Some photos outside described range')
        else:
            break
    else:
        pushbullet.push_note(app_title, f'No response received: photos left in {os.path.split(temp_folder)[-1]}')
        return

    moved_list = move_photos_to_organised_folders(responses)
    convert_mov_videos(moved_list)


def convert_mov_videos(moved_list: list[str]):
    """Run process to convert .mov videos to smaller .mkv format."""
    converted_count = 0
    space_reduction = 0
    for filename in moved_list:
        if filename.lower().endswith('.mov'):
            original_size = os.path.getsize(filename)
            new_filename = filename[:-3] + 'mkv'
            if subprocess.call(['ffmpeg', '-n', '-i', filename] + \
                               '-vcodec libx264 -acodec aac -preset medium -crf 22 -ab 96k'.split(' ') +
                               [new_filename]) == 0:
                space_reduction += (original_size - os.path.getsize(new_filename)) / 1024 ** 2
                send2trash(filename)  # remove original if conversion successful
                converted_count += 1
    if converted_count:
        pushbullet.push_note(app_title,
                             f'Converted {converted_count} .mov videos to .mkv\n{space_reduction:.0f} MB saved')


def move_photos_to_organised_folders(responses: list[tuple[date, str]]) -> list[str]:
    os.chdir(temp_folder)
    file_counter = Counter()
    moved_list = []
    for filename in os.listdir():
        taken_date = datetime.fromtimestamp(os.path.getmtime(filename)).date()
        for date_value, description in responses:
            if taken_date >= date_value:
                folder_name = os.path.join(str(date_value.year), f"{date_value.strftime('%m-%d')} {description}")

        destination_folder = os.path.join(pics_folder, folder_name)
        os.makedirs(destination_folder, exist_ok=True)
        moved_list.append(move(filename, destination_folder))
        file_counter[folder_name] += 1
    os.chdir('..')
    os.rmdir(temp_folder)
    pushbullet.push_note(app_title, '\n'.join(f'{folder}: {count} files' for folder, count in file_counter.items()))
    return moved_list


def move_photos_to_temp_folder() -> list[date]:
    """Move pictures off memory card onto local storage."""
    #  move all pics from folders under DCIM to single folder under Pictures
    folder = r'D:/DCIM' if sys.platform == 'win32' else '/media/ben/SD-4GB/DCIM'
    os.chdir(folder)
    os.makedirs(temp_folder)

    taken_dates = set()
    # loop through folders under DCIM
    for dirpath, _, filenames in os.walk(folder):
        for file in filenames:
            full_filename = os.path.join(dirpath, file)
            taken_date = datetime.fromtimestamp(os.path.getmtime(full_filename)).date()
            if taken_date.year == 2014:  # likely the 'if found' image
                continue
            taken_dates.add(taken_date)
            move(full_filename, temp_folder)

    # send message via Pushbullet to say "move complete" and lists contiguous date ranges (e.g. 30-31 July, 9-12 August)
    taken_dates = sorted(list(taken_dates))
    pushbullet.push_note(app_title, '\n'.join(date_groups(taken_dates)) + '\nRemove memory card')
    return taken_dates


def get_year_lookup(taken_dates: list[date]) -> dict[int, int]:
    """Return a mapping for month -> year, to ensure unambiguous input."""
    year_lookup = {}  # mapping for month -> year, to ensure unambiguous input
    for taken_date in taken_dates:
        if taken_date.month not in year_lookup:
            year_lookup[taken_date.month] = taken_date.year
        elif year_lookup[taken_date.month] != taken_date.year:
            # ambiguous - more than one year for a month (e.g. have pics from Jan 2024 and Jan 2025)
            year_lookup[taken_date.month] = 0
    return year_lookup


def get_response(year_lookup: dict[int, int]) -> list[tuple[date, str]]:
    """Read message back regarding folder names. For instance:
    07-30 Weekend away
    08-09 Other thing
    08-10 Something else"""
    pushes = get_pushes(pushbullet, modified_after=script_start.timestamp())
    for push in pushes:
        if 'title' in push:  # most have titles: looking for one without (sent from phone)
            return []
        try:
            return [response_line(line, year_lookup) for line in push.get('body', '').splitlines()]
        except InvalidResponse as issue:
            pushbullet.push_note(app_title, issue.args[0])
            return []  # wait for another response
    return []  # no response received


def response_line(line: str, year_lookup: dict[int, int]) -> tuple[date, str]:
    """Is this line in the format mm-dd description, or yyyy-mm-dd description?"""
    date_text, description = line.split(' ', maxsplit=1)
    # how many dashes? 1 for mm-dd, 2 for yyyy-mm-dd
    try:
        date_elements = [int(element) for element in date_text.split('-')]
    except ValueError:  # bad int
        raise InvalidResponse(f"Bad date: {date_text}")
    if (element_count := len(date_elements)) not in (2, 3):
        raise InvalidResponse(f"Bad date: {date_text}")
    if element_count == 2:
        month, day = date_elements
        try:
            year = year_lookup[month]
            if year == 0:  # ambiguous: need a year for this one
                raise InvalidResponse(f"Date {date_text} needs a year to be specified")
        except KeyError:
            raise InvalidResponse(f"No photos from {date_text}")
    else:
        year, month, day = date_elements
    try:
        return date(year, month, day), description.strip()
    except ValueError:
        raise InvalidResponse(f"Bad date: {date_text}")


def date_groups(item_list: list[date]) -> Generator[str]:
    """Convert a list of dates into a list of first and last of consecutive subgroups."""
    first = last = item_list[0]
    for n in item_list[1:]:
        if n - timedelta(days=1) == last:  # Part of the group, bump the end
            last = n
        else:  # Not part of the group, yield current group and start a new
            yield range_text(first, last)
            first = last = n
    yield range_text(first, last)  # Yield the last group


def range_text(first: date, last: date) -> str:
    """Convert first and last date into human-readable date range (e.g. 1-10 January, 5 July - 8 August)."""
    year_suffix = ' %Y' if last.year == script_start.year else ''
    dmy_format = f'%{nzp}d %b{year_suffix}'
    if first.year != last.year:
        dmy_format = f'%{nzp}d %b %Y'
        return first.strftime(dmy_format) + ' - ' + last.strftime(dmy_format)
    elif first.month != last.month:
        return first.strftime(f'%{nzp}d %b - ') + last.strftime(dmy_format)
    elif first.day != last.day:
        return first.strftime(f'%{nzp}d-') + last.strftime(dmy_format)
    else:
        return last.strftime(dmy_format)


if __name__ == '__main__':
    # print(get_response({7: 2025}))
    # print(move_photos_to_temp_folder())
    # print(get_year_lookup([date(2025, 6, 29), date(2025, 7, 5)]))
    print(organise_photos())