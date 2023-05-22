import os
import json
import subprocess
import contextlib
from io import BytesIO

import youtube_dl.utils
from youtube_dl import YoutubeDL
from phrydy import MediaFile
from media import is_media_file
from PIL import Image


class BadDownload(Exception):
    pass


class TagAdder:
    """Add tags to a post-processed file."""
    def __init__(self, album, artist):
        self.album = album
        self.artist = artist
        self.files = []

    def debug(self, msg):
        """If a file has finished downloading, add it to the list for tagging later."""
        # msg looks like [ffmpeg] Adding metadata to '1 Lord Franklin.opus'
        prefix = '[ffmpeg] Adding metadata to '
        if not msg.startswith(prefix):
            return
        filename = msg[len(prefix):].strip("'")
        self.files.append(filename)

    def add_tags(self):
        """After all the files have finished downloading, add the tags."""
        for filename in self.files:
            print(f'Tagging {filename} with {self.artist = }, {self.album = }')
            media = MediaFile(filename)
            media.albumartist = self.artist
            media.album = self.album
            media.track = int(filename[:2])
            base, _ = os.path.splitext(filename)
            for ext in ('webp', 'jpg'):
                art_filename = f'{base}.{ext}'
                if os.path.exists(art_filename):
                    if ext == 'webp':  # convert to JPEG since WEBP files can't be embedded in M4A files
                        buffer = BytesIO()
                        Image.open(art_filename).convert('RGB').save(buffer, 'JPEG', optimize=True)
                        image_data = buffer.getvalue()
                        print('Converted thumbnail to JPEG')
                    else:
                        image_data = open(art_filename, 'rb').read()
                    media.art = image_data
                    print(f'Saved thumbnail from {art_filename}')
                    os.remove(art_filename)
                    break
            else:
                print(f'No thumbnail found for {filename}')
            media.save()
            print('Downloaded', filename)

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def reject_large(info_dict):
    """Don't download songs longer than 10 minutes."""
    if info_dict['duration'] < 600:
        return None
    message = f"Too long - skipping {info_dict['title']}"
    print(message)
    return message


def show_status(progress):
    """Show downloading status."""
    if progress['status'] == 'downloading':
        print(f'{progress["_eta_str"]} {progress["filename"]}', end='\r')


def get_youtube_playlists():
    user_profile = os.environ['UserProfile' if os.name == 'nt' else 'HOME']
    music_folder = os.path.join(user_profile, 'Music')
    info_file = 'download.txt'  # info file contained in each folder
    for folder, _, files in os.walk(music_folder):
        if info_file not in files:
            continue
        print(folder)
        os.chdir(folder)
        artist_titles = []
        for file in files:
            if is_media_file(file):
                tags = MediaFile(file)
                artist_titles.append((tags.artist, tags.title))

        def reject_existing(info_dict):
            """Reject any videos matching existing files in the folder."""
            for artist, title in artist_titles:
                video_title = info_dict['title']
                if artist in video_title and title in video_title:
                    message = f"Already got {artist} - {title} - skipping {video_title}"
                    print(message)
                    return message
            return reject_large(info_dict)  # also reject anything that's too long

        info = open(info_file).read()
        if 'playlists' in info:  # playlists page
            if not get_playlist_info(info):
                continue
            get_youtube_playlists()  # restart, since directory structure has changed
            break
        elif '{' in info:
            playlist = json.loads(info)  # dict with keys: url, artist, album
        elif info.startswith('https://www.youtube.com/'):  # just the url?
            playlist = {'url': info.strip()}
        else:
            continue  # can't process info
        print(playlist)

        subfolders = folder.split(os.path.sep)
        album_name = subfolders[-1]  # folder name
        artist = subfolders[-2]  # parent folder name
        if artist in ('Emma', 'Jess', 'YouTube'):  # compilation
            artist = 'Various Artists'
        if ' - ' in album_name:  # artist - album
            artist, album_name = album_name.split(' - ', 1)
        tag_adder = TagAdder(playlist.get('album', album_name), playlist.get('artist', artist))
        options = {'download_archive': 'download-archive.txt',  # keep track of previously-downloaded videos
                   # reverse order for channels (otherwise new videos will always be track 1)
                   # 'max_downloads': 1,  # for testing
                   'ignoreerrors': True,
                   'writethumbnail': True,
                   'playlistreverse': 'channel' in playlist['url'],
                   'format': 'bestaudio/best',
                   # https://github.com/ytdl-org/youtube-dl/blob/master/README.md#output-template
                   'outtmpl': "%(playlist_index)02d %(title)s.%(ext)s",
                   'postprocessors': [{'key': 'FFmpegExtractAudio'}, {'key': 'FFmpegMetadata'},
                                      # {'key': 'EmbedThumbnail'}  # not supported on Opus yet - do it ourselves
                                      ],
                   'logger': tag_adder, 'match_filter': reject_existing, 'progress_hooks': [show_status]}
        with contextlib.suppress(youtube_dl.utils.MaxDownloadsReached):
            YoutubeDL(options).download([playlist['url']])
        # must be after everything's finished
        tag_adder.add_tags()


def get_playlist_info(url):
    """Given a playlist page, download all the playlists contained there, creating subdirs if necessary."""
    # It would be useful to use a different delimiter other than '.' here - but that doesn't seem to work
    output = subprocess.run(['youtube-dl', '-i', '--extract-audio',
                             '--output', '"%(playlist_id)s.%(playlist)s.%(ext)s"', '--get-filename', url],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = output.stdout.decode('utf-8').split('\n')
    lines = filter(None, lines)  # remove blanks
    playlists = {}
    for line in lines:
        # Get the id and the name. We don't care about the extension. Need to take care in case the name contains a '.'
        list_id, rest = line.split('.', 1)
        name, _ = rest.rsplit('.', 1)
        playlists[list_id.lstrip('#')] = name  # each line starts and ends with #, remove it from the id
    got_new = False
    for list_id, name in playlists.items():
        if not os.path.exists(name):
            os.mkdir(name)
            os.chdir(name)
            open('download.txt', 'w').write(f'https://www.youtube.com/playlist?list={list_id}')
            print(f'Created folder for {name}')
            os.chdir('..')
            got_new = True
    return got_new


if __name__ == '__main__':
    get_youtube_playlists()
