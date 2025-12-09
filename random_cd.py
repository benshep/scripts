import os
import subprocess
from platform import node
from random import randrange
from time import time, sleep

from phrydy import MediaFile  # to get media data

import media
from folders import music_folder
from lastfm import lastfm  # contains secrets, so don't show them here


def pick_random_cd(got_cds: bool = True):
    """Pick a random album from the music folder.
    If got_cds is True, prompt to put on CDs (and scrobble to last.fm afterwards), otherwise play on MusicBee."""
    cd_folders = find_folders()

    while True:
        folder = cd_folders.pop(randrange(len(cd_folders)))  # remove from list
        path = os.path.join(music_folder, folder)
        if not os.path.exists(path):
            continue
        os.chdir(path)
        files = os.listdir()
        # if got_cds and 'nocd' in files:
        #     continue  # don't have the CD
        track_list = sorted([MediaFile(f) for f in files if media.is_media_file(f)],
                            key=lambda track: media.disc_track(track, include_disc=True))
        if not track_list:
            continue
        os.system(f'title {folder.replace("&", "^&")}')  # set title of window
        print(folder)
        for track in track_list:
            print(f'{track.track:2}.' if track.track else '  .', track.title)
        if got_cds and scrobble_cd(track_list):  # returns False if prompt answered with 'nocd'
            print('\n')
        else:  # no CD: open music player instead
            music_bee_exe = r'C:\Program Files (x86)\MusicBee\MusicBee.exe'
            # open first, then queue the rest - otherwise order will be wrong
            verb = '/Play'
            for track in track_list:
                subprocess.Popen([music_bee_exe, verb, os.path.join(path, track.path)])
                verb = '/QueueNext'
                sleep(2)
            break  # don't want another one straight away!


def scrobble_cd(track_list: list[MediaFile]) -> bool:
    """Scrobble the tracks on last.fm. Returns False if we get 'no CD' response."""
    start_time = int(time())
    num_tracks = input("Scrobble up to track [auto], or 'n' for no CD: ")
    if num_tracks and 'nocd'.startswith(num_tracks):
        # record the lack of CD, so we don't have to ask again ('n' is sufficient)
        open('nocd', 'w').close()
        return False
    num_tracks = len(track_list) if num_tracks == '' else int(num_tracks)
    for track in track_list:
        if start_time + track.length > time() or (track.track and int(track.track) > num_tracks):
            break
        lastfm.scrobble(artist=track.artist, title=track.title, album=track.album, timestamp=start_time)
        print(f'{track.artist} - {track.title}')
        start_time += track.length
    return True


def find_folders() -> list[str]:
    """Walk through music folders on the local drive and return a list."""
    not_cd_folders_file = os.path.join(music_folder, 'not_cd_folders.txt')
    exclude_prefixes = tuple(open(not_cd_folders_file).read().split('\n')) \
        if os.path.exists(not_cd_folders_file) else ()
    # if not cd_mode:
    #     exclude_prefixes = exclude_prefixes[1:]  # first is _Copied
    root_len = len(music_folder) + 1
    cd_folders = []
    for folder, folder_list, file_list in os.walk(music_folder):
        name = folder[root_len:]
        if not name.startswith(exclude_prefixes) and media.is_album_folder(name):
            cd_folders.append(name)
    return cd_folders


if __name__ == '__main__':
    pick_random_cd(node() == 'DLAST0023')
