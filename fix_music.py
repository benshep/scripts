import os
import requests
import json
import media
import phrydy
from time import sleep


def check_explicit_songs():
    """Loop through music folder looking for songs with 'explicit' lyrics, as flagged by iTunes.
    Rename them with an [Explicit] suffix on the filename."""
    user_profile = os.environ['UserProfile']
    music_folder = os.path.join(user_profile, 'Music')
    os.chdir(music_folder)
    log_file = f'{__file__}.log'
    up_to = open(log_file, encoding='utf-8').read().strip()
    started = False

    for folder, _, files in os.walk(music_folder):
        if folder == up_to:  # got up to here
            started = True
        elif not started:
            continue
        print(folder)
        open(log_file, 'w', encoding='utf-8').write(folder)
        os.chdir(folder)
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


def fix_apostrophes():
    """Loop through music folder looking for Opus files tagged with bad apostrophes (’),
    and replace them with normal ones (')."""
    user_profile = os.environ['UserProfile']
    music_folder = os.path.join(user_profile, 'Music')
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


if __name__ == '__main__':
    fix_apostrophes()
