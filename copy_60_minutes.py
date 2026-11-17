import asyncio
import os
import random
import re
import tempfile
from collections import Counter
from contextlib import suppress
from datetime import datetime, timedelta
from difflib import get_close_matches
from functools import reduce
from pathlib import Path
from shutil import copy2  # to copy files
from typing import NamedTuple

import phrydy  # to get media data
import wcwidth
from PIL import Image
from progress.bar import Bar, IncrementalBar
from send2trash import send2trash

from folders import music_folder, radio_folder
from lastfm import lastfm
from media import is_media_file, artist_title
from tools import remove_bad_chars

music_folder = music_folder.resolve()  # fix issues with symlinks
copy_log_file = music_folder / 'copied_already.txt'
Album = dict[str, float]

test_mode = False
cross = wcwidth.ljust('❌', 3)
tick = wcwidth.ljust('✔️', 3)


class TerminateTaskGroup(Exception):
    """Exception raised to terminate a task group."""


class Folder(NamedTuple):
    """A folder to copy albums into."""
    address: Path
    """The address of the folder."""
    min_length: int
    """The minimum length in minutes of albums in this folder."""
    max_length: int
    """The maximum length in minutes of albums in this folder."""
    min_count: int
    """The minimum count of albums needed in this folder."""


class AlbumKey(NamedTuple):
    """The key used in album dicts."""
    folder: Path
    """The folder containing the album."""
    artist: str
    """The artist of the album."""
    title: str
    """The title of the album."""

    def __str__(self) -> str:
        # show second-level folder if under _Copied
        # e.g. Pink Floyd - The Division Bell (Emma)
        path = self.relative_path()
        parts = path.parts
        name = f" ({parts[1].strip('#')})" if parts[0] == '_Copied' else ''
        return f'{self.artist} - {self.title} {name}'

    def relative_path(self):
        """Strip the root music folder path from the start of the folder name."""
        return self.folder.relative_to(music_folder)

    def tab_join(self) -> str:
        r"""Output tab-separated folder-artist-title; use / as path separator for cross-platform compatibility."""
        return '\t'.join((self.relative_path().as_posix(), self.artist, self.title))


class Tags(NamedTuple):
    """Selected tags relating to a given media file."""
    folder: Path
    """The folder containing the file."""
    file: Path
    """The filename."""
    artist: str
    """The album artist if available, otherwise the artist."""
    album_title: str
    """The album title."""
    length: float
    """The length of the album in minutes."""


def copy_album(album: AlbumKey, files: Album, copy_root: Path, existing_folder: Path | None = None) -> Path:
    """Copy a given album to the copy folder."""
    if album.title:
        no_artist = album.artist in (None, 'None', '', 'Various', 'Various Artists')
        album_filename = remove_bad_chars(album.title if no_artist else f'{album.artist} - {album.title}')
    else:
        album_filename = album.folder.name
    album_filename = album_filename[:60].strip('. ')  # shorten path names (Windows limit: 260 chars) and remove dots
    if existing_folder:  # copying into an existing folder
        copied_name = Path(f'{existing_folder.name}; {album_filename}')
        if not test_mode:
            copied_name = existing_folder.rename(copied_name)
            n = max(int(file.stem[:2]) for file in copied_name.iterdir())  # highest track number in filename
        else:
            n = 0
    else:  # making a new folder
        copied_name = Path(copy_root / (datetime.strftime(datetime.now(), '%Y-%m-%d ') + album_filename))
        if not test_mode:
            copied_name.mkdir()
        n = 0
    if not test_mode:
        for j, f in enumerate(files.keys(), start=1):
            filename = album.folder / f
            media_info = phrydy.MediaFile(filename)
            try:
                copy_filename = f'{int(media_info.track) + n:02d} {remove_bad_chars(media_info.title)}{filename.suffix}'
            except (ValueError, TypeError):  # e.g. couldn't get track name or number
                copy_filename = f'{j + 1 + n:02d} {f}'  # fall back to original name
            copy2(album.folder / f, copied_name / copy_filename)
        with open(copy_log_file, 'a', encoding='utf-8') as log_handle:
            # don't write the music root folder, and convert '\' to '/' for cross-platform compatibility
            log_handle.write(f'{album.tab_join()}\n')
    return copied_name


