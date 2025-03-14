import base64

import requests
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from lastfm import lastfm
from ticketmaster import ticketmaster_api_key
import google_api

google_calendar = google_api.calendar.events()
calendar_id = '3a0374a38ea8a8ce023b6173a9a9a6c3c86d118280f0bf104e2091f81c4a8854@group.calendar.google.com'

# NW England cities to filter concerts
north_west_cities = ['Manchester', 'Liverpool', 'Chester', 'Preston', 'Bolton', 'Warrington', 'Lancaster', 'Salford']


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
        if event['name'] != artist_name:
            continue
        venue = event['_embedded']['venues'][0]
        city = venue['city']['name']  # also available in venue: postalCode, address:line1/..., location:latitude/longitude
        if city not in north_west_cities:  # Only keep NW England events
            continue

        start = event['dates']['start']
        try:
            start_datetime = datetime.fromisoformat(start['dateTime'])
        except KeyError:  # no dateTime specified: default to 7pm
            start_datetime = datetime.fromisoformat(start['localDate']).replace(hour=19, tzinfo=ZoneInfo('Europe/London'))
        venue_name : str = venue['name']
        if venue_name.upper() == venue_name:
            venue_name = venue_name.title()  # convert UPPER CASE to Proper Case (but only if name is in ALL CAPS)
        concert = {
            'date': start_datetime,
            'venue': venue_name,
            'city': city,
            'id': event['id'],
            'url': event['url']
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
            concerts_in_nw[artist] = events

    return concerts_in_nw


def get_upcoming_shows():
    global artist, events
    top_artists = lastfm.get_user('ning').get_top_artists(period='12month', limit=100)
    # print(f"🎵 Top artists for user '{username}' in the last 12 months:")
    # for i, artist in enumerate(top_artists):
    #     print(f"{i + 1: 3d}. {artist.item.name}")
    return find_upcoming_concerts(top_artists)


def get_calendar_events():
    now = datetime.now().isoformat() + 'Z'
    events = google_calendar.list(calendarId=calendar_id, timeMin=now, maxResults=500,
                                  singleEvents=True, orderBy='startTime').execute()
    return events['items']



def format_time(time: datetime):
    return time.strftime('%d %b %H:%M')  # e.g. 15 Mar 14:00


def update_gig_calendar():
    toast = ''
    my_events = get_calendar_events()
    for artist, shows in get_upcoming_shows().items():
        for show in shows:
            # find existing event in my calendar
            venue_name = show["venue"] if show['city'] in show['venue'] else f'{show["venue"]}, {show["city"]}'
            show_title = f'{artist.item.name} at {venue_name}'
            print(show_title)
            # characters allowed in the ID are those used in base32hex encoding, i.e. lowercase letters a-v and digits 0-9, see section 3.1.2 in RFC2938
            # the length of the ID must be between 5 and 1024 characters
            show_id = base64.b32hexencode(show['id'].encode('utf-8')).lower().decode('utf-8').replace('=', '')
            event = {'summary': show_title,
                     'description': show_id,  # was using id but seems to have a problem with removed events
                     'source.title': 'Ticketmaster',
                     'source.url': show['url'],
                     'location': f'{show["venue"]}, {show["city"]}',
                     'start': {'dateTime': show['date'].isoformat()},
                     'end': {'dateTime': (show['date'] + timedelta(hours=3)).isoformat()}}
            calendar_event = next((e for e in my_events if show_id in (e.get('id', ''), e.get('description', ''))), None)
            if not calendar_event:
                toast += f'New show: {show_title}, {format_time(show['date'])}\n'
                google_calendar.insert(calendarId=calendar_id, body=event).execute()
                continue
            # date/time changed?
            start = datetime.fromisoformat(calendar_event['start']['dateTime'])
            if start != show['date']:
                toast += f'Updated {show_title} to {format_time(show["date"])} (was {format_time(start)})\n'
                google_calendar.update(calendarId=calendar_id, eventId=calendar_event['id'], body=event).execute()
    return toast


if __name__ == '__main__':
    # concerts = get_upcoming_shows()
    # print("\n🎤 Upcoming concerts in North West England:")
    # for artist, events in concerts.items():
    #     for event in events:
    #         print(f"{artist.item.name} - {event['date']} at {event['venue']}, {event['city']}")
    print(update_gig_calendar())