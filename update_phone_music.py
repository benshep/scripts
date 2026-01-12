import asyncio
import os
import re
from datetime import datetime, timedelta

import phrydy  # for media file tagging
from dateutil.relativedelta import relativedelta  # for adding months to dates
from pushbullet import Pushbullet  # to show notifications
from send2trash import send2trash

import folders
import media
from lastfm import lastfm  # contains secrets, so don't show them here
from pushbullet_api_key import api_key  # local file, keep secret!

test_mode = False  # don't change anything!


def update_phone_music():
    """Deleted listened-to radio files, and fill up the music folder to capacity."""
    scrobbles = get_scrobbled_titles(lastfm.get_user('ning'))
    start_time = datetime.now()
    toast = asyncio.run(check_radio_files(scrobbles))
    print(datetime.now() - start_time)
    return toast


async def check_radio_files(scrobbled_titles):
    """Find and remove recently-played tracks from the Radio folder. Fix missing titles in tags."""
    scrobbled_radio = []  # list of played radio files to delete
    first_unheard = ''  # first file in the list that hasn't been played
    extra_played_count = 0  # more files that have been played, after one that apparently hasn't
    os.chdir(folders.radio_folder)
    radio_files = os.listdir()
    print(f'{len(radio_files)} files in folder')
    # loop over radio files - first check if they've been scrobbled, then try to correct tags where titles aren't set
    file_count = 0
    # min_date = None
    bump_dates = []
    toast = ''
    # total_hours = 0
    which_artist = {}

    files = [file for file in sorted(radio_files) if media.is_media_file(file)]
    async with asyncio.TaskGroup() as task_group:
        tasks = [task_group.create_task(asyncio.to_thread(phrydy.MediaFile, file)) for file in files]
    all_tags = [t.result() for t in tasks]
    for file, tags in zip(files, all_tags):
        try:
            file_date = datetime.strptime(file[:10], '%Y-%m-%d')
        except ValueError:
            continue  # not a date-based filename

        file_count += 1
        # min_date = min_date or file_date  # set to first one
        # weeks = (file_date - min_date).days // 7

        # remove archive In Our Time episodes
        if '(Archive Episode)' in file:
            toast += delete_file(file)
            continue

        # tags = phrydy.MediaFile(file)
        tags_changed = False
        # total_hours += tags.length / 3600

        track_title = media.artist_title(tags)
        if track_title in scrobbled_titles:
            print(f'[{file_count}] ✔ {track_title}')
            if not first_unheard:  # only found played files so far
                scrobbled_radio.append(file)  # possibly delete this one
            else:
                extra_played_count += 1  # don't delete, but flag as played for later
        elif not first_unheard:
            print(f'[{file_count}] ❌ {track_title}')
            first_unheard = file  # not played this one - flag it if it's the first in the list that's not been played
        elif file_count % 10 == 0:  # bump up first tracks of later-inserted albums to this point
            bump_date = file_date.replace(day=1) + relativedelta(months=1)  # first day of next month - for consistency
            if bump_date not in bump_dates:
                bump_dates.append(bump_date)  # but maintain a list, don't bump everything here

        # unhelpful titles - set it from the filename instead
        if tags.title in ('', 'Untitled Episode', None) \
                or (tags.title.lower() == tags.title and '_' in tags.title and ' ' not in tags.title):
            print(f'[{file_count}] Set {file} title to {file[11:-4]}')
            tags.title = file[11:-4]  # the bit between the date and the extension (assumes 3-char ext)
            tags_changed = True

        if not tags.albumartist:
            if artist := tags.artist or which_artist.get(tags.album):
                print(f'[{file_count}] Set {file} album artist to {artist}' +
                      (' (guessed from album)' if tags.artist is None else ''))
                tags.artist = artist
                tags.albumartist = artist
                tags_changed = True

        # sometimes tracks get an album name but not an artist - try to determine what it would be from existing files
        if tags.album in which_artist:
            if which_artist[tags.album] is not None and which_artist[tags.album] != tags.artist:
                which_artist[tags.album] = None  # mismatch
                print(f'[{file_count}] (multiple artists) - {tags.album}')
        else:  # not seen this album before
            which_artist[tags.album] = tags.artist
            print(f'[{file_count}] {tags.artist} - {tags.album}')
            # is it a new album fairly far down the list?
            if ('(bumped from ' not in file  # don't bump anything more than once
                    and not tags_changed  # don't rename if we want to save tags - might have weird results
                    and bump_dates and bump_dates[0] + timedelta(weeks=4) < file_date):  # not worth bumping <4 weeks
                new_date = bump_dates.pop(0).strftime("%Y-%m-%d")  # i.e. the next bump date from the list
                toast += f'🔼 {file}\n'
                os.rename(file, f'{new_date} (bumped from {file[:10]}) {file[11:]}')

        if tags_changed and not test_mode:
            tags.save()

    for file in scrobbled_radio[:-1]:  # don't delete the last one - we might not have finished it
        toast += delete_file(file)
    if extra_played_count > 2 and first_unheard:  # flag if something is getting 'stuck' at the top of the list
        toast += f'🚩 {first_unheard}: not played but {extra_played_count} after\n'
    # toast += f'📻 {file_count} files; {weeks} weeks; {total_hours:.0f} hours\n'
    return toast


