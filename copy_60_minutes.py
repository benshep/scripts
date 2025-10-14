import os
import re
import time
from difflib import get_close_matches
from typing import Any

import phrydy  # to get media data
import requests

from lastfm import lastfm
import random
from collections import namedtuple, Counter
from datetime import datetime, timedelta
from shutil import copy2  # to copy files
from media import is_media_file, artist_title
import pushbullet
from pushbullet_api_key import api_key  # local file, keep secret!
from send2trash import send2trash
from folders import user_profile, music_folder

copy_log_file = 'copied_already.txt'
Folder = namedtuple('Folder', ['address', 'min_length', 'max_length', 'min_count'])


def find_with_length(albums: dict[tuple[str, str | None, str | None], dict[str, float]],
                     low: int, high: int) -> tuple[str, str | None, str | None] | None:
    """Find an album with a length between the two specified bounds."""
    # random sample up to len(albums) - effectively shuffles the list
    return next(
        (album for album, files in
         random.sample(list(albums.items()), len(albums))
         if low <= sum(files.values()) <= high),
        None)


def copy_album(album: tuple[str, str, str], files, existing_folder=None):
    """Copy a given album to the copy folder."""
    bad_chars = str.maketrans({char: None for char in '*?/\\<>:|"'})  # can't use these in filenames

    def remove_bad_chars(filename: str) -> str:
        return filename.translate(bad_chars)

    folder, artist, title = album
    if title:
        no_artist = artist in (None, '', 'Various', 'Various Artists')
        album_filename = remove_bad_chars(title if no_artist else f'{artist} - {title}')
    else:
        album_filename = os.path.basename(folder)
    album_filename = album_filename[:60].strip('. ')  # shorten path names (Windows limit: 260 chars) and remove dots
    if existing_folder is None:  # making a new folder
        copied_name = datetime.strftime(datetime.now(), '%Y-%m-%d ') + album_filename
        os.mkdir(copied_name)
        n = 0
    else:  # copying into an existing folder
        copied_name = f'{existing_folder}; {album_filename}'
        os.rename(existing_folder, copied_name)
        n = max(int(file[:2]) for file in os.listdir(copied_name))  # highest track number in filename
    os.chdir(copied_name)
    for j, f in enumerate(files.keys(), start=1):
        media_info = phrydy.MediaFile(os.path.join(folder, f))
        name, ext = os.path.splitext(f)
        try:
            copy_filename = remove_bad_chars(f'{int(media_info.track) + n:02d} {media_info.title}{ext}')
        except (ValueError, TypeError):  # e.g. couldn't get track name or number
            copy_filename = f'{j + 1 + n:02d} {f}'  # fall back to original name
        copy2(os.path.join(folder, f), copy_filename)
    os.chdir('..')
    open(os.path.join(music_folder, copy_log_file), 'a', encoding='utf-8').write('\t'.join(map(str, album)) + '\n')
    return copied_name


def scan_music_folder(max_count: int = 0) -> dict[tuple[str, str | None, str | None], dict[str, float]]:
    bytes_to_minutes = 8 / (1024 * 128 * 60)
    os.chdir(music_folder)
    exclude_prefixes = tuple(open('not_cd_folders.txt').read().split('\n')[1:])  # first one is "_Copied" - this is OK
    base, ext = os.path.splitext(copy_log_file)
    # deal with multiple copies of the log (typically Syncthing-generated)
    copied_already = set()
    for name in os.listdir(music_folder):
        if name.startswith(base) and name.endswith(ext):
            copied_already |= set(open(name, encoding='utf-8').read().split('\n'))
            if name != copy_log_file:  # get rid of other copies and keep the original
                send2trash(name)
    open(copy_log_file, 'w', encoding='utf-8').write('\n'.join(copied_already) + '\n')

    print(f'{len(copied_already)} albums in copied_already list')

    def is_included(walk_tuple: tuple[str, list[str], list[str]]) -> bool:
        folder_name = walk_tuple[0]
        return not folder_name[len(music_folder) + 1:].startswith(exclude_prefixes)

    albums = {}
    line_len = 0
    for folder, folder_list, file_list in filter(is_included, os.walk(music_folder)):
        if max_count and len(albums) >= max_count:
            break
        if len(albums) % 10 == 0:
            output = folder[len(music_folder) + 1:]
            output += (line_len - len(output)) * ' '  # pad to length of previous output
            line_len = len(output)
            print(output, end='\r')  # keep on same line
        for file in filter(is_media_file, file_list):
            filename = os.path.join(folder, file)
            try:
                tags = phrydy.MediaFile(filename)
            except Exception as e:
                print(f'No media info for {file}', e)
                continue
            # use album artist (if available) so we can compare 'Various Artist' albums
            artist = tags.albumartist or tags.artist
            album_name = tags.album
            # some buggy mp3s - assume 128kbps
            duration = tags.length / 60 if tags.length else os.path.getsize(filename) * bytes_to_minutes
            key = (folder, artist, album_name)
            if '\t'.join(map(str, key)) in copied_already:
                continue
            # albums is a dict of dicts: each subdict stores (file, duration) as (key, value) pairs
            albums.setdefault(key, {})[file] = duration
    print('')  # next line
    # remove albums with only one track
    return {key: file_list for key, file_list in albums.items() if len(file_list) > 1}


