import os
import json
import subprocess
import contextlib

import yt_dlp.utils
from yt_dlp import YoutubeDL
from phrydy import MediaFile
from media import is_media_file
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!


class AddTags(yt_dlp.postprocessor.PostProcessor):
    """Add tags to a post-processed file."""

    def __init__(self, album, artist):
        super().__init__()
        self.album = album
        self.artist = artist
        self.files = []

    def run(self, info):
        """After a file has finished downloading, tag it with album artist and album."""
        filename = info['filepath']
        _, name = os.path.split(filename)
        self.files.append(name)
        track = int(name.split(' ')[0])  # 01 Title.ext
        media = MediaFile(filename)
        media.albumartist = self.artist
        media.album = self.album
        media.track = track
        title = media.title
        if ' - ' in title:
            # deal with titles like "Artist - Title" or "Title - Artist"
            # (but can't automatically tell, so check first whether artist is defined
            first, last = title.split(' - ', maxsplit=1)
            if first == self.artist:
                title = last
            elif last == self.artist:
                title = first
        pos = title.find('Official')
        if pos > 1:  # e.g. Song Name (Official Audio)
            title = title[:pos].rstrip(' (-[')  # remove suffices like " - Official" and " [Official]" as well
        title = title.strip('"')  # "Song Name" -> Song Name
        media.title = title
        self.to_screen(f'Tagging {name} with {self.artist = }, {self.album = }, {track=}, {title=}')
        media.save()
        return [], info


def reject_large(info_dict):
    """Don't download songs longer than 15 minutes."""
    if info_dict.get('duration', 0) < 900:
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
    # folder = r'K:\Music\_Copied\YouTube\Elbow\The Take Off and Landing of Everything'
    # files = os.listdir(folder)
    # for i in range(1):
    toast = ''
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

        def reject_existing(info_dict, *args, incomplete=False):
            """Reject any videos matching existing files in the folder."""
            if video_title := info_dict.get('title', ''):
                for artist, title in artist_titles:
                    if artist and title and artist in video_title and title in video_title:
                        message = f"Already got {artist} - {title} - skipping {video_title}"
                        print(message)
                        return message
            return reject_large(info_dict)  # also reject anything that's too long

        info = open(info_file).read()
        # if 'playlists' in info:  # playlists page - not really using this at the mo
        #     if not get_playlist_info(info):
        #         continue
        #     get_youtube_playlists()  # restart, since directory structure has changed
        #     break
        if '{' in info:
            playlist = json.loads(info)  # dict with keys: url, artist, album
        elif info.startswith(('https://www.youtube.com/', 'https://music.youtube.com/')):  # just the url?
            playlist = {'url': info.strip()}
        else:
            continue  # can't process info
        # print(playlist)

        subfolders = folder.split(os.path.sep)
        album_name = subfolders[-1]  # folder name
        artist = subfolders[-2]  # parent folder name
        if artist in ('Emma', 'Jess', 'YouTube'):  # compilation
            artist = 'Various Artists'
        if ' - ' in album_name:  # artist - album
            artist, album_name = album_name.split(' - ', 1)
        add_tags = AddTags(playlist.get('album', album_name), playlist.get('artist', artist))
        options = {'download_archive': 'download-archive.txt',  # keep track of previously-downloaded videos
                   'force_write_download_archive': True,
                   # 'no-warnings': True,
                   # 'verbose': True,
                   'quiet': True,
                   # 'max_downloads': 1,  # for testing
                   'ignoreerrors': True, 'writethumbnail': True, 'format': 'bestaudio/best',
                   # reverse order for channels (otherwise new videos will always be track 1)
                   'playlistreverse': 'channel' in playlist['url'],
                   # https://github.com/yt-dlp/yt-dlp#output-template
                   'outtmpl': "%(playlist_index)02d %(title)s.%(ext)s",
                   # 'parse_metadata': 'title:%(artist)s - %(album)s',
                   'postprocessors': [{'key': 'FFmpegExtractAudio'}, {'key': 'FFmpegMetadata'},
                                      {'key': 'EmbedThumbnail'}
                                      ],
                   'match_filter': reject_existing, 'progress_hooks': [show_status]}
        with (contextlib.suppress(yt_dlp.utils.MaxDownloadsReached)):  # don't give an error when limit reached
            with YoutubeDL(options) as downloader:
                downloader.add_post_processor(add_tags, when='after_move')
                downloader.download([playlist['url']])
                new_files = add_tags.files
                if new_files:
                    toast += f'{album_name}: ' + \
                             (f'{len(new_files)} new files\n' if len(new_files) > 1 else f'{new_files[0]}\n')

    if toast:
        Pushbullet(api_key).push_note('🎼 Get YouTube playlists', toast)


def get_playlist_info(url):
    """Given a playlist page, download all the playlists contained there, creating sub-folders if necessary."""
    # TODO before use: rewrite this for yt_dlp. Maybe using --print-to-file option?
    # It would be useful to use a different delimiter other than '.' here - but that doesn't seem to work
    output = subprocess.run(['yt-dlp', '-i', '--extract-audio',
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
    # test()
