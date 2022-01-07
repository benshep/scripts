import os
import requests
import json
import media
from time import sleep


def check_explicit_songs():
    """Loop through music folder looking for songs with 'explicit' lyrics, as flagged by iTunes.
    Rename them with an [Explicit] suffix on the filename."""
    user_profile = os.environ['UserProfile']
    music_folder = os.path.join(user_profile, 'Music')
    os.chdir(music_folder)

    for folder, _, files in os.walk(music_folder):
        print(folder)
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


if __name__ == '__main__':
    check_explicit_songs()
