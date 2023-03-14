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
    cd_folders = find_folders(cd_mode, music_folder)

    while True:
        folder = cd_folders.pop(randrange(len(cd_folders)))  # remove from list
        path = os.path.join(music_folder, folder)
        if not os.path.exists(path):
            continue
        os.chdir(path)
        files = os.listdir()
        if cd_mode and 'nocd' in files:
            continue  # don't have the CD
        track_list = sorted([MediaFile(f) for f in files if is_media_file(f)],
                            key=lambda media: int(media.track) if media.track else 0)
        if not track_list:
            continue
        os.system(f'title {folder.replace("&", "^&")}')  # set title of window
        print(folder)
        [print(f'{media.track:2}.' if media.track else '  .', media.title) for media in track_list]
        if cd_mode:
            scrobble_cd(track_list)
            print('\n')
        else:
            music_bee_exe = r'C:\Program Files (x86)\MusicBee\MusicBee.exe'
            # open first, then queue the rest - otherwise order will be wrong
            verb = '/Play'
            for track in track_list:
                subprocess.Popen([music_bee_exe, verb, os.path.join(path, track.path)])
                verb = '/QueueNext'
                sleep(2)
            break


def scrobble_cd(track_list):
    """Scrobble the tracks on last.fm."""
    start_time = int(time())
    num_tracks = input("Scrobble up to track [auto], or 'n' for no CD: ")
    if num_tracks and 'nocd'.startswith(num_tracks):
        # record the lack of CD, so we don't have to ask again ('n' is sufficient)
        open('nocd', 'w').close()
        return
    num_tracks = len(track_list) if num_tracks == '' else int(num_tracks)
    for media in track_list:
        if start_time + media.length > time() or (media.track and int(media.track) > num_tracks):
            break
        lastfm.scrobble(artist=media.artist, title=media.title, album=media.album, timestamp=start_time)
        print(f'{media.artist} - {media.title}')
        start_time += media.length


def find_folders(cd_mode, music_folder):
    """Walk through music folders on the local drive and return a list."""
    exclude_prefixes = tuple(open(os.path.join(music_folder, 'not_cd_folders.txt')).read().split('\n'))
    if not cd_mode:
        exclude_prefixes = exclude_prefixes[1:]  # first is _Copied
    root_len = len(music_folder) + 1
    cd_folders = []
    for folder, folder_list, file_list in os.walk(music_folder):
        name = folder[root_len:]
        if not name.startswith(exclude_prefixes) and is_album_folder(name):
            cd_folders.append(name)
    return cd_folders


if __name__ == '__main__':
    pick_random_cd(node() == 'DLAST0023')
