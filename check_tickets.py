from webbot import Browser
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!


def check_game_time(show_window=False):
    """Open a browser to check if the date/time is still TBC for a game."""
    web = Browser(showWindow=show_window)
    url = 'https://tickets.manutd.com/en-GB/categories/womens'
    web.go_to(url)
    match_title = 'MU Women v Liverpool Women'
    elements = web.find_elements(match_title)
    parent = elements[0].find_element_by_xpath('..')
    full_text = parent.text
    assert full_text.lower().startswith(match_title.lower())
    venue = full_text[len(match_title) + 1:]  # remove newline too
    if 'TBC' in venue:
        return  # still TBC, never mind
    Pushbullet(api_key).push_link('⚽ Football tickets', url, f'{match_title}\n{venue}')


if __name__ == '__main__':
    check_game_time()