def reducible_copy_album(existing_folder: Path, album_spec: tuple[AlbumKey, Album, Path]) -> Path:
    """Version of copy_album that can be passed to functools.reduce for multiple subsequent copy operations."""
    album, files, copy_root = album_spec
    return copy_album(album, files, copy_root, existing_folder)


async def get_tags(folder: Path, file: Path, album: dict, copied_already: set[str],
                   bar: Bar | None = None) -> Tags | None:
    """For a media file specified by the folder and file, return a Tags named tuple."""
    # If there are only one set of tags in the folder, i.e. not a 'misc' folder,
    # and the length in the scanned files is already too long, cancel the rest of the scan
    # Also cancel if we've found one in copied_already list
    too_long = album['length'] < 0 and len(album['keys']) == 1
    if too_long or (album['keys'] and all(
            key.tab_join() in copied_already for key in album['keys'])):  # gotcha: all([]) == True
        return None  # to cancel the rest of the get_tags calls for this folder
    if not (media := await read_tags(file, folder)):
        return None
    if bar:
        bar.next()
    length = media.length / 60
    album['length'] -= length  # count down from initial value of maximum wanted
    # use album artist (if available) so we can compare 'Various Artist' albums
    album_artist = str(media.albumartist or media.artist)
    album_title = str(media.album)
    album['keys'].add(AlbumKey(folder, album_artist, album_title))
    return Tags(folder, file, album_artist, album_title, length)


async def read_tags(file: Path | str, folder: Path) -> phrydy.MediaFile | None:
    """Read tags from a media file."""
    filename = folder / file
    try:
        media = phrydy.MediaFile(filename)
    except Exception as e:
        print(f'No media info for {file.name}', e)
        return None
    if not media.length:
        media.length = filename.stat().st_size * 8 / (1024 * 128)  # some buggy mp3s - assume 128kbps
    return media


def get_album_files() -> list[tuple[Path, str]]:
    """Scan media files in the current folder and subfolders. Return a list of tuples (folder, file)."""
    exclude_prefixes = tuple((Path(music_folder) / 'not_cd_folders.txt').read_text().split('\n')[1:])  # first one is "_Copied" - this is OK

    def include_folder(walk_tuple: tuple[Path, list[str], list[str]]) -> bool:
        """Returns True if the given folder should be included, based on a set of prefixes to exclude."""
        include_folder.count += 1
        folder = walk_tuple[0]
        should_include = not folder.relative_to(music_folder).as_posix().startswith(exclude_prefixes)
        # if not should_include and test_mode:
        #     print('Excluding', folder[len(base_folder) + 1:])
        return should_include

    include_folder.count = 0
    included = filter(include_folder, music_folder.walk())

    return [(folder, file)
            for folder, _, file_list in included
            for file in filter(is_media_file, file_list)]


