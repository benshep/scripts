#!python3
# -*- coding: utf-8 -*-
import os
from math import log10
from _winapi import CreateJunction
import phrydy  # for media file tagging
import pylast

from lastfm import lastfm  # contains secrets, so don't show them here
from datetime import datetime
from collections import OrderedDict
from send2trash import send2trash
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!


def human_format(num, precision=0):
    """Convert a number into a human-readable format, with k, M, B, T suffixes for
    thousands, millions, billions, trillions respectively."""
    mag = log10(abs(num)) if num else 0  # zero magnitude when num == 0
    precision += max(0, int(-23 - mag))  # add more precision for very tiny numbers: 1.23e-28 => 0.0001y
    mag = max(-8, min(8, mag // 3))  # clip within limits of SI prefixes
    si_prefixes = dict(zip(range(-8, 9), 'y,z,a,f,p,n,µ,m,,k,M,B,T,P,E,Z,Y'.split(',')))  # strictly should be G not B
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


def get_track_title(media):
    return f'{media.artist} - {media.title}'


test_mode = False  # don't change anything!
user_profile = os.environ['UserProfile']

# get recently played tracks (as reported by Last.fm)
user = lastfm.get_user('ning')
played_tracks = user.get_recent_tracks(limit=400)
scrobbled_titles = [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]

scrobbled_radio = []
os.chdir(os.path.join(user_profile, 'Radio'))
radio_files = os.listdir()
# loop over radio files - first check if they've been scrobbled, then try to correct tags where titles aren't set
checking_scrobbles = True
for file in sorted(radio_files):
    try:
        d = datetime.strptime(file[:10], '%Y-%m-%d')
    except ValueError:
        continue  # not a date-based filename

    tags = phrydy.MediaFile(file)
    if checking_scrobbles:
        track_title = get_track_title(tags)
        if track_title.lower() in scrobbled_titles:
            print(f'Found: {track_title}')
            scrobbled_radio.append(file)
        else:
            print(f'Not found: {track_title}')
            checking_scrobbles = False  # stop here - don't keep searching
    else:
        if tags.title in ('', 'Untitled Episode', None):
            print(f'Set {file} title to {file[11:-4]}')
            tags.title = file[11:-4]  # the bit between the date and the extension (assumes 3-char ext)
            if not test_mode:
                tags.save()

toast = ''
print('\nTo delete:')
for file in scrobbled_radio[:-1]:  # don't delete the last one - we might not have finished it
    toast += '🗑️ ' + os.path.splitext(file)[0] + '\n'  # hide the file extension
    print(file)
    if not test_mode:
        send2trash(file)

# update size of radio folder
radio_files = os.listdir()
radio_total = sum([os.path.getsize(file) for file in radio_files])
sd_capacity = 32_006_713_344  # 29.8 GB, as reported by Windows
max_size = sd_capacity * 0.43 - radio_total
print('\nSpace for {:.1f} GB of music'.format(max_size / 1024**3))

music_folder = os.path.join(user_profile, 'Music')
root_len = len(music_folder) + 1

# Find Last.fm top albums. Here weight is number of tracks played. Third list item will be number of tracks per album.
top_albums = OrderedDict((f'{album.item.artist.name} - {album.item.title}'.lower(), [None, int(album.weight), 1])
                         for album in user.get_top_albums(limit=300))

# search through music folders - get all the most recent ones
os.chdir(music_folder)
exclude_prefixes = tuple(open('not_cd_folders.txt').read().split('\n'))
albums = []
for folder, folder_list, file_list in os.walk(music_folder):
    # use all files in the folder to detect the oldest...
    file_list = [os.path.join(folder, file) for file in file_list]
    # ...but filter this down to media files to look for tags
    media_files = [file for file in file_list if file.lower().endswith(('mp3', 'm4a', 'wma', 'opus'))]
    for file in media_files:
        try:
            tags = phrydy.MediaFile(file)
            break
        except phrydy.mediafile.FileTypeError:
            print(f'No media info for {file_list[0]}')
    else:  # no media info for any (or empty list)
        continue
    # use album artist (if available) so we can compare 'Various Artist' albums
    artist = tags.albumartist if tags.albumartist else tags.artist
    if artist is None:
        continue  # can't recognise this file, nothing to do here
    title = str('' or tags.album)  # use empty string if album is None
    name = folder[root_len:]
    # Valid album names: Athlete - Tourist, Elastica\The Menace, The Best Of Bowie
    name_ok = any(part in name.lower() for part in (' - ', os.path.sep, 'best of'))
    if not name.startswith(exclude_prefixes) and name_ok and len(file_list) > 0:
        oldest = min([os.path.getmtime(file) for file in file_list])
        total_size = sum([os.path.getsize(file) for file in file_list])
        album = Album(artist, title, folder, oldest, total_size, len(file_list))
        albums.append(album)
        album_name = (artist + ' - ' + title).lower()
        if album_name in top_albums.keys():  # is it in the top albums? store a reference to it
            album.my_listens = top_albums[album_name][1] / album.track_count
            top_albums[album_name][0] = folder
            top_albums[album_name][2] = len(media_files)
        # Get the global popularity of each album, to give 'classic' albums a boost in the list
        # This requires one network request per album so is a bit slow. Just set to 1 to disable.
        try:
            album.global_listens = lastfm.get_album(artist, title).get_playcount() / album.track_count
        except (pylast.MalformedResponseError, pylast.WSError):  # API issue
            pass
        print(f'{album.artist} - {album.title}: {album.my_listens:.0f}; {human_format(album.global_listens)}')

oldest = min(album.date for album in albums)
newest = max(album.date for album in albums)
most_plays_me = max(album.my_listens for album in albums)
most_plays_global = max(album.global_listens for album in albums)
for album in albums:
    album.age_score = (album.date - oldest)**2 / (newest - oldest)**2
    album.listen_score = album.my_listens / most_plays_me
    album.popularity_score = album.global_listens / most_plays_global

print('')
albums = sorted(albums, key=lambda album: album.get_total_score(), reverse=True)

total_size = 0
link_list = []
get_newest = False
os.chdir(os.path.join(user_profile, 'Music for phone'))
for album in albums:  # breaks out when total_size > max_size
    # recently played? if so, don't link to it after all (to increase turnover)
    if len(set(track.track.title for track in played_tracks if match(track.album, album.title) and (
            match(album.artist, track.track.artist.name) or 'Various' in album.artist))) >= 0.5 * album.track_count:
        continue
    total_size += album.size
    if total_size > max_size:
        break
    name = album.folder[root_len:]
    link_folder = name.replace(os.path.sep, ' - ')
    if not os.path.exists(link_folder):
        if not test_mode:
            CreateJunction(album.folder, link_folder)
        toast += album.toast() + '\n'
    link_list.append(link_folder)

# remove any links that aren't in the list
for folder in os.listdir():
    if os.path.isdir(folder) and folder not in link_list:
        # print(folder)
        toast += '🗑️ ' + folder + '\n'
        if not test_mode:
            os.unlink(folder)

if toast:
    print(toast)
    if not test_mode:
        Pushbullet(api_key).push_note('🎧 Update phone music', toast)
