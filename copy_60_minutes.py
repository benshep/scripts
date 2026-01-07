import asyncio
import os
import random
import re
import time
from collections import Counter
from datetime import datetime, timedelta
from difflib import get_close_matches
from functools import reduce
from shutil import copy2  # to copy files
from typing import NamedTuple

import phrydy  # to get media data
import progress.bar
import pushbullet
import requests
from send2trash import send2trash

from folders import user_profile, music_folder
from lastfm import lastfm
from media import is_media_file, artist_title
from pushbullet_api_key import api_key  # local file, keep secret!
from tools import remove_bad_chars

copy_log_file = 'copied_already.txt'
Album = dict[str, float]

test_mode = False


class Folder(NamedTuple):
    """A folder to copy albums into."""
    address: str
    """The address of the folder."""
    min_length: int
    """The minimum length in minutes of albums in this folder."""
    max_length: int
    """The maximum length in minutes of albums in this folder."""
    min_count: int
    """The minimum count of albums needed in this folder."""


class AlbumKey(NamedTuple):
    """The key used in album dicts."""
    folder: str
    """The folder containing the album."""
    artist: str
    """The artist of the album."""
    title: str
    """The title of the album."""

    def __repr__(self) -> str:
        # show second-level folder if under _Copied
        # e.g. Pink Floyd - The Division Bell (Emma)
        path = self.relative_path()
        name = path.split(os.path.sep)[1].strip('#') if path.startswith('_Copied') else ''
        return f'{self.artist} - {self.title}' + (f' ({name})' if name else '')

    def relative_path(self):
        """Strip the root music folder path from the start of the folder name."""
        return self.folder[len(music_folder) + 1:]

    def tab_join(self) -> str:
        r"""Output tab-separated folder-artist-title, but convert \ to / for cross-platform compatibility."""
        return '\t'.join((self.relative_path().replace("\\", "/"), self.artist, self.title))


class Tags(NamedTuple):
    """Selected tags relating to a given media file."""
    folder: str
    """The folder containing the file."""
    file: str
    """The filename."""
    artist: str
    """The album artist if available, otherwise the artist."""
    album_title: str
    """The album title."""
    length: float
    """The length of the album in minutes."""


def copy_album(album: AlbumKey, files: Album, existing_folder: str = '') -> str:
    """Copy a given album to the copy folder."""
    if album.title:
        no_artist = album.artist in (None, 'None', '', 'Various', 'Various Artists')
        album_filename = remove_bad_chars(album.title if no_artist else f'{album.artist} - {album.title}')
    else:
        album_filename = os.path.basename(album.folder)
    album_filename = album_filename[:60].strip('. ')  # shorten path names (Windows limit: 260 chars) and remove dots
    if existing_folder:  # copying into an existing folder
        copied_name = f'{existing_folder}; {album_filename}'
        if not test_mode:
            os.rename(existing_folder, copied_name)
            n = max(int(file[:2]) for file in os.listdir(copied_name))  # highest track number in filename
        else:
            n = 0
    else:  # making a new folder
        copied_name = datetime.strftime(datetime.now(), '%Y-%m-%d ') + album_filename
        if not test_mode:
            os.mkdir(copied_name)
        n = 0
    if not test_mode:
        os.chdir(copied_name)
        for j, f in enumerate(files.keys(), start=1):
            media_info = phrydy.MediaFile(os.path.join(album.folder, f))
            name, ext = os.path.splitext(f)
            try:
                copy_filename = remove_bad_chars(f'{int(media_info.track) + n:02d} {media_info.title}{ext}')
            except (ValueError, TypeError):  # e.g. couldn't get track name or number
                copy_filename = f'{j + 1 + n:02d} {f}'  # fall back to original name
            copy2(os.path.join(album.folder, f), copy_filename)
        os.chdir('..')
        with open(os.path.join(music_folder, copy_log_file), 'a', encoding='utf-8') as log_handle:
            # don't write the music root folder, and convert '\' to '/' for cross-platform compatibility
            folder = album.folder[len(music_folder) + 1:].replace('\\', '/')
            log_handle.write(f'{folder}\t{album.artist}\t{album.title}\n')
    return copied_name


def reducible_copy_album(existing_folder: str, album_spec: tuple[AlbumKey, Album]) -> str:
    """Version of copy_album that can be passed to functools.reduce for multiple subsequent copy operations."""
    album, files = album_spec
    return copy_album(album, files, existing_folder)


def get_tags(folder: str, file: str, bar: progress.bar.Bar | None = None) -> Tags | None:
    """For a media file specified by the folder and file, return a Tags named tuple."""
    bytes_to_minutes = 8 / (1024 * 128 * 60)  # some buggy mp3s - assume 128kbps
    filename = os.path.join(folder, file)
    try:
        media = phrydy.MediaFile(filename)
    except Exception as e:
        print(f'No media info for {file}', e)
        return None
    if bar:
        bar.next()
    # use album artist (if available) so we can compare 'Various Artist' albums
    return Tags(folder, file, str(media.albumartist or media.artist), str(media.album),
                media.length / 60 if media.length else os.path.getsize(filename) * bytes_to_minutes)