async def copy_albums(copy_folder_list: list[Folder],
                      supplied_file_list: list[tuple[Path, str]],
                      copied_already: set[str]) -> tuple[str, Path]:
    """Select random albums up to the given length for each folder.
    Avoids a big scan of tags by picking folders and files at random from a (fast) os.walk list."""
    toast = ''
    scanned_albums: dict[AlbumKey, Album] = {}
    """Albums are defined by distinct values of (folder, artist, album_name).
    Each value in the album dict is a dict with filenames as keys and duration in minutes as values."""
    start_time = datetime.now()
    max_length_overall = max(copy_folder.max_length for copy_folder in copy_folder_list)
    image_filenames: list[Path] = []
    for copy_folder in copy_folder_list:
        file_list = supplied_file_list.copy()  # reset file list since we remove from it for each copy_folder
        print('\n', copy_folder, sep='')
        min_length, max_length = copy_folder.min_length, copy_folder.max_length
        maybe_list: list[dict[AlbumKey, Album]] = []
        to_copy = 1 if test_mode else copy_folder.min_count - len(list(copy_folder.address.glob('20*/')))
        while to_copy > 0 and len(file_list) > 0:
            start_loop = datetime.now()

            # pick a random folder and a random track from it
            chosen_folder = random.choice(list(set(folder for folder, _ in file_list)))
            chosen_file = random.choice([file for folder, file in file_list if folder == chosen_folder])
            # alternative naive method, favours big folders
            # chosen_folder, chosen_file = random.choice(file_list)

            # scanned this folder yet?
            chosen_key = next((key for key, album in scanned_albums.items()
                               if key[0] == chosen_folder and chosen_file in album),
                              None)
            if chosen_key is None:  # not scanned this folder yet
                # find other tracks in album - how long is it?
                folder_files = [file for folder, file in file_list if folder == chosen_folder]
                # scan chosen file first (avoids problems if cancelling scan early)
                folder_files.remove(chosen_file)
                folder_files.insert(0, chosen_file)
                # display progress if it's going to take a while
                bar = IncrementalBar(chosen_folder.relative_to(music_folder).as_posix(),
                                     max=len(folder_files),
                                     suffix='%(index)d/%(max)d ') if len(folder_files) > 20 else None
                async with asyncio.TaskGroup() as task_group:
                    album = {'length': max_length_overall, 'keys': set()}  # to track total length across get_tags calls
                    get_tags_tasks = [task_group.create_task(get_tags(chosen_folder, file, album, copied_already, bar))
                                      for file in folder_files]
                if bar:  # erase progress bar
                    print('\r' + ' ' * bar._max_width, end='\r')
                folder_tags = filter(None, [task.result() for task in get_tags_tasks])
                # add everything in folder to albums list for later reference
                for tags in folder_tags:
                    # albums is a dict of dicts: each subdict stores (file, duration) as (key, value) pairs
                    key = AlbumKey(tags.folder, tags.artist, tags.album_title)
                    scanned_albums.setdefault(key, {})[tags.file] = tags.length
                    if tags.file == chosen_file:
                        chosen_key = key

            print(chosen_key, end=' ')
            # remove all tracks from list so we won't choose it again
            # note this is potentially removing more than just in chosen_key
            # edge case: 'misc' folders with several albums might get missed
            # if first chosen track has been copied already
            file_list = [(folder, file) for folder, file in file_list if folder != chosen_folder]
            elapsed = (datetime.now() - start_loop).total_seconds() * 1000

            if chosen_key.tab_join() in copied_already:
                print(f'{cross} copied already {elapsed:.0f}ms')
                continue

            if len(scanned_albums[chosen_key]) < 2:
                print(f'{cross} not enough tracks {elapsed:.0f}ms')
                continue

            length = sum(scanned_albums[chosen_key].values())
            print(f'({round(length)} min)', end=' ')
            if length > max_length:
                print(f'{cross} too long {elapsed:.0f}ms')
                continue

            # could we add this to any existing lists?
            new_lengths = [sum(sum(album.values()) for album in copy_dict.values()) + length
                           for copy_dict in maybe_list]
            if any(in_range := [l if min_length <= l <= max_length else False for l in new_lengths]):
                # go for the longest available
                print('in range:', list_lengths(in_range), end=' ')
                index = in_range.index(max(in_range))
            elif any(below_max := [l if l <= max_length else False for l in new_lengths]):
                # need to fit more in, so go for the shortest - more likely to get something
                print('below max:', list_lengths(below_max), end=' ')
                index = below_max.index(min(below_max))
            else:
                index = None
            if index is not None:
                copy_dict = maybe_list[index]
                new_length = new_lengths[index]
                print(tick, 'appended to', *copy_dict.keys())
                copy_dict[chosen_key] = scanned_albums[chosen_key]
            else:  # new list
                maybe_list.append({chosen_key: scanned_albums[chosen_key]})
                new_length = length
                print(tick)
            if new_length >= min_length:
                to_copy -= 1
                print(f'{tick} Got enough, {to_copy=}')

        if to_copy:  # ran out of albums
            toast += f'⏹ Not enough found with length {copy_folder.min_length}-{copy_folder.max_length} minutes\n'
            continue

        # copy from copy_list
        for copy_dict in maybe_list:
            lengths = (sum(album.values()) for album in copy_dict.values())
            total_length = sum(lengths)
            if min_length <= total_length <= max_length:
                copied_already |= {key.tab_join() for key in copy_dict.keys()}
                folder_name: Path | None = reduce(reducible_copy_album, [(ak, a, copy_folder.address) for ak, a in copy_dict.items()], None)
                folder_name_inc_length = Path(f'{folder_name} [{total_length:.0f}]')
                if not test_mode:
                    with suppress(OSError):  # doesn't matter if an error occurs here
                        folder_name.rename(folder_name_inc_length)
                toast += f'{tick} {folder_name_inc_length.name[11:]}\n'
                for key, album in sorted(copy_dict.items(), reverse=True, key=lambda item: sum(item[1].values())):
                    # Check for embedded images in the tags of the first file
                    media = await read_tags(list(album.keys())[0], key.folder)
                    if media.art:
                        _, image_filename = tempfile.mkstemp()
                        image_filename = Path(image_filename)
                        image_filename.write_bytes(media.art)
                    else:
                        # Otherwise, look in the folder
                        image_filename = next((file for file in key.folder.iterdir()
                                               if file.suffix.lower() in ('.png', '.jpg', '.jpeg')
                                               and not file.stem.lower().startswith(('cd', 'back'))), '')
                    if image_filename:
                        image_filenames.append(image_filename)
                        continue

    files_scanned = sum(len(album) for album in scanned_albums.values())
    elapsed_seconds = (datetime.now() - start_time).total_seconds()
    scan_percentage = 100 * files_scanned / len(supplied_file_list)
    print(f'\nRead {files_scanned} files ({scan_percentage:.1f}% of total)'
          f' in {elapsed_seconds :.1f}s, {files_scanned / elapsed_seconds :.0f} files/sec')

    if not image_filenames:
        return toast

    thumbnail_size = 300
    show_count = min(len(image_filenames), 4)
    # gallery 1x1, 2x1, 3x1, 2x2 - don't need more than this
    n_across = [0, 1, 2, 3, 2][show_count]
    n_down = [0, 1, 1, 1, 2][show_count]
    x, y = 0, 0
    gallery = Image.new('RGB', (thumbnail_size * n_across, thumbnail_size * n_down))
    for image_filename in image_filenames[:show_count]:
        with suppress(OSError):  # e.g. PIL.UnidentifiedImageError
            gallery.paste(Image.open(image_filename).resize((thumbnail_size, thumbnail_size)),
                          (x * thumbnail_size, y * thumbnail_size))
            if image_filename.is_relative_to(tempfile.gettempdir()):  # clean up temp files
                os.remove(image_filename)
        x += 1
        if x == n_across:
            x = 0
            y += 1
    _, output_image = tempfile.mkstemp(suffix='.jpg')
    gallery.save(output_image)
    return toast, Path(output_image)


