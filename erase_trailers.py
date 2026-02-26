import os
from datetime import timedelta, datetime
from difflib import SequenceMatcher
from hashlib import sha1
from random import sample
from shutil import copy2

from phrydy.mediafile import MediaFile
from progress.bar import IncrementalBar
from send2trash import send2trash

from folders import radio_folder

frame_start = b'\xff\xfe'
test_mode = False
compare_length = 1153  # first ~30s
max_cut = int(0.9 * compare_length)  # anything more than this is probably an error
hash_size = 1  # just use the first N characters of a hash


def erase_trailers(only_known: bool = False, limit: int | timedelta = timedelta(seconds=60)) -> str:
    """Search for repeated segments in MP3 files in the radio folder, and erase those segments from the files.
    Set only_known=True to only search for known repeats (stored in repeats.txt) , otherwise it will compare every file
    to all the previous ones.
    Uses a time limit of 60 seconds by default; set the limit to -1 to search all files, or set a number of files."""
    # Limitation: it doesn't tend to find repeats from the end of the file. Probably because those bits don't sync
    # neatly to frame boundaries. Potentially could use acoustID to compare the raw audio - but then we have to either
    # figure out how many frames to chop, or re-encode to MP3.
    # https://pypi.org/project/pyacoustid/
    # and use audioread to get the PCM data

    toast = ''
    os.chdir(radio_folder)
    repeat_file = 'repeats.txt'
    digest = {}  # store each file's digest in a dict
    repeats = open(repeat_file, 'r').read().splitlines()
    print(f'{len(repeats)} known repeats')
    start_time = datetime.now()
    file_list = os.listdir()
    last_index = limit if isinstance(limit, int) else len(file_list)
    file_list = sample(file_list, last_index)
    for file in file_list:
        if isinstance(limit, timedelta) and datetime.now() - start_time >= limit:
            print('Time limit reached')
            break
        cut_length = 0
        if not file.lower().endswith('.mp3'):
            continue
        frames = open(file, 'rb').read().split(frame_start)
        this_digest = ''.join(sha1(frame).hexdigest()[:hash_size] for frame in frames[:compare_length])
        try:
            other_file = next(f for f, d in digest.items() if d == this_digest)
            if os.path.getsize(other_file) == os.path.getsize(file):
                # digest and file length are identical to a previous file, almost certainly a duplicate
                print(f'{file} is duplicate of {other_file} - deleting')
                send2trash(file)
                continue
        except StopIteration:
            pass

        # compare with known repeats
        for repeat in repeats:
            if repeat in this_digest:
                index = this_digest.index(repeat)
                length = len(repeat)
                print(f'{file}: found {repeat[:10]} at {index}, {length=}')
                if length > max_cut:
                    print('= too long, ignoring')
                    continue
                this_digest = this_digest.replace(repeat, '', 1)
                del frames[index:index + length]
                cut_length += write_mp3_file(file, frames) or length * 0.13
        if not only_known:
            # compare with previous files
            matcher = SequenceMatcher(autojunk=False)
            matcher.set_seq2(this_digest)  # SequenceMatcher computes and caches detailed info about the second sequence
            bar = IncrementalBar(file, max=len(digest))
            all_matches = [get_matches(prev_digest, matcher, bar) for prev_digest in digest.values()]
            for prev_file, matches in zip(digest.keys(), all_matches):
                if matches:
                    print(f'- {prev_file} {matches}')
                    repeated_length = 0
                    for match in matches[::-1]:  # reverse order so we don't mess up the indices
                        repeat = this_digest[match.b:match.b + match.size]
                        repeated_length += len(repeat)
                        if repeat not in repeats:
                            repeats.append(repeat)
                            open(repeat_file, 'a').write(repeat + '\n')
                        this_digest = this_digest.replace(repeat, '', 1)
                        matcher.set_seq2(this_digest)  # reset the matcher since we've changed the digest
                        del frames[match.b:match.b + match.size]
                    cut_length += write_mp3_file(file, frames) or repeated_length * 0.13
            print('')  # new line after progress bar
        digest[file] = this_digest
        if cut_length:
            toast += f'{file[:-4]}, {cut_length:.0f}s\n'
    return toast


def get_matches(prev_digest, matcher, bar):
    bar.next()
    matcher.set_seq1(prev_digest)
    # MP3 frame size is 26ms, so 38 frames is about a second
    return [match for match in matcher.get_matching_blocks()
            if max_cut > match.size > 38 * hash_size and match.size % hash_size == 0]


def write_mp3_file(file: str, frames: list[bytes]) -> float:
    """Rewrite an MP3 file."""
    if not test_mode:
        original_length = MediaFile(file).length
        send2trash(file)  # don't just overwrite it in case something goes wrong!
        # copy2(file, file + '.orig.mp3')
        open(file, 'wb').write(frame_start.join(frames))
        return original_length - MediaFile(file).length
    else:
        return 0  # don't guess length in test mode


if __name__ == '__main__':
    # test_mode = True
    print(erase_trailers())
