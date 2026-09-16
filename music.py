from datetime import timedelta, datetime
from pathlib import Path
from typing import Generator, NamedTuple

from phrydy.mediafile import MediaFile

from folders import music_folder
from media import is_media_file


class AlbumKey(NamedTuple):
    """The key used in album dicts."""
    folder: Path
    """The folder containing the album."""
    artist: str
    """The artist of the album."""
    title: str
    """The title of the album."""

class Album(list):
    """Class representing an album."""
    folder: Path
    """The folder containing the album."""
    artist: str
    """The artist of the album."""
    title: str
    """The title of the album."""
    duration: timedelta
    tracks: list[Path]
    copied: list[datetime]
    modified_time: float

    def __init__(self, folder: MusicFolder, artist: str, title: str):
        super().__init__()
        self.folder = folder
        self.artist = artist
        self.title = title
        self.modified_time = folder.stat().st_mtime
        self.tracks = []
        self.copied = []
        self.duration = timedelta(0)

    def append(self, track: Path):
        """Append an object to the album."""
        self.tracks.append(track)
        self.modified_time = max(track.stat().st_mtime, self.modified_time)

class MusicFolder(Path):
    """Class representing a folder with music files."""

    def albums(self) -> list[Album]:
        """Scan the folder for media files and return albums."""
        album_dict = {}
        for file in self.glob('*.*'):
            if not is_media_file(file):
                continue
            tags = MediaFile(file)
            key = AlbumKey(self, tags.albumartist or tags.artist or None, tags.album)
            album_dict.setdefault(key, []).append(tags)

    def last_modified(self) -> float:
        """Return the most recent of the folder mtime and that of its files."""
        mtimes = [file.stat().st_mtime for file in self.glob('*.*')]
        mtimes.append(self.stat().st_mtime)
        return max(mtimes)


class Library:
    """Class representing a library."""
    files: dict[Path, float]
    folders: dict[MusicFolder, float]
    albums: dict[AlbumKey, Album]

    def __init__(self):
        self.files = {}
        self.folders = {}  # needed?
        self.albums = {}

    def build(self):
        """Perform a scan of the music folder and save the results in the library."""
        for folder in music_folder.glob('**/'):
            added = False
            f = MusicFolder(folder)
            for key, album in f.albums():
                self.albums[key] = album
                added = True
            if added:
                self.folders[f] = f.last_modified()

        # save in persistent storage (e.g. pickle)

    def update(self):
        """Quickly scan the music folder checking for any updates."""
        folders_on_disk = set(music_folder.glob('**/'))
        files_on_disk = set(music_folder.rglob('*.*'))

        # remove any library folders that don't exist any more
        not_on_disk = set(self.files) - files_on_disk
        for key, album in self.albums.items():


        # add any new folders to the library

        # check mtimes for the rest

    def __contains__(self, item: Path | AlbumKey) -> bool:
        """Check if a folder or album exists in the library."""
        return item in self.albums if isinstance(item, AlbumKey) else item in self.folders

    def folder_albums(self, find_folder: MusicFolder) -> dict[AlbumKey, Album]:
        """Return albums in a given folder."""
        return {
            AlbumKey(folder, artist, title): album
            for (folder, artist, title), album in self.albums
            if folder == find_folder
        }

    def random_album(self, min_duration: int | None = None, max_duration: int | None = None,
                     cds_only: bool = False) -> Album:
        """Choose a random album, limited by specified criteria."""
