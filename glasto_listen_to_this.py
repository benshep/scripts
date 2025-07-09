from subprocess import check_output
import pylast
from lastfm import lastfm

glastonbury_iplayer_url = 'https://www.bbc.co.uk/iplayer/episodes/b007r6vx/glastonbury'
want_songs = True  # looking for individual songs? False means whole sets


def listen_to_this():
    """Fetch a list of Glastonbury performances from iPlayer, and select the most relevant for my listening habits."""
    my_top_artists_names = set(artist.item.name for artist in lastfm.get_user('ning').get_top_artists(limit=200))
    collecting = False
    command = [r'C:\Program Files\get_iplayer\get_iplayer.cmd', glastonbury_iplayer_url, '--pid-recursive-list']
    for line in check_output(command, encoding='ISO-8859-1').splitlines():
        if line == 'Episodes:':  # start of programme list
            collecting = True  # start with the next line
            continue
        if not collecting or ': ' not in line:
            continue
        series, rest = line.split(': ', maxsplit=1)
        if series == 'INFO':
            break  # end of programmes
        programme, _, pid = rest.split(', ', maxsplit=2)
        parts = programme.split(' - ')
        # some are "2025 - Artist - Title" i.e. just one song - looking for these?
        event = parts[0]
        if event in ('2025', 'Live Sets (2025)') and len(parts) == (3 if want_songs else 2):
            performer_name = parts[1]
            if performer_name in my_top_artists_names:
                print(pid, event, performer_name, parts[2] if want_songs else '')
            else:
                try:
                    similar = lastfm.get_artist(performer_name).get_similar(limit=20)
                except pylast.WSError:  # couldn't find artist
                    similar = []
                if overlap := set(artist.item.name for artist in similar) & my_top_artists_names:
                    print(pid, event, performer_name, '- ' + parts[2] if want_songs else '', '- similar to', ', '.join(overlap))


if __name__ == '__main__':
    listen_to_this()