def get_album_files() -> list[tuple[str, str]]:
    """Scan media files in the current folder and subfolders. Return a list of tuples (folder, file)."""
    base_folder = os.getcwd()
    exclude_prefixes = tuple(open('not_cd_folders.txt').read().split('\n')[1:])  # first one is "_Copied" - this is OK

    def include_folder(walk_tuple: tuple[str, list[str], list[str]]) -> bool:
        """Returns True if the given folder should be included, based on a set of prefixes to exclude."""
        include_folder.count += 1
        folder = walk_tuple[0]
        should_include = not folder[len(base_folder) + 1:].startswith(exclude_prefixes)
        if not should_include and test_mode:
            print('Excluding', folder[len(base_folder) + 1:])
        return should_include

    include_folder.count = 0
    included = filter(include_folder, os.walk(base_folder))

    return [(folder, file)
            for folder, _, file_list in included
            for file in filter(is_media_file, file_list)]


async def copy_albums(copy_folder_list: list[Folder], supplied_file_list: list[tuple[str, str]]) -> str:
    """Select random albums up to the given length for each folder.
    Avoids a big scan of tags by picking folders and files at random from a (fast) os.walk list."""
    event_loop = asyncio.get_event_loop()
    toast = ''
    scanned_albums: dict[AlbumKey, Album] = {}
    """Albums are defined by distinct values of (folder, artist, album_name).
    Each value in the album dict is a dict with filenames as keys and duration in minutes as values."""
    os.chdir(music_folder)
    base_folder = os.getcwd()  # in case of symlinks: base_folder != music_folder
    copied_already = read_copy_log()
    start_time = datetime.now()
    for copy_folder in copy_folder_list:
        file_list = supplied_file_list.copy()  # reset file list since we remove from it for each copy_folder
        print('\n', copy_folder, sep='')
        min_length, max_length = copy_folder.min_length, copy_folder.max_length
        maybe_list: list[dict[AlbumKey, Album]] = []
        os.chdir(copy_folder.address)
        to_copy = 10 if test_mode else copy_folder.min_count - len(get_subfolders())
        while to_copy > 0 and len(file_list) > 0:

            # pick a random folder and a random track from it
            chosen_folder = random.choice(list(set(folder for folder, _ in file_list)))
            chosen_file = random.choice([file for folder, file in file_list if folder == chosen_folder])

            # scanned this folder yet?
            bar = None
            chosen_key = next((key for key, album in scanned_albums.items()
                               if key[0] == chosen_folder and chosen_file in album),
                              None)
            if not chosen_key:  # not scanned this folder yet
                # find other tracks in album - how long is it?
                folder_files = [file for folder, file in file_list if folder == chosen_folder]
                if len(folder_files) > 20:  # display progress if it's going to take a while
                    bar = progress.bar.IncrementalBar(chosen_folder[len(base_folder) + 1:],
                                                      max=len(folder_files),
                                                      suffix='%(index)d/%(max)d | %(eta)ss ')
                folder_tags = await asyncio.gather(*[
                    event_loop.run_in_executor(None, get_tags, *(chosen_folder, file, bar))
                    for file in folder_files])
                # add everything in folder to albums list for later reference
                for tags in folder_tags:
                    # albums is a dict of dicts: each subdict stores (file, duration) as (key, value) pairs
                    key = AlbumKey(tags.folder, tags.artist, tags.album_title)
                    scanned_albums.setdefault(key, {})[tags.file] = tags.length
                    if tags.file == chosen_file:
                        chosen_key = key

            print(chosen_key, end=' ')
            # remove all tracks from list so we won't choose it again
            for file in scanned_albums[chosen_key]:
                file_list.remove((chosen_folder, file))

            if chosen_key.tab_join() in copied_already:
                print('❌  copied already')
                continue

            if len(scanned_albums[chosen_key]) < 2:
                print('❌  not enough tracks')
                continue

            length = sum(scanned_albums[chosen_key].values())
            print(f'({round(length)} min)', end=' ')
            if length > max_length:
                print('❌  too long')
                continue

            # could we add this to any existing lists?
            new_lengths = [sum(sum(album.values()) for album in copy_dict.values()) + length
                           for copy_dict in maybe_list]
            in_range = [min_length <= new_length <= max_length for new_length in new_lengths]
            below_max = [new_length <= max_length for new_length in new_lengths]
            index = in_range.index(True) if any(in_range) else below_max.index(True) if any(below_max) else None
            if index is not None:
                copy_dict = maybe_list[index]
                new_length = new_lengths[index]
                print('✔️ appended to', *copy_dict.keys())
                copy_dict[chosen_key] = scanned_albums[chosen_key]
            else:  # new list
                maybe_list.append({chosen_key: scanned_albums[chosen_key]})
                new_length = length
                print('✔️')
            if new_length >= min_length:
                to_copy -= 1
                print(f'✔️ Got enough, {to_copy=}')

        if to_copy:  # ran out of albums
            return toast + f'⏹ Not enough found with length {copy_folder.min_length}-{copy_folder.max_length} minutes\n'

        # copy from copy_list
        for copy_dict in maybe_list:
            total_length = sum(sum(album.values()) for album in copy_dict.values())
            if min_length <= total_length <= max_length:
                copied_already |= {key.tab_join() for key in copy_dict.keys()}
                folder_name = reduce(reducible_copy_album, copy_dict.items(), '')
                folder_name_inc_length = f'{folder_name} [{total_length:.0f}]'
                if not test_mode:
                    os.rename(folder_name, folder_name_inc_length)
                toast += f'✔ {folder_name_inc_length[11:]}\n'
    files_scanned = sum(len(album) for album in scanned_albums.values())
    elapsed_seconds = (datetime.now() - start_time).total_seconds()
    scan_percentage = 100 * files_scanned / len(file_list)
    print(f'Read {files_scanned} files ({scan_percentage:.1f}% of total) in {elapsed_seconds :.1f}s, {files_scanned / elapsed_seconds :.0f} files/sec')
    return toast


