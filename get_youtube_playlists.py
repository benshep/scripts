import os
import json
import subprocess
import contextlib

import yt_dlp.utils
from yt_dlp import YoutubeDL
from phrydy import MediaFile
from PIL import Image
from io import BytesIO
from media import is_media_file
from send2trash import send2trash
from folders import music_folder

def crop_cover(media):
    """Deal with album covers that have been turned into widescreen thumbnails."""
    if not media.art:
        print(f'No cover in {media.filename}')
        return
    cover = Image.open(BytesIO(media.art))
    width, height = cover.size
    border_size = (width - height) // 2
    if border_size < 10:  # close enough to square
        print(f'Cover in {media.filename} is square {cover.size}')
        return
    left_border = cover.crop((0, 0, border_size - 10, height))  # left, upper, right, lower
    right_border = cover.crop((width - border_size + 10, 0, width, height))  # left, upper, right, lower
    if left_border.getcolors(10) and right_border.getcolors(10):  # both return not None if there are <=10 colours
        square_thumb = cover.crop((border_size, 0, width - border_size, height))
        data = BytesIO()
        img_format = cover.format
        if media.format == 'AAC' and img_format not in ('PNG', 'JPEG'):
            img_format = 'JPEG'  # otherwise throws an error
        square_thumb.save(data, format=img_format)
        media.art = data.getvalue()
        media.save()
        print(f'Cropped cover in {media.filename} to {square_thumb.size} image')
    else:
        print(f'Cover in {media.filename} is a full image - no borders')


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
        if media.album is not None:
            # hack for EPIC: original album names have saga names too, we don't want to overwrite them
            if self.album not in media.album:
                media.album = self.album
            pos = media.album.find('Official')
            if pos > 1:  # e.g. Album Name (Official Audio)
                media.album = media.album[:pos].rstrip(' (-[')  # remove suffices like " - Official" and " [Official]" as well
        media.track = track
        title = media.title
        if title is not None:
            if ' - ' in title:
                # deal with titles like "Artist - Title" or "Title - Artist"
                # (but can't automatically tell, so check first whether artist is defined)
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
        self.to_screen(f'Tagged {name} with {self.artist = }, {media.album = }, {track=}, {title=}')
        crop_cover(media)
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


def get_youtube_playlists(just_crop_art=False):
    info_file = 'download.txt'  # info file contained in each folder
    archive_file = 'download-archive.txt'
    # folder = r'K:\Music\_Copied\YouTube\Elbow\The Take Off and Landing of Everything'
    # files = os.listdir(folder)
    # for i in range(1):
    toast = ''
    for folder, _, files in os.walk(music_folder):
        # if just_crop_art is selected, look for archive files too
        if info_file not in files and (not just_crop_art or archive_file not in files):
            continue
        print(folder)
        os.chdir(folder)
        artist_titles = []
        for file in files:
            if is_media_file(file):
                tags = MediaFile(file)
                if just_crop_art:
                    crop_cover(tags)
                    continue
                artist_titles.append((tags.artist, tags.title))

        if just_crop_art:
            continue

        def reject_existing(info_dict, *args, incomplete=False):
            """Reject any videos matching existing files in the folder."""
            if video_title := info_dict.get('title', ''):
                for artist, title in artist_titles:
                    if artist and title and artist in video_title and title in video_title:
                        message = f"Already got {artist} - {title} - skipping {video_title}"
                        print(message)
                        return message
            return reject_large(info_dict)  # also reject anything that's too long

        subfolders = folder.split(os.path.sep)
        album_name = subfolders[-1]  # folder name
        artist = subfolders[-2]  # parent folder name
        if artist in ('Emma', 'Jess', 'YouTube'):  # compilation
            artist = 'Various Artists'
        if ' - ' in album_name:  # artist - album
            artist, album_name = album_name.split(' - ', 1)
        download_info = open(info_file).read()
        lines = download_info.splitlines()
        # if 'playlists' in info:  # playlists page - not really using this at the mo
        #     if not get_playlist_info(info):
        #         continue
        #     get_youtube_playlists()  # restart, since directory structure has changed
        #     break
        if '{' in download_info:
            playlist = json.loads(download_info)  # dict with keys: url, artist, album
            lines = [playlist['url']]
        elif lines[0].startswith(('https://www.youtube.com/', 'https://music.youtube.com/')):  # just the url?
            playlist = {}
        else:
            continue  # can't process info
        for url in lines:
            playlist['url'] = url.strip()
            # print(playlist)
            add_tags = AddTags(playlist.get('album', album_name), playlist.get('artist', artist))
            options = {'download_archive': archive_file,  # keep track of previously-downloaded videos
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
                                          {'key': 'EmbedThumbnail'}],
                       'match_filter': reject_existing, 'progress_hooks': [show_status]}
            with (contextlib.suppress(yt_dlp.utils.MaxDownloadsReached)):  # don't give an error when limit reached
                with YoutubeDL(options) as downloader:
                    downloader.add_post_processor(add_tags, when='after_move')
                    error_code = downloader.download([playlist['url']])  # 1 if error occurred, else 0
                    # _Copied folder is for albums not playlists, won't be updated so can delete info file
                    if '_Copied' in folder and not error_code:
                        print(f'Success. Deleting {info_file} from {folder}')
                        send2trash(info_file)
                    new_files = add_tags.files
                    if new_files:
                        toast += f'{album_name}: ' + \
                                 (f'{len(new_files)} new files' if len(new_files) > 1 else f'{new_files[0]}') + \
                                 (' (with errors)\n' if error_code else '\n')

    return toast


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
    print(get_youtube_playlists())
    # test()
