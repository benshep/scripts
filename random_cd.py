#!python3
# -*- coding: utf-8 -*-
import os
from random import randrange
from lastfm import lastfm  # contains secrets, so don't show them here
from phrydy import MediaFile  # to get media data
from time import time

from media import is_media_file, is_album_folder


def pick_random_cd():
    music_folder = os.path.join(os.environ['UserProfile'], 'Music')
    exclude_prefixes = tuple(open(os.path.join(music_folder, 'not_cd_folders.txt')).read().split('\n'))
    root_len = len(music_folder) + 1
    cd_folders = []

    for folder, folder_list, file_list in os.walk(music_folder):
        name = folder[root_len:]
        if not name.startswith(exclude_prefixes) and is_album_folder(name):
            cd_folders.append(name)

    while True:
        folder = cd_folders.pop(randrange(len(cd_folders)))  # remove from list
        os.system(f'title {folder.replace("&", "^&")}')  # set title of window
        print(folder)
        start_time = int(time())
        os.chdir(os.path.join(music_folder, folder))
        track_list = sorted([MediaFile(f) for f in os.listdir() if is_media_file(f)], key=lambda media: int(media.track))
        [print(f'{media.track:2d}. {media.title}') for media in track_list]
        num_tracks = input('Scrobble up to track [auto]: ')
        num_tracks = len(track_list) if num_tracks == '' else int(num_tracks)

        scrobbled = False
        for media in track_list:
            if start_time + media.length > time() or int(media.track) > num_tracks:
                break
            lastfm.scrobble(artist=media.artist, title=media.title, album=media.album, timestamp=start_time)
            scrobbled = True
            print(f'{media.artist} - {media.title}')
            start_time += media.length
        if scrobbled:
            os.startfile('.')  # open Explorer in folder
        print('\n')


if __name__ == '__main__':
    pick_random_cd()
