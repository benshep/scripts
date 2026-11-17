import os
import subprocess
from shutil import get_terminal_size
from platform import node
from random import randrange
from time import time, sleep
from pathlib import Path
from contextlib import suppress

import wcwidth
from phrydy import MediaFile  # to get media data

import media
from folders import music_folder
from lastfm import lastfm  # contains secrets, so don't show them here

on_windows = os.name == 'nt'

def pick_random_cd(got_cds: bool = True):
    """Pick a random album from the music folder.
    If got_cds is True, prompt to put on CDs (and scrobble to last.fm afterwards), otherwise play on MusicBee."""
    cd_folders = find_folders()

    while cd_folders:
        folder = cd_folders.pop(randrange(len(cd_folders)))  # remove from list
        if not folder.exists():
            continue
        files = list(folder.glob('*.*'))
        relative_folder = folder.relative_to(music_folder)
        got_this_cd = got_cds and relative_folder.parts[0] != '_Copied' and 'nocd' not in [file.name for file in files]
        track_list = sorted([MediaFile(f) for f in files if media.is_media_file(f)],
                            key=lambda track: media.disc_track(track, include_disc=True))
        if not track_list:
            print('No tracks found for', relative_folder)
            continue
        if on_windows:
            os.system(f'title {folder.stem.replace("&", "^&")}')  # set title of window
        print(folder)
        for track in track_list:
            print(number_title(track))
        if not (got_this_cd and scrobble_cd(track_list)):  # returns False if prompt answered with 'nocd'
            print('Playing via device')
            if on_windows:
                music_bee_exe = r'C:\Program Files (x86)\MusicBee\MusicBee.exe'
                # open first, then queue the rest - otherwise order will be wrong
                verb = '/Play'
                for track in track_list:
                    subprocess.Popen([music_bee_exe, verb, track.path])
                    verb = '/QueueNext'
                    sleep(2)
                break
            else:
                output = subprocess.check_output(['bluetoothctl', 'devices', 'Connected']).decode('utf-8')
                if 'SoundCore' not in output:
                    print('No Bluetooth audio output device')
                    break
                with suppress(subprocess.CalledProcessError):
                    subprocess.check_output(['mocp', '-S'])  # ensure server running
                subprocess.call(['mocp', '--clear'])
                for track in track_list:
                    subprocess.call(['mocp', '--append', track.path])
                subprocess.call(['mocp', '--play'])
                while True:
                    response = input('Play/pause = p, next/prev = [ ], blank for new album: ')
                    switch = {'p': '--toggle-pause', '[': '--previous', ']': '--next'}.get(response, None)
                    if switch is not None:
                        subprocess.call(['mocp', switch])
                    else:
                        break
        print('\n')


def number_title(track: MediaFile) -> str:
    """Return the number and title of a track in string form."""
    if track.track:
        return f'{track.track:2}. {track.title}'
    else:
        return f'  . {track.title}'


def scrobble_cd(track_list: list[MediaFile]) -> bool:
    """Scrobble the tracks on last.fm. Returns False if we get 'no CD' response."""
    start_time = int(time())
    num_tracks = input("Scrobble up to track [auto], or 'n' for no CD: ")
    if num_tracks and 'nocd'.startswith(num_tracks):
        # record the lack of CD, so we don't have to ask again ('n' is sufficient)
        open('nocd', 'w').close()
        return False
    num_tracks = len(track_list) if num_tracks == '' else int(num_tracks)
    print(f'\033[{len(track_list) + 2}A')  # move up to start of track listing
    for track in track_list:
        do_scrobble = start_time + track.length <= time() and track.track and int(track.track) <= num_tracks
        if do_scrobble:
            lastfm.scrobble(artist=track.artist, title=track.title, album=track.album, timestamp=start_time)
        print(number_title(track), '✔️' if do_scrobble else '❌')
        start_time += track.length
    return True


def find_folders() -> list[Path]:
    """Walk through music folders on the local drive and return a list."""
    not_cd_folders_file = music_folder / 'not_cd_folders.txt'
    exclude_prefixes = tuple(not_cd_folders_file.read_text().splitlines())[1:] \
        if not_cd_folders_file.exists() else ()
    # if not cd_mode:
    #     exclude_prefixes = exclude_prefixes[1:]  # first is _Copied
    cd_folders = []
    for folder in music_folder.rglob('*/', recurse_symlinks=True):
        relative = folder.relative_to(music_folder)
        if not str(relative).startswith(exclude_prefixes) and media.is_album_folder(relative):
            print(wcwidth.ljust(str(relative), get_terminal_size().columns), end='\r')
            cd_folders.append(folder)
    print(f'Found {len(cd_folders)} folders'.ljust(get_terminal_size().columns))
    return cd_folders


if __name__ == '__main__':
    pick_random_cd(node() != 'DDAST0025')
