#!python3
# -*- coding: utf-8 -*-
import os
import phrydy  # to get media data
from lastfm import lastfm
import random
from datetime import datetime
from shutil import copy2  # to copy files
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!
from send2trash import send2trash

user_folder = os.environ['UserProfile']
music_folder = os.path.join(user_folder, 'Music')
copy_folder_list = [(os.path.join(user_folder, 'Commute'), 55, 70),
                    (os.path.join(user_folder, '40 minutes'), 35, 40)]
media_exts = ('.mp3', '.m4a', '.ogg', '.flac', '.opus')
bad_chars = str.maketrans({char: None for char in '*?/\\<>:|"'})  # can't use these in filenames

# get recently played tracks (as reported by Last.fm)
played_tracks = lastfm.get_user('ning').get_recent_tracks(limit=200)
scrobbles = [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]


def artist_title(filename):
    """Return {artist} - {title} string for a given file."""
    media_info = phrydy.MediaFile(filename)
    return f'{media_info.artist} - {media_info.title}'.lower()


toast = ''
# Go through each copy folder in turn. Delete subfolders from it if they've been played.
for i in reversed(range(len(copy_folder_list))):
    copy_folder = copy_folder_list[i][0]
    # delete the oldest if it's been played (assumes files have yyyy-mm-dd prefix)
    folder_walk = list(os.walk(copy_folder))
    hidden_files = os.path.join(copy_folder, '.')  # don't count hidden folders (like .stfolder)
    try:
        oldest = min(root for root, d, f in folder_walk if not root.startswith(hidden_files) and root != copy_folder)
    except ValueError:  # no subfolders!
        continue
    print(f'Oldest dir: {oldest}')
    played_count = len([f for f in sorted(os.listdir(oldest)) if artist_title(os.path.join(oldest, f)) in scrobbles])
    print(f'Played {played_count} tracks')

    if played_count > 3:
        send2trash(oldest)
        toast += '❌ ' + oldest[len(copy_folder)+12:]  # skip yyyy-mm-dd bit for readability
    else:
        del copy_folder_list[i]

if len(copy_folder_list) == 0:
    print('Not ready to copy new album.')
    exit()

albums = {}
os.chdir(music_folder)
exclude_prefixes = tuple(open('not_cd_folders.txt').read().split('\n')[1:])  # first one is "_Copied" - this is OK
for folder_name, folder_list, file_list in os.walk(music_folder):
    if folder_name[len(music_folder) + 1:].startswith(exclude_prefixes):
        continue
    if len(albums) % 30 == 0:
        print(folder_name)
    for file in file_list:
        filename = os.path.join(folder_name, file)
        name, ext = os.path.splitext(file)
        if ext.lower() in media_exts:
            try:
                tags = phrydy.MediaFile(filename)
            except:
                print(f'No media info for {file_list[0]}')
            # use album artist (if available) so we can compare 'Various Artist' albums
            artist = tags.albumartist if tags.albumartist else tags.artist
            album_name = tags.album
            duration = tags.length / 60  # in minutes
            if duration is None:
                duration = os.path.getsize(filename) * 8 / (1024 * 128 * 60)  # some buggy mp3s - assume 128kbps
            key = (folder_name, artist, album_name)
            if key in albums.keys():
                album_file_list = albums[key]
            else:
                albums[key] = album_file_list = {}
            album_file_list[file] = duration
# remove albums with only one track
albums = {key: file_list for key, file_list in albums.items() if len(file_list) > 1}


def find_with_length(low, high):
    """Find an album with a length between the two specified bounds."""
    try:
        # random sample up to len(albums) - effectively shuffles the list
        return next(a for a, f in random.sample(list(albums.items()), len(albums)) if low <= sum(f.values()) <= high)
    except StopIteration:
        return None


def copy_album(album, files, existing_folder=None):
    """Copy a given album to the copy folder."""
    folder, art, t = album
    no = (None, '', 'Various', 'Various Artists')
    album_filename = (t if art in no else f'{art} - {t}').translate(bad_chars) if t else os.path.basename(folder)
    if existing_folder is None:  # making a new folder
        copied_name = datetime.strftime(datetime.now(), '%Y-%m-%d ') + album_filename
        os.mkdir(copied_name)
        n = 0
    else:  # copying into an existing folder
        copied_name = f'{existing_folder}; {album_filename}'
        os.rename(existing_folder, copied_name)
        n = len(os.listdir(copied_name))
    os.chdir(copied_name)
    j = 0
    for f in files.keys():
        j += 1
        media_info = phrydy.MediaFile(os.path.join(folder, f))
        try:
            copy_filename = f'{int(media_info.track) + n:02d} {media_info.title}{ext}'.translate(bad_chars)
        except (ValueError, TypeError):  # e.g. couldn't get track name or number
            copy_filename = f'{j + n:02d} {f}'  # fall back to original name
        copy2(os.path.join(folder, f), copy_filename)
    os.chdir('..')
    return copied_name


# Now select random albums up to the given length for each folder
for copy_folder, min_length, max_length in copy_folder_list:
    os.chdir(copy_folder)
    while True:  # break out when we're done
        key = random.choice(list(albums.keys()))
        file_list = albums.pop(key)
        duration = sum(file_list.values())
        if min_length <= duration <= max_length:  # length that we're looking for?
            folder_name = copy_album(key, file_list)
            break
        elif duration < min_length:  # less than we want? look for another one to fill the rest of the time
            second_key = find_with_length(min_length - duration, max_length - duration)
            if second_key is None:  # none to be found, try again
                continue
            second_file_list = albums.pop(second_key)
            duration += sum(second_file_list.values())
            folder_name = copy_album(second_key, second_file_list, copy_album(key, file_list))  # do first one first!
            break

    os.rename(folder_name, f'{folder_name} [{duration:.0f}]')  # rename with the total length
    toast += '\n✔ ' + folder_name[11:]  # skip [YYYY-MM-DD] part

if toast:
    Pushbullet(api_key).push_note('🎵 Commute Music', toast)
