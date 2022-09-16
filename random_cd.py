#!python3
# -*- coding: utf-8 -*-
import os
import subprocess
from random import randrange
from lastfm import lastfm  # contains secrets, so don't show them here
from phrydy import MediaFile  # to get media data
from time import time, sleep
from platform import node

from media import is_media_file, is_album_folder


def pick_random_cd(cd_mode=True):
    music_folder = os.path.join(os.environ['UserProfile'], 'Music')
    exclude_prefixes = tuple(open(os.path.join(music_folder, 'not_cd_folders.txt')).read().split('\n'))
    if not cd_mode:
        exclude_prefixes = exclude_prefixes[1:]  # first is _Copied
    root_len = len(music_folder) + 1
    cd_folders = []

    for folder, folder_list, file_list in os.walk(music_folder):
        name = folder[root_len:]
        if not name.startswith(exclude_prefixes) and is_album_folder(name):
            cd_folders.append(name)

    while True:
        folder = cd_folders.pop(randrange(len(cd_folders)))  # remove from list
        path = os.path.join(music_folder, folder)
        if not os.path.exists(path):
            continue
        start_time = int(time())
        os.chdir(path)
        files = os.listdir()
        nocd = 'nocd'
        if cd_mode and (nocd in files or any(is_opus(file) for file in files)):
            continue  # already ripped to Opus
        track_list = sorted([MediaFile(f) for f in files if is_media_file(f)], key=lambda media: int(media.track))
        if not track_list:
            continue
        os.system(f'title {folder.replace("&", "^&")}')  # set title of window
        print(folder)
        [print(f'{media.track:2d}. {media.title}') for media in track_list]
        if cd_mode:
            num_tracks = input('Scrobble up to track [auto]: ')
            if nocd.startswith(num_tracks):  # record the lack of CD, so we don't have to ask again ('n' is sufficient)
                open(nocd, 'w').close()
                continue
            num_tracks = len(track_list) if num_tracks == '' else int(num_tracks)

            scrobbled = False
            for media in track_list:
                if start_time + media.length > time() or int(media.track) > num_tracks:
                    break
                lastfm.scrobble(artist=media.artist, title=media.title, album=media.album, timestamp=start_time)
                scrobbled = True
                print(f'{media.artist} - {media.title}')
                start_time += media.length
            # if this was a CD and not in Opus format, open in Explorer in preparation for re-ripping
            if scrobbled:
                # if any(is_opus(media.path) for media in track_list):
                #     print('Already ripped to Opus format')
                # else:
                os.startfile('.')  # open Explorer in folder
            print('\n')
        else:
            subprocess.call([r'C:\Program Files (x86)\MusicBee\MusicBee.exe'] +
                            [os.path.join(path, media.path) for media in track_list])
            sleep(10)
            break


def is_opus(filename):
    """Returns True if the given filename has an Opus extension."""
    return os.path.splitext(filename)[1].lower() == '.opus'


if __name__ == '__main__':
    pick_random_cd(node() == 'DLAST0023')