def list_lengths(lengths: list[float]) -> str:
    """Return a comma-separated string of lengths with 1 decimal place."""
    return ', '.join([f'{l:.1f}' for l in filter(None, lengths)])


def read_copy_log(max_size: int = 700) -> set[str]:
    """Read the copied_already.txt log file and output a set of lines in the file.
    Each line consists of a relative file path, album artist and title, separated by tabs.
    Path separators in the file are always stored as '/'.
    Multiple copies of the log are merged into a single file."""
    # deal with multiple copies of the log (typically Syncthing-generated)
    copied_already = set()
    pattern = f'{copy_log_file.stem}*{copy_log_file.suffix}'
    print(pattern)
    for name in music_folder.glob(pattern):
        print(name)
        copied_already |= set(name.read_text(encoding='utf-8').splitlines())
        if name != copy_log_file:  # get rid of other copies and keep the original
            send2trash(name)
    # Allow some albums from the copied_already list back into the list
    while len(copied_already) > max_size:
        rescued = copied_already.pop()
        print('Rescued:', rescued)
    if not test_mode:
        copy_log_file.write_text('\n'.join(copied_already) + '\n', encoding='utf-8')
    print(f'{len(copied_already)} albums in copied_already list')
    return copied_already


async def check_folder_list(copy_folder_list: list[Folder]) -> tuple[str, list[Folder]]:
    """Go through each copy folder in turn. Delete subfolders from it if they've been played."""
    scrobbles = get_scrobbles()
    toast = ''
    folders_to_fill = []
    start_time = datetime.now()
    artist_title.counter = 0
    for copy_folder in copy_folder_list:
        # delete any that have been played
        subfolders = list(copy_folder.address.glob('20*/'))
        to_delete = []
        for subfolder in subfolders:
            print(subfolder.name, end=' ')
            files = [file for file in subfolder.iterdir() if is_media_file(file)]
            file_count = len(files)
            try:
                async with asyncio.TaskGroup() as task_group:
                    artist_titles = [task_group.create_task(asyncio.to_thread(artist_title, file)) for file in files]
                    # artist_titles = [t.result() for t in tasks]
                    played_count = 0
                    not_played_count = 0
                    for tags in artist_titles:
                        # sometimes Last.fm artists/titles aren't quite the same as mine - look for close matches
                        if get_close_matches(await tags, scrobbles, n=1, cutoff=0.9):
                            played_count += 1
                            if played_count >= file_count / 2:
                                print(wcwidth.ljust("▶️", 3), f'played at least {played_count}/{file_count} tracks')
                                to_delete.append(subfolder)
                                break
                        else:
                            not_played_count += 1
                            if not_played_count >= file_count / 2:
                                print(wcwidth.ljust("⛔", 3), 'not played')
                                break
                    raise TerminateTaskGroup()
            except* TerminateTaskGroup:
                pass

        for subfolder in to_delete:
            send2trash(subfolder)
            toast += f'{cross} {subfolder.name[11:]}\n'
            subfolders.remove(subfolder)
        if test_mode or len(subfolders) < copy_folder.min_count:  # need more albums in this folder
            folders_to_fill.append(copy_folder)
    print('Checked folders in', datetime.now() - start_time, 'with', artist_title.counter, 'calls to artist_title')
    return toast, folders_to_fill


