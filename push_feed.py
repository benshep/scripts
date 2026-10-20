from datetime import datetime
from typing import LiteralString

import feedparser


def get_feed(**kwargs) -> tuple[LiteralString, str] | None:
    """Read an RSS feed, and return the last unread entry."""
    last_run = kwargs.get('last_run_time', datetime.now())
    url = 'https://www.xkcd.com/rss.xml'
    feed = feedparser.parse(url)
    new_entries = [entry for entry in feed.entries if datetime(*entry.published_parsed[:6]) > last_run]
    if len(new_entries) > 1:
        return '\n'.join(entry.title for entry in new_entries), use_mobile_site(feed.feed.link)
    elif len(new_entries) == 1:
        entry = new_entries[0]
        return entry.title, use_mobile_site(entry.link)
    return None


def use_mobile_site(url: str) -> str:
    """Replace a standard URL with a mobile-suitable one."""
    return url.replace('https://xkcd.com', 'https://m.xkcd.com')


if __name__ == '__main__':
    print(get_feed(last_run_time=datetime.now().replace(day=1)))
