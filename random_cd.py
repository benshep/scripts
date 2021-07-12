#!python3
# -*- coding: utf-8 -*-
import os
from random import randrange
from lastfm import lastfm  # contains secrets, so don't show them here
from phrydy import MediaFile  # to get media data
from time import time

music_folder = os.path.join(os.environ['UserProfile'], 'Music')
exclude_prefixes = tuple(open(os.path.join(music_folder, 'not_cd_folders.txt')).read().split('\n'))
media_exts = ('.mp3', '.m4a', '.ogg', '.flac', '.opus')
root_len = len(music_folder) + 1
cd_folders = []

for folder, folder_list, file_list in os.walk(music_folder):
    name = folder[root_len:]
    if not name.startswith(exclude_prefixes) and (' - ' in name or os.path.sep in name or 'best of' in name.lower()):
        cd_folders.append(name)

while True:
    folder = cd_folders.pop(randrange(len(cd_folders)))  # remove from list
    os.system(f'title {folder.replace("&", "^&")}')  # set title of window
    print(folder)
    start_time = int(time())
    os.chdir(os.path.join(music_folder, folder))
    track_list = sorted([MediaFile(f) for f in os.listdir() if f.lower().endswith(media_exts)], key=lambda media: int(media.track))
    [print(f'{media.track:2d}. {media.title}') for media in track_list]
    num_tracks = input('Scrobble up to track [auto]: ')
    num_tracks = len(track_list) if num_tracks == '' else int(num_tracks)

    for media in track_list:
        if start_time + media.length > time() or int(media.track) > num_tracks:
            break
        lastfm.scrobble(artist=media.artist, title=media.title, album=media.album, timestamp=start_time)
        print(f'{media.artist} - {media.title}')
        start_time += media.length
    print('\n')