def get_scrobbles() -> list[str]:
    """Get recently played tracks (as reported by Last.fm)."""
    played_tracks = lastfm.get_user('ning').get_recent_tracks(limit=200)
    return [f'{track.track.artist.name} - {track.track.title}'.lower() for track in played_tracks]


def find_copy_folders() -> list[Folder]:
    """Look through the Radio folder to find folders named like '55-70 minutes x6'. Return a list of those folders."""
    extra_time = 0 if 4 <= datetime.now().month <= 10 else 5  # takes longer in winter!
    if not radio_folder.exists():
        return []  # doesn't exist on every computer
    folder_list = []
    pattern = re.compile(r'(?P<min_length>\d+)-(?P<max_length>\d+) minutes x(?P<count>\d+)')
    for folder in radio_folder.glob('*/'):  # folders only
        if not (match := pattern.match(folder.name)):
            continue
        min_length = int(match['min_length'])
        max_length = int(match['max_length'])
        count = int(match['count'])
        time_to_add = extra_time if min_length >= 30 else 0
        folder_list.append(Folder(folder, min_length + time_to_add, max_length + time_to_add, count))
    return folder_list


def copy_60_minutes(**kwargs) -> str | tuple[str, str] | datetime:
    return asyncio.run(copy_60_minutes_async())


async def copy_60_minutes_async() -> str | tuple[str, str] | datetime:
    """Find albums of the specified length to copy into subfolders of the Radio folder.
    The idea is to have whole albums to listen to on my bike commute to work."""
    # if test_mode:
    #     profiler = Profiler(async_mode='enabled')
    #     profiler.start()
    tomorrow_morning = datetime.now().replace(hour=9, minute=0) + timedelta(days=1)
    if not (copy_folder_list := find_copy_folders()):
        print('No folders to copy into on this device')
        return tomorrow_morning
    print(*copy_folder_list, sep='\n')
    toast, copy_folder_list = await check_folder_list(copy_folder_list)
    if not copy_folder_list:
        print('Not ready to copy new album.')
        return tomorrow_morning

    copied_already = read_copy_log()
    copy_toast, image_filename = await copy_albums(copy_folder_list, get_album_files(), copied_already)
    toast += copy_toast
    # if test_mode:
    #     profiler.stop()
    #     profiler.open_in_browser()
    return (toast, image_filename) if image_filename else toast


def list_by_length(albums: dict[AlbumKey, Album], max_length: int = 0) -> None:
    """List the number of albums by length."""
    length_counter = Counter()
    for key, file_list in albums.items():
        duration = sum(file_list.values())
        length_counter[int(duration // 5 * 5)] += 1  # round to next-lowest 5 minutes
    max_count = max(length_counter.values())
    for length in sorted(length_counter.keys()):
        if max_length and length > max_length:
            break
        print(length, length_counter[length], "*" * int(60 * length_counter[length] / max_count), sep='\t')


if __name__ == '__main__':
    # then = datetime.now()
    # print(*scan_music_folder().items(), sep='\n')
    # print(datetime.now() - then)
    # test_mode = True
    # from pyinstrument import Profiler
    result = copy_60_minutes()
    if isinstance(result, tuple):
        print(*result, sep='\n')
        os.startfile(result[1])
    else:
        print(result)
