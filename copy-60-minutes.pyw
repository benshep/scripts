#!python3
# -*- coding: utf-8 -*-
import os
from phrydy import MediaFile  # to get media data
from lastfm import lastfm
import pickle  # to save state
from datetime import datetime
from shutil import copy2  # to copy files
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!
from send2trash import send2trash

test_mode = False  # don't change anything!
user_folder = os.environ['UserProfile']
copy_folder = os.path.join(user_folder, 'Commute')
db_filename = 'python_albums.db'
# act_filename = 'last_activity.db'
list_filename = '60-minutes.txt'
min_length = 55 * 60 * 1000
max_length = 70 * 60 * 1000
illegal_chars = str.maketrans({char: None for char in '*?/\\<>:|"'})

albums = pickle.load(open(db_filename, 'rb'))[0]

# get recently played tracks (as reported by Last.fm)
played_tracks = lastfm.get_user('ning').get_recent_tracks(limit=200)
scrobbled_titles = [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]

# delete the oldest if it's been played (assumes files have yyyy-mm-dd prefix)
folder_walk = list(os.walk(copy_folder))
hidden_files = os.path.join(copy_folder, '.')  # don't count hidden folders (like .stfolder)
oldest = min(root for root, dirs, files in folder_walk if not root.startswith(hidden_files) and root != copy_folder)
print(f'Oldest dir: {oldest}')
played_count = 0
for file in sorted(os.listdir(oldest)):
    media_info = MediaFile(os.path.join(oldest, file))
    if f'{media_info.artist} - {media_info.title}'.lower() in scrobbled_titles:
        played_count += 1
print(f'Played {played_count} tracks')

if test_mode or played_count > 3:
    if not test_mode:
        send2trash(oldest)
    toast = '❌ ' + oldest[len(copy_folder)+12:]  # skip yyyy-mm-dd bit for readability
else:
    print('Not ready to copy new album.')
    exit()

albums_60 = open(list_filename, 'r', encoding='utf-8').read().splitlines()
folder, artist, title = tuple(albums_60[-1].split('\t'))  # get the last one
# replace 'None' text with None
artist = None if artist == 'None' else artist
title = None if title == 'None' else title
album = (folder, artist, title)

no_artist = (None, '', 'Various', 'Various Artists')
album_filename = (title if artist in no_artist else f'{artist} - {title}'.translate(illegal_chars)) if title else os.path.basename(folder)

files = albums[album]
toast += '\n✔  ️' + album_filename
folder_name = datetime.strftime(datetime.now(), '%Y-%m-%d ') + album_filename
full_folder_name = os.path.join(copy_folder, folder_name)
if not test_mode:
    os.mkdir(full_folder_name)
duration = 0
for file in files.keys():
    filename, ext = os.path.splitext(file)
    media_info = MediaFile(os.path.join(folder, file))
    duration += media_info.length

    try:
        copy_filename = f'{int(media_info.track):02d} {media_info.title}{ext}'.translate(illegal_chars)
    except ValueError:  # e.g. couldn't get track name
        copy_filename = file  # fall back to original name
    if not test_mode:
        copy2(os.path.join(folder, file), os.path.join(full_folder_name, copy_filename))
os.rename(full_folder_name, f'{full_folder_name} [{duration / 60:.0f}]')

if not test_mode:
    # remove the last one from the list
    open(list_filename, 'w', encoding='utf-8').write('\n'.join(albums_60[:-1]) + '\n')

Pushbullet(api_key).push_note('🎵 Commute Music' + (' (Test Mode)' if test_mode else ''), toast)
