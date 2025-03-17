import os
from hashlib import sha1
from difflib import SequenceMatcher
from send2trash import send2trash
from folders import radio_folder

frame_start = b'\xff\xfe'


def erase_trailers(only_known=False, limit=30):
    """Search for repeated segments in MP3 files in the radio folder, and erase those segments from the files.
    Set only_known=True to only search for known repeats (stored in repeats.txt) , otherwise it will compare every file
    to all the previous ones.
    Analyses the first 30 files by default; set the limit to -1 or None to search them all."""
    # Limitation: it doesn't tend to find repeats from the end of the file. Probably because those bits don't sync
    # neatly to frame boundaries. Potentially could use acoustID to compare the raw audio - but then we have to either
    # figure out how many frames to chop, or re-encode to MP3.
    # https://pypi.org/project/pyacoustid/
    # and use audioread to get the PCM data

    toast = ''
    hash_size = 1  # just use the first N characters of a hash
    os.chdir(radio_folder)
    repeat_file = 'repeats.txt'
    digest = {}  # store each file's digest in a dict
    repeats = open(repeat_file, 'r').read().splitlines()
    print(f'{len(repeats)} known repeats')
    compare_length = 1153  # first ~30s
    max_cut = int(0.9 * compare_length)  # anything more than this is probably an error
    if limit is None:
        limit = -1
    for file in os.listdir()[:limit]:
        cut_length = 0
        if not file.lower().endswith('.mp3'):
            continue
        frames = open(file, 'rb').read().split(frame_start)
        this_digest = ''.join(sha1(frame).hexdigest()[:hash_size] for frame in frames[:compare_length])
        print(file)
        try:
            other_file = next(f for f, d in digest.items() if d == this_digest)
            if os.path.getsize(other_file) == os.path.getsize(file):
                # digest and file length are identical to a previous file, almost certainly a duplicate
                print(f'- Duplicate of {other_file} - deleting')
                send2trash(file)
                continue
        except StopIteration:
            pass

        # compare with known repeats
        for repeat in repeats:
            if repeat in this_digest:
                index = this_digest.index(repeat)
                length = len(repeat)
                print(f'= found {repeat[:10]} at {index}, {length=}')
                if length > max_cut:
                    print('= too long, ignoring')
                    continue
                this_digest = this_digest.replace(repeat, '', 1)
                del frames[index:index + length]
                write_mp3_file(file, frames)
                cut_length += length
        if not only_known:
            # compare with previous files
            matcher = SequenceMatcher(autojunk=False)
            matcher.set_seq2(this_digest)  # SequenceMatcher computes and caches detailed info about the second sequence
            for prev_file, prev_digest in digest.items():
                matcher.set_seq1(prev_digest)
                # MP3 frame size is 26ms, so 38 frames is about a second
                if matches := [match for match in matcher.get_matching_blocks()
                               if max_cut > match.size > 38 * hash_size and match.size % hash_size == 0]:
                    print(f'- {prev_file} {matches}')
                    for match in matches[::-1]:  # reverse order so we don't mess up the indices
                        repeat = this_digest[match.b:match.b + match.size]
                        if repeat not in repeats:
                            repeats.append(repeat)
                            open(repeat_file, 'a').write(repeat + '\n')
                        this_digest = this_digest.replace(repeat, '', 1)
                        matcher.set_seq2(this_digest)  # reset the matcher since we've changed the digest
                        del frames[match.b:match.b + match.size]
                        cut_length += len(repeat)
                    write_mp3_file(file, frames)
        digest[file] = this_digest
        if cut_length:
            toast += f'{file[:-4]}, {cut_length * 0.026:.0f}s\n'
    return toast


def write_mp3_file(file, frames):
    send2trash(file)  # don't just overwrite it in case something goes wrong!
    open(file, 'wb').write(frame_start.join(frames))


if __name__ == '__main__':
    print(erase_trailers(only_known=True))