def delete_file(file: str) -> str:
    """Delete a file, and return a toast line about it."""
    if not test_mode and os.path.exists(file):
        send2trash(file)
    return f'🗑️ {os.path.splitext(file)[0]}\n'


def get_scrobbled_titles(lastfm_user, limit=999) -> list[str]:
    # get recently played tracks (as reported by Last.fm)
    return [f'{track.track.artist.name} - {track.track.title}'.lower() for track in
            (lastfm_user.get_recent_tracks(limit=limit))]  # limit <= 999


def get_data_from_music_update(push):
    """Given a Pushbullet toast, return the date and the number of files, weeks, hours."""
    date = datetime.fromtimestamp(push['created'])
    status_line = next(line for line in push['body'].split('\n') if line.startswith('📻'))
    match = re.match(r'📻 (\d+) files; (\d+) weeks; (\d+) hours', status_line)
    files, weeks, hours = match.group(1, 2, 3)
    return date, int(files), int(weeks), int(hours)


def check_radio_hours_added():
    """Fetch the last 60 days of toasts, and determine how many hours were added to the radio files on average."""
    pb = Pushbullet(api_key)
    start = datetime.now() - timedelta(days=60)
    pushes = pb.get_pushes(modified_after=start.timestamp())
    music_updates = [push for push in pushes if push.get('title') == '🎧 Update phone music']

    last = music_updates[0]  # reverse chronological order
    first = music_updates[-1]
    last_date, _, _, last_hours = get_data_from_music_update(last)
    first_date, _, _, first_hours = get_data_from_music_update(first)
    hours_per_week = 7 * (last_hours - first_hours) / (last_date - first_date).days
    print(f'Since {first_date.strftime("%d/%m/%Y")}: {hours_per_week=:+.1f}')

    # for push in music_updates:
    #     created_date = datetime.fromtimestamp(push['created']).strftime('%d/%m/%Y %H:%M')
    #     try:
    #         status_line = next(line for line in push['body'].split('\n') if line.startswith('📻'))
    #     except StopIteration:
    #         continue
    #     print(created_date, status_line[2:], sep='; ')


def bump_down():
    """Bump an album down the list by increasing the date in the filename."""
    os.chdir(folders.radio_folder)
    radio_files = os.listdir()
    next_date = None
    for file in sorted(radio_files, reverse=True):  # get most recent first
        if not media.is_media_file(file):
            continue
        try:
            file_date = datetime.strptime(file[:10], '%Y-%m-%d')
        except ValueError:
            continue  # not a date-based filename

        tags = phrydy.MediaFile(file)
        if tags.album is None or "The Hitchhiker’s Guide to the Galaxy: The Complete Radio Series" not in tags.album:
            continue

        if not next_date:
            next_date = file_date
            print('Last file', file, next_date)
        else:
            next_date -= timedelta(days=6)
            os.rename(file, next_date.strftime('%Y-%m-%d') + file[10:])


if __name__ == '__main__':
    # get_artists(os.path.join(user_profile, 'Music'))
    # bump_down()
    test_mode = True
    print(update_phone_music())
