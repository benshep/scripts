import os
from collections import namedtuple
from youtube_dl import YoutubeDL
from phrydy import MediaFile


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
        media.save()
        print('Downloaded', filename)

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def get_youtube_playlists():
    Playlist = namedtuple('Playlist', ['folder', 'url', 'artist', 'album'])
    playlists = [Playlist(('Rob Peacock', ), 'https://www.youtube.com/channel/UCbdNnpqhT8VyrsI8GCxYapw',
                          'Rob Peacock', 'YouTube'),
                 Playlist(('_Compilations', 'Emma', 'Good Vibes'), 'https://www.youtube.com/playlist?list=PLpw2OjrHadPUQvEHRKy5Iniw7MNmRMn43',
                          'Various Artists', 'Good Vibes'),
                 Playlist(('_Compilations', 'Emma', 'Me'), 'https://www.youtube.com/playlist?list=PLpw2OjrHadPW9gYyB0GpZkcsXdxEoJ_1R',
                          'Various Artists', 'Me')]
    user_profile = os.environ['UserProfile']
    music_folder = os.path.join(user_profile, 'MusicTest')

    for playlist in playlists:
        folder = os.path.join(music_folder, *playlist.folder)
        os.makedirs(folder, exist_ok=True)
        os.chdir(folder)

        tag_adder = TagAdder(playlist.album, playlist.artist)
        options = {'download_archive': 'download-archive.txt',  # keep track of previously-downloaded videos
                   'playlistreverse': 'channel' in playlist.url,  # reverse order for channels (otherwise new videos will always be track 1)
                   'format': 'bestaudio/best',
                   'outtmpl': "%(playlist_index)02d %(title)s.%(ext)s",  # https://github.com/ytdl-org/youtube-dl/blob/master/README.md#output-template
                   'postprocessors': [{'key': 'FFmpegExtractAudio'}, {'key': 'FFmpegMetadata'}],
                   'logger': tag_adder}
        YoutubeDL(options).download([playlist.url])


if __name__ == '__main__':
    get_youtube_playlists()
