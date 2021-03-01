#!python3
# -*- coding: utf-8 -*-
import os
from random import choice
from lastfm import lastfm  # contains secrets, so don't show them here
from phrydy import MediaFile  # to get media data
from time import time, sleep

music_folder = os.path.join(os.environ['UserProfile'], 'Music')
exclude_prefixes = tuple(open(os.path.join(music_folder, 'not_cd_folders.txt')).read().split('\n'))
root_len = len(music_folder) + 1
cd_folders = []

for folder, folder_list, file_list in os.walk(music_folder):
    name = folder[root_len:]
    if not name.startswith(exclude_prefixes) and (' - ' in name or os.path.sep in name or 'best of' in name.lower()):
        cd_folders.append(name)

folder = choice(cd_folders)
os.system(f'title {folder}')  # set title of window
print(folder)
start_time = int(time())
os.chdir(os.path.join(music_folder, folder))
track_list = sorted([MediaFile(file) for file in os.listdir() if file.lower().endswith(('mp3', 'm4a', 'wma'))],
                    key=lambda media: int(media.track))
[print(f'{media.track:2d}. {media.title}') for media in track_list]
num_tracks = input('Scrobble up to track [auto]: ')
num_tracks = len(track_list) if num_tracks == '' else int(num_tracks)

for media in track_list:
    if start_time + media.length > time() or int(media.track) > num_tracks:
        break
    lastfm.scrobble(artist=media.artist, title=media.title, album=media.album, timestamp=start_time)
    print(f'{media.artist} - {media.title}')
    start_time += media.length

sleep(5)