def check_folder_list(copy_folder_list: list[Folder]) -> tuple[str, list[Folder]]:
    """Go through each copy folder in turn. Delete subfolders from it if they've been played."""
    scrobbles = get_scrobbles()
    toast = ''
    folders_to_fill = []
    for copy_folder in copy_folder_list:
        os.chdir(copy_folder.address)
        # delete any that have been played
        subfolders = get_subfolders()
        to_delete = []
        for subfolder in subfolders:
            print(subfolder)
            os.chdir(subfolder)
            files = [file for file in os.listdir() if is_media_file(file)]
            # sometimes Last.fm artists/titles aren't quite the same as mine - look for close matches
            played_count = len([filename for filename in files
                                if get_close_matches(artist_title(filename).lower(), scrobbles, n=1, cutoff=0.9)])
            file_count = len(files)
            print(f'Played {played_count}/{file_count} tracks')
            if played_count >= file_count / 2:
                to_delete.append(subfolder)
            os.chdir('..')

        for subfolder in to_delete:
            send2trash(subfolder)
            toast += f'❌ {subfolder[11:]}\n'
            subfolders.remove(subfolder)
        if len(subfolders) < copy_folder.min_count:  # need more albums in this folder
            folders_to_fill.append(copy_folder)
    return toast, folders_to_fill


def get_scrobbles() -> list[str]:
    """Get recently played tracks (as reported by Last.fm)."""
    played_tracks = lastfm.get_user('ning').get_recent_tracks(limit=200)
    return [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]


def get_subfolders() -> list[str]:
    """Return the subfolders in a folder that have a date prefix."""
    return [folder for folder in os.listdir() if folder.startswith('20') and os.path.isdir(folder)]


def copy_albums(copy_folder_list: list[Folder],
                albums: dict[tuple[str, str | None, str | None], dict[str, float]]) -> str | Any:
    """Select random albums up to the given length for each folder."""
    toast = ''
    for copy_folder in copy_folder_list:
        os.chdir(copy_folder.address)
        folder_count = len(get_subfolders())
        while folder_count < copy_folder.min_count:
            while len(albums) > 0:  # break out when we're done
                key = random.choice(list(albums.keys()))
                file_list = albums.pop(key)
                duration = sum(file_list.values())
                if copy_folder.min_length <= duration <= copy_folder.max_length:  # length that we're looking for?
                    print(key, int(duration))
                    folder_name = copy_album(key, file_list)
                    break
                elif duration < copy_folder.min_length:
                    # less than we want? look for another one to fill the rest of the time
                    print(*key, int(duration))
                    gap_min_length = copy_folder.min_length - duration
                    gap_max_length = copy_folder.max_length - duration
                    second_key = find_with_length(albums, gap_min_length, gap_max_length)
                    if second_key is None:  # none to be found, try again
                        print(f'No albums with length between {gap_min_length:.0f} and {gap_max_length:.0f} minutes')
                        continue
                    second_file_list = albums.pop(second_key)
                    new_duration = sum(second_file_list.values())
                    print(*second_key, int(new_duration))
                    duration += new_duration
                    # do first one first!
                    folder_name = copy_album(second_key, second_file_list, copy_album(key, file_list))
                    break
            else:  # didn't break out: ran out of albums before finding one of the right length
                # 13/3/25: still got 87 at 55-70 mins, maybe 20 weeks worth?
                return toast + f'⏹ None found with length {copy_folder.min_length}-{copy_folder.max_length} minutes\n'
            folder_count += 1
            os.rename(folder_name, f'{folder_name} [{duration:.0f}]')  # rename with the total length
            toast += f'✔ {folder_name[11:]}\n'
    return toast


