#!python3
# -*- coding: utf-8 -*-
import os
from pymediainfo import MediaInfo  # to get media data
import pickle  # to save state
from shutil import get_terminal_size  # to copy files
from folders import music_folder

music_folders = [music_folder, r'\\Ksv86254dell.dl.ac.uk\d\My Music']
media_exts = ('.mp3', '.m4a', '.ogg', '.flac', '.opus')
db_filename = 'python_albums.db'
list_filename = '60-minutes.txt'
min_length = 55 * 60 * 1000
max_length = 70 * 60 * 1000
illegal_chars = '*?/\\<>:|"'


def is_image(path):
    root, extension = os.path.splitext(path)
    return extension.lower() in ('.png', '.jpg', '.jpeg', '.bmp')


try:
    db_file = open(db_filename, 'rb')
    data = pickle.load(db_file)
    db_file.close()
except (FileNotFoundError, EOFError):
    data = {}

albums = data[0] if data else {}
folder_mtime = data[1] if len(data) > 1 else {}

print('Checking for updated folders')
term_width = get_terminal_size(fallback=(80, 30)).columns - 1
albums_60 = [tuple(line.split('\t')) for line in open(list_filename).read().splitlines()]
updated_albums = set()
for music_folder in music_folders:
    for current_folder, folder_list, file_list in os.walk(music_folder):
        print('\r' + (current_folder[:term_width]).ljust(term_width), end='\r')
        folder_name = os.path.join(music_folder, current_folder)
        mtime = max([os.path.getmtime(os.path.join(folder_name, file)) for file in file_list]) if file_list else 0
        if folder_name not in folder_mtime.keys() or folder_mtime[folder_name] < mtime:  # modified since last time
            print(current_folder, len(file_list))
            folder_mtime[folder_name] = mtime
            for file in file_list:
                filename = os.path.join(folder_name, file)
                name, ext = os.path.splitext(file)
                if ext.lower() in media_exts:
                    media_info = MediaInfo.parse(filename)
                    artist = media_info.tracks[0].album_performer
                    if artist is None:
                        artist = media_info.tracks[0].performer  # this is a fudge - might have unexpected results
                    album_name = media_info.tracks[0].album
                    duration = media_info.tracks[0].duration  # in ms
                    if duration is None:
                        print(file)
                        duration = 0  # some buggy mp3s - need a fix for this
                    key = (folder_name, artist, album_name)
                    updated_albums.add(key)
                    if key in albums.keys():
                        album_file_list = albums[key]
                    else:
                        albums[key] = album_file_list = {}
                    album_file_list[file] = duration

# updated_albums = {album: sum(albums[album].values()) for album in updated_albums}
# print(updated_albums)
# exit()

f = open(list_filename, 'a', encoding='utf-8')
for album in updated_albums:
    file_list = albums[album]
    duration = sum(file_list.values())
    if min_length < duration < max_length and album not in albums_60:
        f.write('{}\t{}\t{}\n'.format(*album))
f.close()

print()
pickle.dump((albums, folder_mtime), open(db_filename, 'wb'))

#  do this the first time to create a new list
# albums_60 = [album for album, file_list in albums.items() if min_length < sum(file_list.values()) < max_length]
# random.shuffle(albums_60)
# f = open(list_filename, 'w', encoding='utf-8')
# for album in albums_60:
#     f.write('{}\t{}\t{}\n'.format(*album))
# f.close()
