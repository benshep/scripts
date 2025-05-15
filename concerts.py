import urllib.parse
from time import sleep
import os
import requests
from base64 import b32hexencode
from math import cos, sin, radians, atan2, sqrt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import TypedDict
from lastfm import lastfm
from ticketmaster import ticketmaster_api_key
import google_api
import googleapiclient.errors
from folders import music_folder

google_calendar = google_api.calendar.events()
calendar_id = '3a0374a38ea8a8ce023b6173a9a9a6c3c86d118280f0bf104e2091f81c4a8854@group.calendar.google.com'

# central latitude and longitude, and radius in km - centred around Haydock, includes Liverpool and Manchester
# https://www.mapdevelopers.com/draw-circle-tool.php?circles=%5B%5B33602.27%2C53.4918407%2C-2.6405878%2C%22%23AAAAAA%22%2C%22%23000000%22%2C0.4%5D%5D
central_lat, central_long, radius = radians(53.491841), radians(-2.640588), 33.603
# Approximate radius of earth in km
earth_radius = 6373.0

musicbrainz_api_url = 'https://musicbrainz.org/ws/2'


def get_ticketmaster_events(artist_name):
    """Find upcoming concerts for an artist using Ticketmaster API"""
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        'apikey': ticketmaster_api_key,
        'keyword': artist_name,
        'countryCode': 'GB',  # United Kingdom
        'size': 10  # Limit results per artist
    }
    # limit: 5000 requests every 1 day
    response = requests.get(url, params=params).json()

    events = response.get('_embedded', {}).get('events', [])
    concerts = []

    for event in events:
        info = event['_embedded']
        if event['name'] != artist_name and all(
                attraction['name'] != artist_name for attraction in info.get('attractions', [])):
            continue
        venue = info['venues'][0]
        if 'location' not in venue:
            print(venue)
            print(f'No location info for {venue["name"]}')
            continue
        location = venue['location']
        longitude = radians(float(location['longitude']))
        latitude = radians(float(location['latitude']))
        dlon = longitude - central_long
        dlat = latitude - central_lat
        a = sin(dlat / 2) ** 2 + cos(central_lat) * cos(latitude) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = earth_radius * c
        city = venue['city']['name']  # also available in venue: postalCode, address:line1/...
        if distance > radius:  # Only keep NW England events
            continue

        start = event['dates']['start']
        try:
            start_datetime = datetime.fromisoformat(start['dateTime'])
        except KeyError:  # no dateTime specified: default to 7pm
            start_datetime = datetime.fromisoformat(start['localDate']).replace(hour=19,
                                                                                tzinfo=ZoneInfo('Europe/London'))
        venue_name: str = venue['name']
        if venue_name.upper() == venue_name:
            venue_name = venue_name.title()  # convert UPPER CASE to Proper Case (but only if name is in ALL CAPS)
        concert_title = event['name']
        if artist_name not in event['name']:
            concert_title += f' (feat. {artist_name})'
        if venue_name not in concert_title:
            concert_title += f' at {venue_name}'
        if city not in concert_title:
            concert_title += f', {city}'
        # print(concert_title)
        concert = {
            'date': start_datetime,
            'venue': venue_name,
            'city': city,
            'id': event['id'],
            'url': event['url'],
            'title': concert_title,
        }
        # print(event)
        concerts.append(concert)

    return concerts


def find_upcoming_concerts(artists):
    """Find upcoming concerts in NW England for given artists"""
    concerts_in_nw = {}

    for artist in artists:
        artist_name = artist.item.name
        # print(artist_name)
        events = get_ticketmaster_events(artist_name)
        if events:
            concerts_in_nw[artist_name] = events

    return concerts_in_nw


def get_upcoming_shows():
    global artist, events
    top_artists = get_top_artists()
    # print(f"🎵 Top artists for user '{username}' in the last 12 months:")
    # for i, artist in enumerate(top_artists):
    #     print(f"{i + 1: 3d}. {artist.item.name}")
    return find_upcoming_concerts(top_artists)


def get_top_artists():
    return lastfm.get_user('ning').get_top_artists(period='12month', limit=100)


def get_calendar_events() -> list[dict]:
    now = datetime.now().isoformat() + 'Z'
    events = google_calendar.list(calendarId=calendar_id, timeMin=now, maxResults=500,
                                  singleEvents=True, orderBy='startTime').execute()
    return events['items']


def format_time(time: datetime):
    return time.strftime('%d %b %H:%M')  # e.g. 15 Mar 14:00


