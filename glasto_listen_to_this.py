import os
from contextlib import suppress
from subprocess import check_output
import pylast
from lastfm import lastfm
from folders import radio_folder
from tools import remove_bad_chars

glastonbury_iplayer_url = 'https://www.bbc.co.uk/iplayer/episodes/b007r6vx/glastonbury'
want_songs = True  # looking for individual songs? False means whole sets


def listen_to_this():
    """Fetch a list of Glastonbury performances from iPlayer, and select the most relevant for my listening habits."""
    my_top_artists_names = set(artist.item.name for artist in lastfm.get_user('ning').get_top_artists(limit=200))
    collecting = False
    command = [r'C:\Program Files\get_iplayer\get_iplayer.cmd', glastonbury_iplayer_url,
               '--pid-recursive-list', '--tracklist']
    for line in check_output(command, encoding='ISO-8859-1').splitlines():
        if line == 'Episodes:':  # start of programme list
            collecting = True  # start with the next line
            continue
        if not collecting or ': ' not in line:
            continue
        series, rest = line.split(': ', maxsplit=1)
        if series == 'INFO':
            break  # end of programmes
        programme, _, pid = rest.split(', ', maxsplit=2)
        parts = programme.split(' - ')
        # some are "2025 - Artist - Title" i.e. just one song - looking for these?
        event = parts[0]
        if event in ('2025', 'Live Sets (2025)') and len(parts) == (3 if want_songs else 2):
            performer_name = parts[1]
            if performer_name in my_top_artists_names:
                print(pid, event, performer_name, parts[2] if want_songs else '')
            else:
                try:
                    similar = lastfm.get_artist(performer_name).get_similar(limit=20)
                except pylast.WSError:  # couldn't find artist
                    similar = []
                if overlap := set(artist.item.name for artist in similar) & my_top_artists_names:
                    print(pid, event, performer_name, '- ' + parts[2] if want_songs else '', '- similar to', ', '.join(overlap))


def split_by_track():
    """Run through audio files for whole sets and split into individual tracks."""
    os.chdir(os.path.join(radio_folder, 'Glastonbury'))
    for file in os.listdir():
        if not file.lower().endswith('.m4a'):
            continue
        tracklist_file = file[:-3] + 'tracks.txt'
        if not os.path.exists(tracklist_file):
            continue
        print(tracklist_file)
        command_base = f'ffmpeg -i "{file}" -vn -acodec copy'
        start_time = 0
        title = 'Intro'
        artist = ''
        track_number = 1
        folder = file[:-4]
        with suppress(FileExistsError):
            os.mkdir(folder)
        batch = open(file + '.bat', 'w')
        for section in open(tracklist_file).read().split('\n--------\n')[1:]:  # first section is description
            lines = section.splitlines()
            if len(lines) < 4:  # assume no time code
                continue
            start, artist, new_title, duration = lines
            new_title = new_title.rsplit('(', maxsplit=1)[0].strip()  # remove (Glastonbury 2025) from end
            hours, minutes, seconds = [int(x) for x in start.split(':')]
            new_start = hours * 3600 + minutes * 60 + seconds
            if new_start != start_time:
                track_filename = os.path.join(folder, remove_bad_chars(f'{track_number:02d} {title}.m4a'))
                batch.write(f'{command_base} -ss {start_time} -to {new_start} -metadata title="{title}" '
                            f'-metadata author="{artist}" -metadata track={track_number} "{track_filename}"\n')
                start_time = new_start
                track_number += 1
            title = new_title
        # write out the last track: no end time necessary
        track_filename = os.path.join(folder, remove_bad_chars(f'{track_number:02d} {title}.m4a'))
        batch.write(f'{command_base} -ss {start_time} -metadata title="{title}" '
                    f'-metadata author="{artist}" -metadata track={track_number} "{track_filename}"\n')
    print()


if __name__ == '__main__':
    split_by_track()