def find_copy_folders() -> list[Folder]:
    """Look through the Radio folder to find folders named like '55-70 minutes x6'. Return a list of those folders."""
    extra_time = 0 if 4 <= datetime.now().month <= 10 else 5  # takes longer in winter!
    radio_folder = os.path.join(user_profile, 'Radio')
    os.chdir(radio_folder)
    folder_list = []
    for folder in os.listdir():
        if not os.path.isdir(folder):
            continue
        if not (match := re.match(r'(\d+)-(\d+) minutes x(\d+)', folder)):
            continue
        folder_list.append(Folder(os.path.join(radio_folder, folder),
                                  int(match.group(1)) + extra_time, int(match.group(2)) + extra_time,
                                  int(match.group(3))))
    return folder_list


def copy_60_minutes() -> str | datetime:
    """Find albums of the specified length to copy into subfolders of the Radio folder.
    The idea is to have whole albums to listen to on my bike commute to work."""
    copy_folder_list = find_copy_folders()
    print(*copy_folder_list, sep='\n')
    toast, copy_folder_list = check_folder_list(copy_folder_list)
    if not copy_folder_list:
        print('Not ready to copy new album.')
        return datetime.now().replace(hour=9, minute=0) + timedelta(days=1)  # try again 9am tomorrow

    albums = scan_music_folder()
    list_by_length(albums, max_length=80)
    toast += copy_albums(copy_folder_list, albums)
    return toast


def list_by_length(albums: dict[tuple[str, str | None, str | None], dict[str, float]],
                   max_length: int = 0) -> None:
    """List the number of albums by length."""
    length_counter = Counter()
    for key, file_list in albums.items():
        duration = sum(file_list.values())
        length_counter[int(duration // 5 * 5)] += 1  # round to next-lowest 5 minutes
    for length in sorted(length_counter.keys()):
        if max_length and length > max_length:
            break
        print(length, length_counter[length], sep='\t')


def get_pushes(pb: pushbullet.Pushbullet, modified_after: float | None = None, limit: int | None = None,
               filter_inactive: bool = True,
               wait_for_reset: bool = False,
               verbose: bool = False) -> list[dict]:
    """Version of get_pushes from pushbullet.py that allows for rate limiting.
    See https://docs.pushbullet.com/#ratelimiting
    If wait_for_reset is True, it will wait until the rate limit gets reset,
    otherwise it just returns what it has so far."""
    data = {"modified_after": modified_after, "limit": limit}
    if filter_inactive:
        data['active'] = "true"

    pushes_list = []
    previous_remaining = 0
    used = 0
    while True:
        r = pb._session.get(pb.PUSH_URL, params=data)
        if r.status_code != requests.codes.ok:
            raise pushbullet.PushbulletError(r.text)

        js = r.json()
        # The units are a sort of generic 'cost' number. A request costs 1 and a database operation costs 4.
        # So reading 500 pushes costs about 500 database operations + 1 request = 500*4 + 1 = 2001
        reset = int(r.headers.get('X-Ratelimit-Reset'))  # when it resets (integer seconds in Unix Time)
        rate_limit = int(r.headers.get('X-Ratelimit-Limit'))  # what the ratelimit is
        remaining = int(r.headers.get('X-Ratelimit-Remaining'))  # how much you have remaining
        if previous_remaining > 0:
            used = previous_remaining - remaining
        previous_remaining = remaining
        reset_time = datetime.fromtimestamp(reset)
        if verbose:
            print(f'{reset_time=} {rate_limit=} {remaining=} {used=}')
        pushes_list += js.get("pushes")
        if remaining < 2 * used:  # we could use up to 2x more next time (seems to be mostly 85 but sometimes lower)
            if wait_for_reset:
                print('Waiting for rate limit reset at', reset_time)
                time.sleep(reset - datetime.now().timestamp() + 5)
            else:
                break
        if 'cursor' in js and (not limit or len(pushes_list) < limit):
            if verbose:
                print(f'Got {len(pushes_list)} pushes')
            data['cursor'] = js['cursor']
        else:
            break

    return pushes_list


def check_previous() -> None:
    """Fetch previous toasts, and determine how many hours were added to the radio files on average."""
    pb = pushbullet.Pushbullet(api_key)
    start = datetime.now() - timedelta(days=1000)
    pushes = get_pushes(pb, modified_after=start.timestamp(), wait_for_reset=True, verbose=True)
    music_updates = [push for push in pushes if push.get('title') == '🎵 Commute Music']

    for update in music_updates:
        for line in update['body'].splitlines():
            if line.startswith('✔'):
                print(line)


if __name__ == '__main__':
    copy_60_minutes()