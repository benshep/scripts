import contextlib
import os
import re
from math import log10
import phrydy  # for media file tagging
import mediafile
import pylast
import json  # to save data
import shutil
from dateutil.relativedelta import relativedelta  # for adding months to dates

import folders
import media
from lastfm import lastfm  # contains secrets, so don't show them here
from datetime import datetime, timedelta
from collections import OrderedDict
from send2trash import send2trash
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!

import socket
from folders import user_profile

test_mode = False  # don't change anything!


def human_format(num, precision=0):
    """Convert a number into a human-readable format, with k, M, G, T suffixes for
    thousands, millions, billions, trillions respectively."""
    mag = log10(abs(num)) if num else 0  # zero magnitude when num == 0
    precision += max(0, int(-23 - mag))  # add more precision for very tiny numbers: 1.23e-28 => 0.0001y
    mag = max(-8, min(8, mag // 3))  # clip within limits of SI prefixes
    si_prefixes = dict(zip(range(-8, 9), 'y,z,a,f,p,n,µ,m,,k,M,G,T,P,E,Z,Y'.split(',')))
    return f'{num / 10 ** (3 * mag):.{precision}f}{si_prefixes[mag]}'


def match(a: str, b: str):
    """Case-insensitive string comparison."""
    return (a or '').lower() == (b or '').lower()  # replace None with blank string


class Album:
    def __init__(self, artist, title, folder, date, size, track_count):
        self.artist = artist
        self.title = title
        self.folder = folder
        self.date = date
        self.size = size
        self.track_count = track_count
        self.my_listens = self.global_listens = self.age_score = self.listen_score = self.popularity_score = 0

    def get_total_score(self):
        return self.age_score + self.listen_score + self.popularity_score

    def toast(self):
        max_score = max(self.age_score, self.listen_score, self.popularity_score)
        if self.age_score == max_score:
            icon = '🌟'
            suffix = datetime.fromtimestamp(self.date).strftime('%b %Y')
        elif self.listen_score == max_score:
            icon = '🔥'
            suffix = f'{self.my_listens:.0f} plays'
        else:
            icon = '🌍'
            suffix = f'{human_format(self.global_listens)} global plays'
        return f'{icon} {self.artist} - {self.title}, {suffix}'


def folder_size(folder):
    """Return the size of a folder under the user's home directory."""
    return sum(sum(os.path.getsize(os.path.join(folder_name, file)) for file in file_list)
               for folder_name, _, file_list in os.walk(os.path.join(user_profile, folder)))


def update_phone_music():
    """Deleted listened-to radio files, and fill up the music folder to capacity."""
    return check_radio_files(get_scrobbled_titles(lastfm.get_user('ning')))


def rename_folder(old):
    """Add or remove a # character from the end of a folder name.
    If the new folder exists, copy everything from the old to the new folder."""
    new = old.rstrip('#') if old.endswith('#') else f'{old}#'
    os.makedirs(new, exist_ok=True)
    # maybe it got moved in the meantime by a sync operation, so ignore 'not found' errors
    with contextlib.suppress(FileNotFoundError):
        for filename in os.listdir(old):
            os.replace(os.path.join(old, filename), os.path.join(new, filename))
        os.rmdir(old)


def json_load_if_exists(filename):
    """Read in JSON data if the file exists, else an empty dict."""
    return json.load(open(filename)) if os.path.exists(filename) else {}


def get_artists(music_folder):
    """Return a dict containing artists and their most similar artists."""
    root_len = len(music_folder) + 1
    os.chdir(music_folder)
    exclude_prefixes = tuple(open('not_cd_folders.txt').read().split('\n'))[1:]  # first is _Copied which is OK
    similar_artists = json_load_if_exists('similar_artists.json')
    artist_files = json_load_if_exists('artist_files.json')
    socket.setdefaulttimeout(2)  # in case of a slow network!
    for i, (folder, _, file_list) in enumerate(os.walk(music_folder)):
        name = folder[root_len:]
        if name.startswith(exclude_prefixes):
            continue
        if i % 10 == 0:
            cols = shutil.get_terminal_size().columns
            print(name + ' ' * (cols - len(name)), end='\r')  # keep on same line
        # use all files in the folder to detect the oldest...
        file_list = [os.path.join(folder, file) for file in file_list]
        # ...but filter this down to media files to look for tags
        media_files = list(filter(media.is_media_file, file_list))
        for file in media_files:
            tags = phrydy.MediaFile(file)
            if not tags.artist:
                continue
            short_file = file[root_len:]
            file_and_length = (short_file, int(tags.length))
            for artist in tags.artist.split(', '):
                if artist in artist_files:
                    if file_and_length not in artist_files[artist]:
                        # file not listed - add it
                        artist_files[artist].append(file_and_length)
                else:
                    artist_files[artist] = [file_and_length]
            json.dump(artist_files, open('artist_files.json', 'w'))

    for artist in artist_files.keys():
        if artist not in similar_artists:
            try:
                similar = [similar_artist.item.name for similar_artist in
                           lastfm.get_artist(artist).get_similar()
                           if similar_artist.item.name in artist_files]
                similar_artists[artist] = similar
                json.dump(similar_artists, open('similar_artists.json', 'w'))
            except (pylast.WSError, pylast.MalformedResponseError, pylast.NetworkError):
                # artist not found or timeout
                continue
    print('')


def get_albums(user, music_folder):
    """Return a dict representing albums in the music folder."""
    # Find Last.fm top albums. Weight is number of tracks played. Third list item will be number of tracks per album.
    top_albums = OrderedDict((f'{album.item.artist.name} - {album.item.title}'.lower(), [None, int(album.weight), 1])
                             for album in user.get_top_albums(limit=300))
    # search through music folders - get all the most recent ones
    root_len = len(music_folder) + 1
    os.chdir(music_folder)
    exclude_prefixes = tuple(open('not_cd_folders.txt').read().split('\n'))
    albums = []
    socket.setdefaulttimeout(2)  # in case of a slow network!
    line_len = 0
    for folder, _, file_list in os.walk(music_folder):
        # use all files in the folder to detect the oldest...
        file_list = [os.path.join(folder, file) for file in file_list]
        # ...but filter this down to media files to look for tags
        media_files = list(filter(media.is_media_file, file_list))
        artist, title = get_album_info(media_files)
        if artist is None:
            continue

        name = folder[root_len:]
        # Valid album names: Athlete - Tourist, Elastica\The Menace, The Best Of Bowie
        name_excluded = name.startswith(exclude_prefixes)
        if not name_excluded and media.is_album_folder(name) and file_list:
            oldest = min(os.path.getmtime(file) for file in file_list)
            oldest = min(oldest, os.path.getmtime(folder), os.path.getctime(folder))
            total_size = sum(os.path.getsize(file) for file in file_list)
            album = Album(artist, title, folder, oldest, total_size, len(file_list))
            albums.append(album)
            album_name = f'{artist} - {title}'.lower()
            if album_name in top_albums.keys():  # is it in the top albums? store a reference to it
                album.my_listens = top_albums[album_name][1] / album.track_count
                top_albums[album_name][0] = folder
                top_albums[album_name][2] = len(media_files)
            # Get the global popularity of each album, to give 'classic' albums a boost in the list
            # This requires one network request per album so is a bit slow. Just set to 1 to disable.
            try:
                album.global_listens = lastfm.get_album(artist, title).get_playcount() / album.track_count
            except (pylast.MalformedResponseError, pylast.WSError, pylast.NetworkError):
                # API issue, or network timeout (we deliberately set the timeout to a small value)
                album.global_listens = 1
            if len(albums) % 10 == 0:
                output = f'{album.artist} - {album.title}: {album.my_listens:.0f}; {human_format(album.global_listens)}'
                output += (line_len - len(output)) * ' '  # pad to length of previous output
                line_len = len(output)
                print(output, end='\r')  # keep on same line
    print('')  # next line
    socket.setdefaulttimeout(None)  # back to normal behaviour
    oldest = min(album.date for album in albums)
    newest = max(album.date for album in albums)
    most_plays_me = max(album.my_listens for album in albums)
    most_plays_global = max(album.global_listens for album in albums)
    for album in albums:
        album.age_score = (album.date - oldest) ** 2 / (newest - oldest) ** 2
        album.listen_score = album.my_listens / most_plays_me
        album.popularity_score = album.global_listens / most_plays_global
    print('')
    return sorted(albums, key=lambda album: album.get_total_score(), reverse=True)


def get_album_info(media_files):
    for file in media_files:
        try:
            tags = phrydy.MediaFile(file)
            break
        except mediafile.FileTypeError:
            print(f'No media info for {file}')
    else:  # no media info for any (or empty list)
        return None, None
    # use album artist (if available) so we can compare 'Various Artist' albums
    artist = tags.albumartist or tags.artist
    title = str('' or tags.album)  # use empty string if album is None
    return artist, title


def check_radio_files(scrobbled_titles):
    """Find and remove recently-played tracks from the Radio folder. Fix missing titles in tags."""
    scrobbled_radio = []  # list of played radio files to delete
    first_unheard = ''  # first file in the list that hasn't been played
    extra_played_count = 0  # more files that have been played, after one that apparently hasn't
    os.chdir(folders.radio_folder)
    radio_files = os.listdir()
    print(f'{len(radio_files)} files in folder')
    # loop over radio files - first check if they've been scrobbled, then try to correct tags where titles aren't set
    file_count = 0
    # min_date = None
    bump_dates = []
    toast = ''
    # total_hours = 0
    which_artist = {}
    for file in sorted(radio_files):
        if not media.is_media_file(file):
            continue
        try:
            file_date = datetime.strptime(file[:10], '%Y-%m-%d')
        except ValueError:
            continue  # not a date-based filename

        file_count += 1
        # min_date = min_date or file_date  # set to first one
        # weeks = (file_date - min_date).days // 7

        tags = phrydy.MediaFile(file)
        tags_changed = False
        # total_hours += tags.length / 3600

        track_title = media.artist_title(tags)
        if track_title in scrobbled_titles:
            print(f'[{file_count}] ✔ {track_title}')
            if not first_unheard:  # only found played files so far
                scrobbled_radio.append(file)  # possibly delete this one
            else:
                extra_played_count += 1  # don't delete, but flag as played for later
        elif not first_unheard:
            print(f'[{file_count}] ❌ {track_title}')
            first_unheard = file  # not played this one - flag it if it's the first in the list that's not been played
        elif file_count % 10 == 0:  # bump up first tracks of later-inserted albums to this point
            bump_date = file_date.replace(day=1) + relativedelta(months=1)  # first day of next month - for consistency
            if bump_date not in bump_dates:
                bump_dates.append(file_date)  # but maintain a list, don't bump everything here

        # unhelpful titles - set it from the filename instead
        if tags.title in ('', 'Untitled Episode', None) \
                or (tags.title.lower() == tags.title and '_' in tags.title and ' ' not in tags.title):
            print(f'[{file_count}] Set {file} title to {file[11:-4]}')
            tags.title = file[11:-4]  # the bit between the date and the extension (assumes 3-char ext)
            tags_changed = True

        if not tags.albumartist:
            if artist := tags.artist or which_artist.get(tags.album):
                print(f'[{file_count}] Set {file} album artist to {artist}' +
                      (' (guessed from album)' if tags.artist is None else ''))
                tags.artist = artist
                tags.albumartist = artist
                tags_changed = True

        # sometimes tracks get an album name but not an artist - try to determine what it would be from existing files
        if tags.album in which_artist:
            if which_artist[tags.album] is not None and which_artist[tags.album] != tags.artist:
                which_artist[tags.album] = None  # mismatch
                print(f'[{file_count}] (multiple artists) - {tags.album}')
        else:  # not seen this album before
            which_artist[tags.album] = tags.artist
            print(f'[{file_count}] {tags.artist} - {tags.album}')
            # is it a new album fairly far down the list?
            if ('(bumped)' not in file  # don't bump anything more than once
                    and not tags_changed  # don't rename if we want to save tags - might have weird results
                    and bump_dates and bump_dates[0] + timedelta(weeks=4) < file_date):  # not worth bumping <4 weeks
                new_date = bump_dates.pop(0).strftime("%Y-%m-%d")  # i.e. the next bump date from the list
                toast += f'🔼 {file}\n'
                os.rename(file, f'{new_date} (bumped) {file[11:]}')

        if tags_changed and not test_mode:
            tags.save()

    for file in scrobbled_radio[:-1]:  # don't delete the last one - we might not have finished it
        toast += f'🗑️ {os.path.splitext(file)[0]}\n'
        if not test_mode and os.path.exists(file):
            send2trash(file)
    if extra_played_count > 2 and first_unheard:  # flag if something is getting 'stuck' at the top of the list
        toast += f'🚩 {first_unheard}: not played but {extra_played_count} after\n'
    # toast += f'📻 {file_count} files; {weeks} weeks; {total_hours:.0f} hours\n'
    return toast


def get_scrobbled_titles(lastfm_user, limit=999) -> list[str]:
    # get recently played tracks (as reported by Last.fm)
    return [f'{track.track.artist.name} - {track.track.title}'.lower() for track in
            (lastfm_user.get_recent_tracks(limit=limit))]  # limit <= 999


def get_data_from_music_update(push):
    """Given a Pushbullet toast, return the date and the number of files, weeks, hours."""
    date = datetime.fromtimestamp(push['created'])
    status_line = next(line for line in push['body'].split('\n') if line.startswith('📻'))
    match = re.match(r'📻 (\d+) files; (\d+) weeks; (\d+) hours', status_line)
    files, weeks, hours = match.group(1, 2, 3)
    return date, int(files), int(weeks), int(hours)


def check_radio_hours_added():
    """Fetch the last 60 days of toasts, and determine how many hours were added to the radio files on average."""
    pb = Pushbullet(api_key)
    start = datetime.now() - timedelta(days=60)
    pushes = pb.get_pushes(modified_after=start.timestamp())
    music_updates = [push for push in pushes if push.get('title') == '🎧 Update phone music']

    last = music_updates[0]  # reverse chronological order
    first = music_updates[-1]
    last_date, _, _, last_hours = get_data_from_music_update(last)
    first_date, _, _, first_hours = get_data_from_music_update(first)
    hours_per_week = 7 * (last_hours - first_hours) / (last_date - first_date).days
    print(f'Since {first_date.strftime("%d/%m/%Y")}: {hours_per_week=:+.1f}')

    # for push in music_updates:
    #     created_date = datetime.fromtimestamp(push['created']).strftime('%d/%m/%Y %H:%M')
    #     try:
    #         status_line = next(line for line in push['body'].split('\n') if line.startswith('📻'))
    #     except StopIteration:
    #         continue
    #     print(created_date, status_line[2:], sep='; ')


def bump_down():
    """Bump an album down the list by increasing the date in the filename."""
    os.chdir(folders.radio_folder)
    radio_files = os.listdir()
    next_date = None
    for file in sorted(radio_files, reverse=True):  # get most recent first
        if not media.is_media_file(file):
            continue
        try:
            file_date = datetime.strptime(file[:10], '%Y-%m-%d')
        except ValueError:
            continue  # not a date-based filename

        tags = phrydy.MediaFile(file)
        if tags.album is None or "The Hitchhiker’s Guide to the Galaxy: The Complete Radio Series" not in tags.album:
            continue

        if not next_date:
            next_date = file_date
            print('Last file', file, next_date)
        else:
            next_date -= timedelta(days=6)
            os.rename(file, next_date.strftime('%Y-%m-%d') + file[10:])


if __name__ == '__main__':
    # get_artists(os.path.join(user_profile, 'Music'))
    # bump_down()
    print(update_phone_music())
