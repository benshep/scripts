import os
from pathlib import Path
from time import sleep
from phrydy import MediaFile


# Functions for working with media files
media_exts = ('.mp3', '.m4a', '.ogg', '.flac', '.opus', '.wma')


def is_media_file(filename: str | Path) -> bool:
    """Return True if the filename ends with a known media file extension."""
    return filename.lower().endswith(media_exts) if isinstance(filename, str) else filename.suffix.lower() in media_exts


def artist_title(file: str | MediaFile | Path, separator: str = ' - ') -> str:
    """Return {artist} - {title} string for a given file, converted to lowercase for easy comparison.
    Pass file as a filename or a MediaFile object from phrydy."""
    media_info = file if isinstance(file, MediaFile) else MediaFile(file)
    artist_title.counter += 1
    return f'{media_info.artist}{separator}{media_info.title}'.lower()
artist_title.counter = 0

def is_album_folder(name: Path):
    """Returns True if the given name looks like an album folder."""
    return ' - ' in name.name or len(name.parts) > 1 or 'best of' in name.name.lower()


def disc_track(media: MediaFile, include_disc: bool = False) -> int:
    """Return track number of a MediaFile for sorting.
    :param media: MediaFile to return the track number from.
    :param include_disc: if True and a disc number exists, the returned track number will be 100 * disc + track.
    """
    track_number = int(media.track or 0)
    disc_number = int(media.disc or 0)
    return int(include_disc) * disc_number * 100 + track_number


if __name__ == '__main__':
    os.chdir(r'C:\Users\bjs54\Music\_Soundtracks\The No. 1 Sci-Fi Album')
    for file in os.listdir():
        if is_media_file(file):
            print(disc_track(MediaFile(file), include_disc=True), file)
