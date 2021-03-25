#!python3
# -*- coding: utf-8 -*-
import os
from _winapi import CreateJunction
import phrydy
from lastfm import lastfm  # contains secrets, so don't show them here
from datetime import datetime
from collections import OrderedDict
from send2trash import send2trash
from contextlib import contextmanager
from win10toast import ToastNotifier  # to show pop-up notification


def get_track_title(media):
    title = media.title
    artist = media.artist
    return f'{artist} - {title}'


# https://gist.github.com/howardhamilton/537e13179489d6896dd3
@contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(previous_dir)


user_profile = os.environ['UserProfile']
music_folder = os.path.join(user_profile, 'Music')
phone_folder = os.path.join(user_profile, 'Music for phone')
radio_folder = os.path.join(user_profile, 'Radio')
commute_folder = os.path.join(user_profile, 'Commute')

# get recently played tracks (as reported by Last.fm)
user = lastfm.get_user('ning')
played_tracks = user.get_recent_tracks(limit=200)
scrobbled_titles = [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]

scrobbled_radio = []
with pushd(radio_folder):
    radio_files = os.listdir()
    # loop over radio files - first check if they've been scrobbled, then try to correct tags where titles aren't set
    checking_scrobbles = True
    for file in sorted(radio_files):
        try:
            d = datetime.strptime(file[:10], '%Y-%m-%d')
        except ValueError:
            continue  # not a date-based filename

        if checking_scrobbles:
            tags = phrydy.MediaFile(file)
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
                tags.save()

print('\nTo delete:')
for file in scrobbled_radio[:-1]:  # don't delete the last one - we might not have finished it
    print(file)
    send2trash(os.path.join(radio_folder, file))

# update size of radio folder
radio_files = os.listdir(radio_folder)
radio_total = sum([os.path.getsize(os.path.join(radio_folder, file)) for file in radio_files])
sd_capacity = 32_006_713_344  # 29.8 GB, as reported by Windows
max_size = sd_capacity * 0.43 - radio_total
print('\nSpace for {:.1f} GB of music'.format(max_size / 1024**3))

root_len = len(music_folder) + 1
cd_folders = OrderedDict()

# Find Last.fm top albums. Here weight is number of tracks played. Third list item will be number of tracks per album.
top_albums = OrderedDict((f'{a.item.artist.name} - {a.item.title}'.lower(), [None, int(a.weight), 1])
                         for a in user.get_top_albums(limit=300))

# search through music folders - get all the most recent ones
exclude_prefixes = tuple(open(os.path.join(music_folder, 'not_cd_folders.txt')).read().split('\n'))
for folder, folder_list, file_list in os.walk(music_folder):
    # use all files in the folder to detect the oldest...
    file_list = [os.path.join(folder, file) for file in file_list]
    # ...but filter this down to media files to look for tags
    media_files = [file for file in file_list if file.lower().endswith(('mp3', 'm4a', 'wma'))]
    if len(media_files) == 0:
        continue
    try:
        tags = phrydy.MediaFile(media_files[0])
    except phrydy.mediafile.FileTypeError:
        print(f'No media info for {file_list[0]}')
    # use album artist (if available) so we can compare 'Various Artist' albums
    try:
        album_name = ((tags.albumartist if tags.albumartist else tags.artist) + ' - ' + tags.album).lower()
    except TypeError:  # can't concatenate None with string - probably a track with no album name listed
        pass  # print(f'Tag error for {tags.albumartist}, {tags.artist}, {tags.album} ({file_list[0]})')
    # print(album_name)
    if album_name in top_albums.keys():  # is it in the top albums? store a reference to it
        top_albums[album_name][0] = folder
        top_albums[album_name][2] = len(media_files)
    name = folder[root_len:]
    name_ok = ' - ' in name or os.path.sep in name or 'best of' in name.lower()
    if not name.startswith(exclude_prefixes) and name_ok and len(file_list) > 0:
        oldest = min([os.path.getmtime(file) for file in file_list])
        total_size = sum([os.path.getsize(file) for file in file_list])
        cd_folders[folder] = (oldest, total_size)

# Sort by (tracks played) / (tracks on album) i.e. approx number of times album has been played
# This means albums with a lot of tracks don't get undue prominence
top_albums = OrderedDict(sorted(top_albums.items(), key=lambda x: x[1][1] / x[1][2], reverse=True))
print('\nNo album folder for:\n', '\n'.join(name for name, folder in top_albums.items() if folder is None))
cd_folders = OrderedDict(sorted(cd_folders.items(), key=lambda x: x[1][0], reverse=True))  # sort on age of oldest file

total_size = 0
link_list = []
get_newest = False
print('\nAdding links to music folder:')
links_added = []
while True:  # breaks out when total_size > max_size
    get_newest = not get_newest  # alternate between newest and top
    if get_newest:
        folder = next(iter(cd_folders.keys()))
        # print(f'New: {folder}')
    else:
        # get the next from the top albums list
        # we might have already used it though - loop through until we find one that's not been used (and isn't None)
        in_list = False
        while not in_list:
            folder, tracks_played, n_tracks = top_albums.pop(next(iter(top_albums.keys())))  # remove 1st one from list
            in_list = folder in cd_folders.keys()
            # print(f'Top ({tracks_played / n_tracks:.1f}): {in_list} {folder}')
    oldest, size = cd_folders.pop(folder)  # remove from the list
    total_size += size
    if total_size > max_size:
        break
    name = folder[root_len:]
    link_folder = name.replace(os.path.sep, ' - ')
    try:
        CreateJunction(folder, os.path.join(phone_folder, link_folder))
        print(link_folder)
        links_added.append(('🌟 ' if get_newest else '🔥 ') + link_folder)
    except FileExistsError:  # already created this link
        pass
    link_list.append(link_folder)

# print(len(link_list))
print('\nRemoving:')
# remove any links that aren't in the list
# print(len(os.listdir(phone_folder)))
links_removed = []
for folder in os.listdir(phone_folder):
    full_path = os.path.join(phone_folder, folder)
    if os.path.isdir(full_path) and folder not in link_list:
        print(folder)
        links_removed.append('🗑️ ' + folder)
        os.unlink(full_path)

toast = ''
if len(links_added) > 0:
    toast += '\n'.join(links_added) + '\n'
if len(links_removed) > 0:
    toast += '\n'.join(links_removed)
if toast > '':
    ToastNotifier().show_toast('Update phone music', toast, duration=30)