def read_copy_log() -> set[str]:
    """Read the copied_already.txt log file and output a set of lines in the file.
    Each line consists of a relative file path, album artist and title, separated by tabs.
    Path separators in the file are always stored as '/'.
    Multiple copies of the log are merged into a single file."""
    base, ext = os.path.splitext(copy_log_file)
    # deal with multiple copies of the log (typically Syncthing-generated)
    copied_already = set()
    for name in os.listdir(music_folder):
        if name.startswith(base) and name.endswith(ext):
            copied_already |= set(open(name, encoding='utf-8').read().split('\n'))
            if name != copy_log_file:  # get rid of other copies and keep the original
                send2trash(name)
    # Allow one album from the copied_already list back into the list
    rescued = random.choice(tuple(copied_already))
    print('Rescued', rescued)
    if not test_mode:
        copied_already.remove(rescued)
    open(copy_log_file, 'w', encoding='utf-8').write('\n'.join(copied_already) + '\n')
    print(f'{len(copied_already)} albums in copied_already list')
    return copied_already


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
        if test_mode or len(subfolders) < copy_folder.min_count:  # need more albums in this folder
            folders_to_fill.append(copy_folder)
    return toast, folders_to_fill


def get_scrobbles() -> list[str]:
    """Get recently played tracks (as reported by Last.fm)."""
    played_tracks = lastfm.get_user('ning').get_recent_tracks(limit=200)
    return [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]


def get_subfolders() -> list[str]:
    """Return the subfolders in a folder that have a date prefix."""
    return [folder for folder in os.listdir() if folder.startswith('20') and os.path.isdir(folder)]


def find_copy_folders() -> list[Folder]:
    """Look through the Radio folder to find folders named like '55-70 minutes x6'. Return a list of those folders."""
    extra_time = 0 if 4 <= datetime.now().month <= 10 else 5  # takes longer in winter!
    radio_folder = os.path.join(user_profile, 'Radio')
    os.chdir(radio_folder)
    folder_list = []
    for folder in os.listdir():
        if not os.path.isdir(folder):
            continue
        if not (match := re.match(r'(?P<min_length>\d+)-(?P<max_length>\d+) minutes x(?P<count>\d+)', folder)):
            continue
        folder_list.append(Folder(os.path.join(radio_folder, folder),
                                  int(match['min_length']) + extra_time, int(match['max_length']) + extra_time,
                                  int(match['count'])
                                  ))
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

    os.chdir(music_folder)
    return toast + asyncio.run(copy_albums(copy_folder_list, get_album_files()))


def list_by_length(albums: dict[AlbumKey, Album], max_length: int = 0) -> None:
    """List the number of albums by length."""
    length_counter = Counter()
    for key, file_list in albums.items():
        duration = sum(file_list.values())
        length_counter[int(duration // 5 * 5)] += 1  # round to next-lowest 5 minutes
    max_count = max(length_counter.values())
    for length in sorted(length_counter.keys()):
        if max_length and length > max_length:
            break
        print(length, length_counter[length], "*" * int(60 * length_counter[length] / max_count), sep='\t')


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
    # then = datetime.now()
    # print(*scan_music_folder().items(), sep='\n')
    # print(datetime.now() - then)
    test_mode = True
    print(copy_60_minutes())
