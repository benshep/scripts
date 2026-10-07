import time
from datetime import datetime, timedelta
from math import log
from typing import Any, Generator

import requests

from pushbullet_api_key import api_key  # local file, keep secret!
import pushbullet


def human_format(num: float, precision: int = 0, split_with: str = '', binary: bool = False) -> str:
    """Convert a number into a human-readable format, with k, M, G, T suffixes for
    thousands, millions, billions, trillions respectively.
    :param num: Number to convert to human-readable
    :param precision: Number of digits to round to
    :param split_with: Optional string to place between the number and the suffix
    :param binary: Use base 1024 instead of 1000, for file sizes and so on
    :return: Human-readable string"""
    base = 1024 if binary else 1000
    mag = log(abs(num), base ** (1/3)) if num else 0  # zero magnitude when num == 0
    precision += max(0, int(-29 - mag))  # add more precision for very tiny numbers: 1.23e-28 => 0.0001y
    mag = max(-10, min(10, int(mag // 3)))  # clip within limits of SI prefixes
    si_prefixes = ' kMGTPEZYRQqryzafpnµm'  # index 1..10 for big numbers, -10..-1 for small ones
    return f'{num / base ** mag:.{precision}f}{split_with}{si_prefixes[mag]}'.strip()


def match(a: str, b: str) -> bool:
    """Case-insensitive string comparison."""
    return (a or '').lower() == (b or '').lower()  # replace None with blank string


bad_chars = str.maketrans({char: None for char in '*?/\\<>:|"'})  # can't use these in filenames


def remove_bad_chars(filename: str) -> str:
    return filename.translate(bad_chars)


def odd_even_pages(num_pages: int):
    """Output the odd and even pages in a range, suitable for printing two pages to a sheet."""
    print('Odd')
    print(','.join(str(p + 1) for p in range(num_pages) if p % 4 in (0, 1)))
    print('Even')
    print(','.join(str(p + 1) for p in range(num_pages) if p % 4 in (2, 3)))


def get_pushes(pb: pushbullet.Pushbullet, modified_after: float | None = None, limit: int | None = None,
               filter_inactive: bool = True,
               wait_for_reset: bool = False,
               verbose: bool = False) -> list[dict]:
    """Version of get_pushes from pushbullet.py that allows for rate limiting.
    See https://docs.pushbullet.com/#ratelimiting
    If wait_for_reset is True, it will wait until the rate limit gets reset,
    otherwise it just returns what it has so far."""
    return list(push_generator(pb, modified_after=modified_after, limit=limit, filter_inactive=filter_inactive,
                               wait_for_reset=wait_for_reset, verbose=verbose))


def push_generator(pb: pushbullet.Pushbullet, modified_after: float | None = None, limit: int | None = None,
               filter_inactive: bool = True,
               wait_for_reset: bool = False,
               verbose: bool = False) -> Generator[Any, None, None]:
    """Generator-enabled get_pushes, allows for rate limiting.
    See https://docs.pushbullet.com/#ratelimiting
    If wait_for_reset is True, it will wait until the rate limit gets reset,
    otherwise it just returns what it has so far."""

    data = {"modified_after": modified_after, "limit": limit}
    if filter_inactive:
        data['active'] = "true"

    total_got = 0
    previous_remaining = 0
    used = 0
    while True:
        r = pb._session.get(pb.PUSH_URL, params=data)
        js = r.json()
        # Don't raise error for rate-limited requests; just wait for reset
        if r.status_code != requests.codes.ok and js.get('error', {}).get('code', None) != 'ratelimited':
            raise pushbullet.PushbulletError(r.text)

        # The units are a sort of generic 'cost' number. A request costs 1 and a database operation costs 4.
        # So reading 500 pushes costs about 500 database operations + 1 request = 500*4 + 1 = 2001
        reset = int(r.headers.get('X-Ratelimit-Reset'))  # when it resets (integer seconds in Unix Time)
        rate_limit = int(r.headers.get('X-Ratelimit-Limit'))  # what the ratelimit is
        remaining = int(r.headers.get('X-Ratelimit-Remaining'))  # how much you have remaining
        if previous_remaining > 0:
            used = previous_remaining - remaining
        previous_remaining = remaining
        reset_time = datetime.fromtimestamp(reset)
        if verbose:
            print(f'{reset_time=} {rate_limit=} {remaining=} {used=}')
        pushes = js.get("pushes")
        yield from pushes
        if remaining < 2 * used:  # we could use up to 2x more next time (seems to be mostly 85 but sometimes lower)
            if wait_for_reset:
                print('Waiting for rate limit reset at', reset_time)
                time.sleep(reset - datetime.now().timestamp() + 5)
            else:
                break
        if 'cursor' in js and (not limit or total_got < limit):
            if verbose:
                print(f'Got {total_got} pushes')
            data['cursor'] = js['cursor']
        else:
            break


def check_previous(title: str, line_start: str = '',
                   show_date: bool = True, days_before: int = 1000) -> Generator[Any, None, None]:
    """Fetch previous toasts produced by one of the automation routines.
    :param title: Only show toasts with this title.
    :param line_start: Only show lines which start with this string.
    :param show_date: Output the date of each matching toast.
    :param days_before: Go back this number of days looking for pushes.
    """
    pb = pushbullet.Pushbullet(api_key)
    start = datetime.now() - timedelta(days=days_before)
    pushes = push_generator(pb, modified_after=start.timestamp(), wait_for_reset=True, verbose=True)
    music_updates = (push for push in pushes if push.get('title') == title)

    for update in music_updates:
        if lines := [line for line in update['body'].splitlines() if line.startswith(line_start)]:
            if show_date:
                print(datetime.fromtimestamp(update['created']))
            print(*lines, sep='\n')
            yield from lines


if __name__ == '__main__':
    # while True:
    #     odd_even_pages(int(input('Number of pages: ')))
    copied = check_previous('✂  erase_trailers', days_before=10)
    print(*list(copied), sep='\n')
