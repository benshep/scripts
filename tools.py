from math import log


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
    precision += max(0, int(-23 - mag))  # add more precision for very tiny numbers: 1.23e-28 => 0.0001y
    mag = max(-8, min(8, int(mag // 3)))  # clip within limits of SI prefixes
    si_prefixes = ' kMGTPEZYyzafpnµm'  # index 1..8 for big numbers, -8..-1 for small ones
    return f'{num / base ** mag:.{precision}f}{split_with}{si_prefixes[mag]}'.strip()


def match(a: str, b: str) -> bool:
    """Case-insensitive string comparison."""
    return (a or '').lower() == (b or '').lower()  # replace None with blank string


bad_chars = str.maketrans({char: None for char in '*?/\\<>:|"'})  # can't use these in filenames


def remove_bad_chars(filename: str) -> str:
    return filename.translate(bad_chars)
