#!python3
# -*- coding: utf-8 -*-
import os
import phrydy  # to get media data
from lastfm import lastfm
import random
from datetime import datetime
from shutil import copy2  # to copy files
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!
from send2trash import send2trash

user_folder = os.environ['UserProfile']
music_folder = os.path.join(user_folder, 'Music')
copy_folder = os.path.join(user_folder, 'Commute')
media_exts = ('.mp3', '.m4a', '.ogg', '.flac', '.opus')
min_length = 55
max_length = 70
illegal_chars = str.maketrans({char: None for char in '*?/\\<>:|"'})

# get recently played tracks (as reported by Last.fm)
played_tracks = lastfm.get_user('ning').get_recent_tracks(limit=200)
scrobbled_titles = [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]

# delete the oldest if it's been played (assumes files have yyyy-mm-dd prefix)
folder_walk = list(os.walk(copy_folder))
hidden_files = os.path.join(copy_folder, '.')  # don't count hidden folders (like .stfolder)
oldest = min(root for root, dirs, files in folder_walk if not root.startswith(hidden_files) and root != copy_folder)
print(f'Oldest dir: {oldest}')
played_count = 0
for file in sorted(os.listdir(oldest)):
    media_info = phrydy.MediaFile(os.path.join(oldest, file))
    print(f'{media_info.artist} - {media_info.title}'.lower())
    if f'{media_info.artist} - {media_info.title}'.lower() in scrobbled_titles:
        played_count += 1
print(f'Played {played_count} tracks')

if played_count > 3:
    send2trash(oldest)
    toast = '❌ ' + oldest[len(copy_folder)+12:]  # skip yyyy-mm-dd bit for readability
else:
    print('Not ready to copy new album.')
    exit()

albums = {}
i = 0
os.chdir(music_folder)
exclude_prefixes = tuple(open('not_cd_folders.txt').read().split('\n')[2:])
for current_folder, folder_list, file_list in os.walk(music_folder):
    if current_folder[len(music_folder) + 1:].startswith(exclude_prefixes):
        continue

    i += 1
    if i % 30 == 0:
        print(current_folder)
    folder_name = os.path.join(music_folder, current_folder)
    for file in file_list:
        filename = os.path.join(folder_name, file)
        name, ext = os.path.splitext(file)
        if ext.lower() in media_exts:
            try:
                tags = phrydy.MediaFile(filename)
            except:
                print(f'No media info for {file_list[0]}')
            # use album artist (if available) so we can compare 'Various Artist' albums
            artist = tags.albumartist if tags.albumartist else tags.artist
            album_name = tags.album
            duration = tags.length / 60  # in minutes
            if duration is None:
                duration = os.path.getsize(filename) * 8 / (1024 * 128 * 60)  # some buggy mp3s - assume 128kbps
            key = (folder_name, artist, album_name)
            if key in albums.keys():
                album_file_list = albums[key]
            else:
                albums[key] = album_file_list = {}
            album_file_list[file] = duration

# remove albums with only one track
print(albums)
for key, file_list in list(albums.items()):
    if len(file_list) <= 1:
        albums.pop(key)


def find_with_length(minimum, maximum):
    try:
        return next(album for album, files in random.sample(list(albums.items()), len(albums)) if minimum <= sum(files.values()) <= maximum)
    except StopIteration:
        return None


def copy_album(album, file_list, existing_folder=None):
    os.chdir(copy_folder)
    folder, artist_name, title = album
    no_artist = (None, '', 'Various', 'Various Artists')
    album_filename = (title if artist_name in no_artist else f'{artist_name} - {title}'.translate(illegal_chars)) if title else os.path.basename(folder)
    if existing_folder is None:
        folder_name = datetime.strftime(datetime.now(), '%Y-%m-%d ') + album_filename
        os.mkdir(folder_name)
        n = 0
    else:
        folder_name = existing_folder + '; ' + album_filename
        os.rename(existing_folder, folder_name)
        n = len(os.listdir(folder_name))
    os.chdir(folder_name)
    i = 0
    for file in file_list.keys():
        i += 1
        media_info = phrydy.MediaFile(os.path.join(folder, file))
        try:
            copy_filename = f'{int(media_info.track) + n:02d} {media_info.title}{ext}'.translate(illegal_chars)
        except ValueError:  # e.g. couldn't get track name
            copy_filename = f'{i:02d} {file}'  # fall back to original name
        copy2(os.path.join(folder, file), copy_filename)
    return folder_name


while True:
    key = random.sample(list(albums.keys()), 1)[0]
    file_list = albums.pop(key)
    duration = sum(file_list.values())
    if min_length <= duration <= max_length:
        folder_name = copy_album(key, file_list)
        break
    elif duration < min_length:
        second_key = find_with_length(min_length - duration, max_length - duration)
        if second_key is None:
            continue
        second_file_list = albums.pop(second_key)
        duration += sum(second_file_list.values())
        folder_name = copy_album(second_key, second_file_list, copy_album(key, file_list))  # do first one first!
        break

os.chdir(copy_folder)
os.rename(folder_name, f'{folder_name} [{duration:.0f}]')

toast += '\n✔  ️' + folder_name[11:]  # skip [YYYY-MM-DD] part

Pushbullet(api_key).push_note('🎵 Commute Music', toast)
