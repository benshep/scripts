import os
import requests
import json
import subprocess
import media
import phrydy
from time import sleep
from send2trash import send2trash
from folders import music_folder


def explicit_songs(files):
    """Look for songs with 'explicit' lyrics, as flagged by iTunes.
    Rename them with an [Explicit] suffix on the filename."""
    for file in files:
        if not media.is_media_file(file) or '[Explicit]' in file:
            continue
        artist_title = media.artist_title(file, separator=' ')
        params = {'country': 'gb', 'media': 'music', 'entity': 'song', 'term': artist_title}
        sleep(6)  # limit to 10 calls per minute
        try:
            itunes_data = json.loads(requests.get('https://itunes.apple.com/search', params=params).text)
        except Exception:
            print(f"Couldn't fetch data for {file}")
            continue
        for result in itunes_data['results']:
            itunes_artist_title = f"{result['artistName']} {result['trackName']}".lower()
            if itunes_artist_title == artist_title:
                if result['trackExplicitness'] == 'explicit':
                    basename, ext = os.path.splitext(file)
                    print(f'--- Renaming {file}')
                    os.rename(file, f'{basename} [Explicit]{ext}')
                break
        else:
            print(f'No data for {artist_title}')


def fix_tags(fix_function):
    """Loop through music folder and use the supplied fix_function to fix tags."""
    os.chdir(music_folder)
    log_file = f'{__file__}.log'
    if os.path.exists(log_file):
        up_to = open(log_file, encoding='utf-8').read().strip()
        started = False
    else:
        up_to = None
        started = True

    for folder, _, files in os.walk(music_folder):
        if folder == up_to:  # got up to here
            started = True
        elif not started:
            continue
        # print(folder)
        open(log_file, 'w', encoding='utf-8').write(folder)
        os.chdir(folder)
        # files = list(filter(media.is_media_file, files))
        files = list(filter(lambda file: file.lower().endswith(('.jpeg', '.jpg')), files))
        fix_function(files, folder)
        # sleep(2)


def apostrophes(files):
    """Look for Opus files tagged with bad apostrophes (’), and replace them with normal ones (')."""
    for file in files:
        basename, ext = os.path.splitext(file)
        if ext.lower() != '.opus':
            continue
        tags = phrydy.MediaFile(file)
        for tag_name in tags.readable_fields():
            if tag_name == 'art':
                continue
            tag_text = getattr(tags, tag_name)
            if not isinstance(tag_text, str) or '’' not in tag_text:
                continue
            setattr(tags, tag_name, tag_text.replace('’', "'"))
            tags.save()
            print(file, tag_name, tag_text)


def album_artist(files):
    """Replace a blank album artist field with something populated from the artist field."""
    if all(phrydy.MediaFile(file).albumartist for file in files):
        return  # nothing to do
    artists = [phrydy.MediaFile(file).artist for file in files]
    unique_artists = set(artists)
    if len(unique_artists) == 1:  # only one for all of them - apply this to album
        artist = artists[0]
        print(f'Setting album artist to {artist} for {len(files)} files starting with {files[0]}')
        for file in files:
            tags = phrydy.MediaFile(file)
            if not tags.albumartist:
                tags.albumartist = artist
                tags.save()
    else:
        print(unique_artists)


def find_320k_mp3s(files):
    """Convert MP3 files with 320kbps bitrate to Opus with 96kbps."""
    for file in files:
        old_size = os.path.getsize(file)
        basename, ext = os.path.splitext(file)
        if ext.lower() != '.mp3':
            continue
        tags = phrydy.MediaFile(file)
        if tags.bitrate >= 320000:
            opus_file = f"{basename}.opus"
            command = ['ffmpeg.exe', '-i', file, '-acodec', 'libopus', opus_file]
            subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            new_size = os.path.getsize(opus_file)
            print(f'{old_size / 1024**2:.02f}', f'{new_size / 1024**2:.02f}', file, sep='\t')
            send2trash(file)


def delete_low_res_jpgs(files, folder):
    if len(files) < 2:
        return
    print(f'<p>{folder}</p>')
    print(*[f'<img src="{folder}\\{file}">\n' for file in files])


if __name__ == '__main__':
    fix_tags(delete_low_res_jpgs)