def update_gig_calendar():
    toast = ''
    my_events = get_calendar_events()
    for artist_name, shows in get_upcoming_shows().items():
        for show in shows:
            show_title = show['title']
            print('Adding', show_title)
            # https://developers.google.com/calendar/api/v3/reference/events/insert
            # characters allowed in the ID are those used in base32hex encoding, i.e. lowercase letters a-v and digits 0-9, see section 3.1.2 in RFC2938
            # the length of the ID must be between 5 and 1024 characters
            show_id = b32hexencode(show['id'].encode('utf-8')).lower().decode('utf-8').replace('=', '')
            event = {'summary': show_title,
                     'id': show_id,
                     'source': {
                         'title': 'Ticketmaster',
                         'url': show['url'],
                     },
                     'location': f'{show["venue"]}, {show["city"]}',
                     'start': {'dateTime': show['date'].isoformat()},
                     'end': {'dateTime': (show['date'] + timedelta(hours=3)).isoformat()}}
            # print(show['date'].date())
            # try to find matching events in calendar: don't add if we already have one
            for my_event in my_events:
                # we store the id to remember it
                if show_id in (my_event.get('id', ''), my_event.get('description', '')):
                    print('- already found via id')
                    break
                # but sometimes Ticketmaster returns several identical events - try to eliminate these
                my_event_date = datetime.fromisoformat(my_event['start']['dateTime']).date()
                # print(my_event['summary'], my_event_date)
                if artist_name in my_event['summary'] and my_event_date == show['date'].date():
                    print('- already found via artist and date')
                    break
            else:  # not found
                toast += f'New show: {show_title}, {format_time(show["date"])}\n'
                try:
                    google_calendar.insert(calendarId=calendar_id, body=event).execute()
                except googleapiclient.errors.HttpError as error:
                    if error.error_details[0].get('reason', '') == 'duplicate':  # id already exists: use description field
                        event['description'] = event.pop('id')
                        google_calendar.insert(calendarId=calendar_id, body=event).execute()
                    else:
                        raise error
                my_events.append(event)
                continue
            # date changed?
            start = datetime.fromisoformat(my_event['start']['dateTime'])
            if start.date() != show['date'].date():
                toast += f'Updated {show_title} to {format_time(show["date"])} (was {format_time(start)})\n'
                google_calendar.update(calendarId=calendar_id, eventId=my_event['id'], body=event).execute()
    return toast


Release = TypedDict('Release', {
    'title': str,
    'date': str | datetime,
    'artist': str
})


def get_new_releases(artist) -> list[Release]:
    """Fetch new releases for an artist from MusicBrainz."""
    artist_name = artist.item.name
    now = datetime.now()
    period = timedelta(days=30)
    min_date = (now - period).strftime('%Y-%m-%d')
    max_date = (now + period).strftime('%Y-%m-%d')
    print(artist_name)
    query = ' AND '.join([
        f'artist:"{artist_name}"',
        'type:album', '-type:live',
        f'firstreleasedate:[{min_date} TO {max_date}]',
    ])
    url = f'{musicbrainz_api_url}/release-group/'
    params = {
        'query': query,
        'fmt': 'json'
    }

    headers = {'User-Agent': f'get_new_releases/{now.strftime("%Y%m%d")} ( bjashepherd@gmail.com )'}
    sleep(1)  # MusicBrainz rate limit: 1 request per second  https://wiki.musicbrainz.org/MusicBrainz_API/Rate_Limiting
    response = requests.get(url, params=params, headers=headers)
    # print(response.url)
    json = response.json()
    # print(json)
    releases = json.get('release-groups', [])
    # if len(releases):
    #     print(json)
    return [
        {
            'title': release['title'],
            'date': release.get('first-release-date', 'Unknown'),
            'artist': artist_name
        } for release in releases
        if artist_name in [artist['name'] for artist in release['artist-credit']]
    ]


def find_new_releases():
    """Find new releases for the user's top artists."""
    release_list_filename = os.path.join(music_folder, 'New releases.md')
    release_list = open(release_list_filename, encoding='utf-8').read() if os.path.exists(release_list_filename) else ''
    artists = get_top_artists()
    all_releases = []
    toast = ''

    if not artists:
        print("No top artists found.")
        return

    for artist in artists:
        releases = get_new_releases(artist)
        if releases:
            all_releases.extend(releases)
            for release in releases:
                release_title = f"{release['artist']} - {release['title']}"
                if release_title not in release_list:
                    toast += release_title + '\n'
                    youtube_url = 'https://music.youtube.com/search?q=' + urllib.parse.quote_plus(release_title)
                    release_text = f"[{release_title}]({youtube_url}), out {release['date']}\n"
                    open(release_list_filename, 'a', encoding='utf-8').write('- [ ] ' + release_text)  # add checkbox
        # else:
            # print(f"No new releases found for {artist.item.name}.")
    return toast

if __name__ == '__main__':
    # concerts = get_upcoming_shows()
    # print("\n🎤 Upcoming concerts in North West England:")
    # for artist, events in concerts.items():
    #     for event in events:
    #         print(f"{artist.item.name} - {event['date']} at {event['venue']}, {event['city']}")
    print(get_upcoming_shows())
    # print(update_gig_calendar())