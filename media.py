import os
import phrydy
# Functions for working with media files


def is_media_file(filename: str):
    """Return True if the filename ends with a known media file extension."""
    return filename.lower().endswith(('.mp3', '.m4a', '.ogg', '.flac', '.opus', '.wma'))


def artist_title(file):
    """Return {artist} - {title} string for a given file, converted to lowercase for easy comparison.
    Pass file as a filename or a MediaFile object from phrydy."""
    media_info = phrydy.MediaFile(file) if isinstance(file, str) else file
    return f'{media_info.artist} - {media_info.title}'.lower()


def is_album_folder(name: str):
    """Returns True if the given name looks like an album folder."""
    return ' - ' in name or os.path.sep in name or 'best of' in name.lower()
