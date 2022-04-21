#!python3
# -*- coding: utf-8 -*-
import os
from math import log10
import phrydy  # for media file tagging
import pylast

import media
from lastfm import lastfm  # contains secrets, so don't show them here
from datetime import datetime
from collections import OrderedDict
from send2trash import send2trash
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!

import socket

# REWRITE:
# Database class to store music
# add_file(filename): scan file and add to database
#
# first walk through music folder
# for each file:
# (album, album artist, folder) is key
# store file size, mtime, track number, duration too
# remove short 'albums' with 1 or 2 tracks
#
# for each album:
# get total size, duration, number of tracks
# get my play count
# get earliest last modified date
#
# remove recently-played albums
# delete folders from Commute with recently-played albums
# copy (or link?) albums of given length to Commute and 40 minutes
# remove albums that are in Commute and 40 minutes
#
# now create links for Music for phone folder
# don't assign global score yet - just use a mid-value (0.5)
# work from highest to lowest scoring, add up total size, set threshold
# for albums around the threshold, check global plays
# need to repeat process to fine-tune?

test_mode = False  # don't change anything!
user_profile = os.environ['UserProfile']


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
    user = lastfm.get_user('ning')
    toast = check_radio_files(user)

    # update size of all shared phone folders
    used_total = sum(folder_size(folder) for folder in ['40 minutes', 'Commute', 'Nokia 3.4', 'Radio'])

    GB = 1024 ** 3
    sd_capacity = (32 - 4) * GB  # leave a bit of space
    max_size = sd_capacity - used_total
    print(f'\nSpace for {max_size / GB:.1f} GB of music')

    music_folder = os.path.join(user_profile, 'Music')
    albums = get_albums(user, music_folder)

    total_size = 0
    os.chdir(music_folder)
    root_len = len(music_folder) + 1
    # Instead of linking, add a # to the end of folders NOT to sync
    for album in albums:  # breaks out when total_size > max_size
        # recently played? if so, don't link to it after all (to increase turnover)
        # if len(set(track.track.title for track in played_tracks if match(track.album, album.title) and (
        #         match(album.artist, track.track.artist.name) or 'Various' in album.artist))) >= 0.5 * album.track_count:
        #     continue
        total_size += album.size
        name = album.folder[root_len:]
        excluded = name.endswith('#')
        if total_size > max_size:  # already done everything we can fit - exclude everything else
            if not excluded:
                rename_folder(name)
                toast += f'🗑️ {name}\n'
        elif excluded:  # was previously excluded
            rename_folder(name)
            toast += album.toast() + '\n'

    if toast:
        print(toast)
        if not test_mode:
            Pushbullet(api_key).push_note('🎧 Update phone music', toast)


def rename_folder(old):
    """Add or remove a # character from the end of a folder name.
    If the new folder exists, copy everything from the old to the new folder."""
    new = old.rstrip('#') if old.endswith('#') else f'{old}#'
    os.makedirs(new, exist_ok=True)
    try:
        for filename in os.listdir(old):
            os.replace(os.path.join(old, filename), os.path.join(new, filename))
        os.rmdir(old)
    except FileNotFoundError:  # maybe it got moved in the meantime by a sync operation
        pass


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
            if len(albums) % 30 == 0:
                print(f'{album.artist} - {album.title}: {album.my_listens:.0f}; {human_format(album.global_listens)}')
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
        except phrydy.mediafile.FileTypeError:
            print(f'No media info for {file}')
    else:  # no media info for any (or empty list)
        return None, None
    # use album artist (if available) so we can compare 'Various Artist' albums
    artist = tags.albumartist or tags.artist
    title = str('' or tags.album)  # use empty string if album is None
    return artist, title


def check_radio_files(lastfm_user):
    """Find and remove recently-played tracks from the Radio folder. Fix missing titles in tags."""
    # get recently played tracks (as reported by Last.fm)
    played_tracks = lastfm_user.get_recent_tracks(limit=400)
    scrobbled_titles = [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]
    scrobbled_radio = []
    os.chdir(os.path.join(user_profile, 'Radio'))
    radio_files = os.listdir()
    # loop over radio files - first check if they've been scrobbled, then try to correct tags where titles aren't set
    checking_scrobbles = True
    file_count = 0
    min_date = None
    total_hours = 0
    for file in sorted(radio_files):
        try:
            file_date = datetime.strptime(file[:10], '%Y-%m-%d')
        except ValueError:
            continue  # not a date-based filename

        file_count += 1
        min_date = min_date or file_date  # set to first one
        weeks = (file_date - min_date).days // 7

        tags = phrydy.MediaFile(file)
        tags_changed = False
        total_hours += tags.length / 3600
        if checking_scrobbles:
            track_title = media.artist_title(tags)
            if track_title.lower() in scrobbled_titles:
                print(f'Found: {track_title}')
                scrobbled_radio.append(file)
            else:
                print(f'Not found: {track_title}')
                checking_scrobbles = False  # stop here - don't keep searching
        if tags.title in ('', 'Untitled Episode', None):
            print(f'Set {file} title to {file[11:-4]}')
            tags.title = file[11:-4]  # the bit between the date and the extension (assumes 3-char ext)
            tags_changed = True
        if not tags.albumartist:
            print(f'Set {file} album artist to {tags.artist}')
            tags.albumartist = tags.artist
            tags_changed = True
        if tags_changed and not test_mode:
            tags.save()
    toast = ''
    print('\nTo delete:')
    for file in scrobbled_radio[:-1]:  # don't delete the last one - we might not have finished it
        toast += f'🗑️ {os.path.splitext(file)[0]}\n'
        print(file)
        if not test_mode and os.path.exists(file):
            send2trash(file)
    toast += f'📻 {file_count} files; {weeks} weeks; {total_hours:.0f} hours\n'
    return toast


if __name__ == '__main__':
    update_phone_music()
