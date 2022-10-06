import os
import json
import subprocess
from youtube_dl import YoutubeDL
from phrydy import MediaFile


class BadDownload(Exception):
    pass


class TagAdder:
    """Add tags to a post-processed file."""
    def __init__(self, album, artist):
        self.album = album
        self.artist = artist

    def debug(self, msg):
        """If a file has finished downloading, add the relevant tags."""
        # print(msg)
        # msg looks like [ffmpeg] Adding metadata to '1 Lord Franklin.opus'
        prefix = '[ffmpeg] Adding metadata to '
        if not msg.startswith(prefix):
            return
        filename = msg[len(prefix):].strip("'")
        media = MediaFile(filename)
        media.albumartist = self.artist
        media.album = self.album
        media.track = int(filename[:2])
        basename, _ = os.path.splitext(filename)
        try:
            art_filename = next(f'{basename}.{ext}' for ext in ('jpg', 'webp') if os.path.exists(f'{basename}.{ext}'))
            media.art = open(art_filename, 'rb').read()
            print(f'Saved thumbnail from {art_filename}')
            os.remove(art_filename)
        except StopIteration:
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
        print(f'{progress["_eta_str"]} {progress["filename"]}')#, end='\r')


def get_youtube_playlists():
    user_profile = os.environ['UserProfile']
    music_folder = os.path.join(user_profile, 'Music')
    info_file = 'download.txt'  # info file contained in each folder
    for folder, _, files in os.walk(music_folder):
        if info_file not in files:
            continue
        print(folder)
        os.chdir(folder)
        info = open(info_file).read()
        if '{' in info:
            playlist = json.loads(info)  # dict with keys: url, artist, album
        elif 'playlists' in info:  # playlists page
            if not get_playlist_info(info):
                continue
            get_youtube_playlists()  # restart, since directory structure has changed
            break
        elif info.startswith('https://www.youtube.com/'):  # just the url?
            playlist = {'url': info.strip()}
        else:
            continue  # can't process info
        print(playlist)

        tag_adder = TagAdder(playlist.get('album', os.path.split(folder)[-1]),  # default to folder name
                             playlist.get('artist', 'Various Artists'))
        options = {'download_archive': 'download-archive.txt',  # keep track of previously-downloaded videos
                   # reverse order for channels (otherwise new videos will always be track 1)
                   'ignoreerrors': True,
                   'writethumbnail': True,
                   'playlistreverse': 'channel' in playlist['url'],
                   'format': 'bestaudio/best',
                   # https://github.com/ytdl-org/youtube-dl/blob/master/README.md#output-template
                   'outtmpl': "%(playlist_index)02d %(title)s.%(ext)s",
                   'postprocessors': [{'key': 'FFmpegExtractAudio'}, {'key': 'FFmpegMetadata'},
                                      # {'key': 'EmbedThumbnail'}  # not supported on Opus yet - do it ourselves
                                      ],
                   'logger': tag_adder, 'match_filter': reject_large, 'progress_hooks': [show_status]}
        YoutubeDL(options).download([playlist['url']])


def get_playlist_info(url):
    """Given a playlist page, download all the playlists contained there, creating subdirs if necessary."""
    output = subprocess.run(['youtube-dl', '-i', '--extract-audio',
                             '--output', '"%(playlist_id)s.%(playlist)s.%(ext)s"', '--get-filename', url],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = output.stdout.decode('utf-8').split('\n')
    lines = filter(None, lines)  # remove blanks
    split = [line.split('.') for line in lines]
    playlists = {list_id: name for list_id, name, _ in split}  # remove duplicates, ignore extensions
    got_new = False
    for list_id, name in playlists.items():
        if not os.path.exists(name):
            os.mkdir(name)
            os.chdir(name)
            open('download.txt', 'w').write('https://www.youtube.com/playlist?list=' + list_id.lstrip('#'))
            print(f'Created folder for {name}')
            os.chdir('..')
            got_new = True
    return got_new


if __name__ == '__main__':
    get_youtube_playlists()
