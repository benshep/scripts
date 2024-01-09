#!python3
# -*- coding: utf-8 -*-
import os
import phrydy  # to get media data
from lastfm import lastfm
import random
from collections import namedtuple, Counter
from datetime import datetime, timedelta
from shutil import copy2  # to copy files
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!
from send2trash import send2trash

user_folder = os.environ['UserProfile']
music_folder = os.path.join(user_folder, 'Music')
copy_log_file = os.path.join(music_folder, 'copied_already.txt')


def is_media_file(filename):
    return filename.lower().endswith(('.mp3', '.m4a', '.ogg', '.flac', '.opus', '.wma'))


def artist_title(filename):
    """Return {artist} - {title} string for a given file."""
    media_info = phrydy.MediaFile(filename)
    return f'{media_info.artist} - {media_info.title}'.lower()


def find_with_length(albums, low, high):
    """Find an album with a length between the two specified bounds."""
    try:
        # random sample up to len(albums) - effectively shuffles the list
        return next(a for a, f in random.sample(list(albums.items()), len(albums)) if low <= sum(f.values()) <= high)
    except StopIteration:
        return None


def copy_album(album, files, existing_folder=None):
    """Copy a given album to the copy folder."""
    bad_chars = str.maketrans({char: None for char in '*?/\\<>:|"'})  # can't use these in filenames

    def remove_bad_chars(filename: str):
        return filename.translate(bad_chars)

    folder, artist, title = album
    if title:
        no_artist = artist in (None, '', 'Various', 'Various Artists')
        album_filename = remove_bad_chars(title if no_artist else f'{artist} - {title}')
    else:
        album_filename = os.path.basename(folder)
    album_filename = album_filename[:60].strip()  # shorten path names (Windows limit: 260 chars)
    if existing_folder is None:  # making a new folder
        copied_name = datetime.strftime(datetime.now(), '%Y-%m-%d ') + album_filename
        os.mkdir(copied_name)
        n = 0
    else:  # copying into an existing folder
        copied_name = f'{existing_folder}; {album_filename}'
        os.rename(existing_folder, copied_name)
        n = len(os.listdir(copied_name))
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
    open(copy_log_file, 'a', encoding='utf-8').write('\t'.join(map(str, album)) + '\n')
    return copied_name


def scan_music_folder(max_count=0):
    bytes_to_minutes = 8 / (1024 * 128 * 60)
    os.chdir(music_folder)
    exclude_prefixes = tuple(open('not_cd_folders.txt').read().split('\n')[1:])  # first one is "_Copied" - this is OK
    copied_already = open(copy_log_file, encoding='utf-8').read().split('\n')
    print(f'{len(copied_already)} albums in copied_already list')

    def is_included(walk_tuple):
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


def check_folder_list(copy_folder_list):
    """Go through each copy folder in turn. Delete subfolders from it if they've been played."""
    scrobbles = get_scrobbles()
    toast = ''
    for i in reversed(range(len(copy_folder_list))):
        copy_folder = copy_folder_list[i].address
        os.chdir(copy_folder)
        # delete any that have been played
        subfolders = get_subfolders()
        for subfolder in subfolders:
            print(subfolder)
            os.chdir(subfolder)
            files = os.listdir()
            played_count = len([filename for filename in files if artist_title(filename) in scrobbles])
            file_count = len(files)
            print(f'Played {played_count}/{file_count} tracks')
            os.chdir('..')

            if played_count >= file_count / 2:
                send2trash(subfolder)
                toast += f'❌ {subfolder[11:]}\n'
                subfolders.remove(subfolder)
        if len(subfolders) >= copy_folder_list[i].min_count:  # got enough albums in this folder
            del copy_folder_list[i]
    return toast, copy_folder_list


def get_scrobbles():
    """Get recently played tracks (as reported by Last.fm)."""
    played_tracks = lastfm.get_user('ning').get_recent_tracks(limit=200)
    return [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]


def get_subfolders():
    """Return the subfolders in a folder that have a date prefix."""
    return [folder for folder in os.listdir() if folder.startswith('20')]


def copy_albums(copy_folder_list, albums):
    """Select random albums up to the given length for each folder."""
    toast = ''
    for copy_folder in copy_folder_list:
        os.chdir(copy_folder.address)
        folder_count = len(get_subfolders())
        while folder_count < copy_folder.min_count:
            while True:  # break out when we're done
                key = random.choice(list(albums.keys()))
                file_list = albums.pop(key)
                duration = sum(file_list.values())
                if copy_folder.min_length <= duration <= copy_folder.max_length:  # length that we're looking for?
                    print(key, int(duration))
                    folder_name = copy_album(key, file_list)
                    break
                elif duration < copy_folder.min_length:  # less than we want? look for another one to fill the rest of the time
                    print(key, int(duration))
                    gap_min_length = copy_folder.min_length - duration
                    gap_max_length = copy_folder.max_length - duration
                    second_key = find_with_length(albums, gap_min_length, gap_max_length)
                    if second_key is None:  # none to be found, try again
                        print(f'No albums with length between {gap_min_length:.0f} and {gap_max_length:.0f} minutes')
                        continue
                    second_file_list = albums.pop(second_key)
                    new_duration = sum(second_file_list.values())
                    print(second_key, int(new_duration))
                    duration += new_duration
                    folder_name = copy_album(second_key, second_file_list, copy_album(key, file_list))  # do first one first!
                    break
            folder_count += 1
            os.rename(folder_name, f'{folder_name} [{duration:.0f}]')  # rename with the total length
            toast += f'✔ {folder_name[11:]}\n'
    return toast


def copy_60_minutes():
    Folder = namedtuple('Folder', ['address', 'min_length', 'max_length', 'min_count'])
    extra_time = 0 if 4 <= datetime.now().month <= 10 else 5  # takes longer in winter!
    extra_time += 5  # extra mile during Keckwick Lane closure period
    copy_folder_list = [Folder(os.path.join(user_folder, 'Commute'), 55 + extra_time, 70 + extra_time, 4),
                        Folder(os.path.join(user_folder, '40 minutes'), 35, 40, 2)]
    print(copy_folder_list)
    toast, copy_folder_list = check_folder_list(copy_folder_list)
    if not copy_folder_list:
        print('Not ready to copy new album.')
        return

    albums = scan_music_folder()
    list_by_length(albums, max_length=80)
    toast += copy_albums(copy_folder_list, albums)

    if toast:
        Pushbullet(api_key).push_note('🎵 Commute Music', toast)


def list_by_length(albums, max_length=0):
    """List the number of albums by length."""
    length_counter = Counter()
    for key, file_list in albums.items():
        duration = sum(file_list.values())
        length_counter[int(duration // 5 * 5)] += 1  # round to next-lowest 5 minutes
    for length in sorted(length_counter.keys()):
        if max_length and length > max_length:
            break
        print(length, length_counter[length], sep='\t')


def check_previous():
    """Fetch previous toasts, and determine how many hours were added to the radio files on average."""
    pb = Pushbullet(api_key)
    start = datetime.now() - timedelta(days=360)
    pushes = pb.get_pushes(modified_after=start.timestamp())
    music_updates = [push for push in pushes if push.get('title') == '🎵 Commute Music']

    for update in music_updates:
        for line in update['body'].splitlines():
            if line.startswith('✔'):
                print(line)


if __name__ == '__main__':
    list_by_length(scan_music_folder(max_count=20), max_length=50)
