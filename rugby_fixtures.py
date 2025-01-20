from collections import namedtuple
import requests
import json
from datetime import datetime, timedelta, timezone
import google_api

google_calendar = google_api.calendar.events()
Fixture = namedtuple('Fixture', ['id', 'time', 'home', 'away'])



def ymd(date, time=False):
    """Convert datetime into yyyy-mm-dd format (ISO 8601), and optionally THH:MM."""
    return date.strftime('%Y-%m-%d' + ('T%H:%MZ' if time else ''))


def get_home_fixtures():
    """Get a list of home fixtures for the St Helens rugby league teams using the BBC Sports API."""
    today = datetime.today()
    end_date = today + timedelta(weeks=12)
    url = f'https://www.bbc.co.uk/wc-data/container/sport-data-scores-fixtures?selectedEndDate={ymd(end_date)}' \
          f'&selectedStartDate={ymd(today)}&todayDate={ymd(today)}' \
          f'&urn=urn%3Abbc%3Asportsdata%3Arugby-league%3Ateam%3Ast-helens'
    print(url)
    data = json.loads(requests.get(url).text)
    fixtures = []
    for event in data['eventGroups']:
        match = event['secondaryGroups'][0]['events'][0]
        home_team = match['home']['fullName']
        away_team = match['away']['fullName']
        # datetime format: 2025-02-15T17:30:00.000+00:00
        start_time = datetime.strptime(match['startDateTime'], '%Y-%m-%dT%H:%M:%S.000%z')
        bbc_id = match['id']
        if home_team == 'St Helens':
            print(bbc_id, start_time, home_team, 'vs', away_team)
            fixtures.append(Fixture(bbc_id, start_time, home_team, away_team))
    return fixtures


calendar_id = 'family07468001989407757250@group.calendar.google.com'


def get_calendar_events():
    now = datetime.now().isoformat() + 'Z'
    events = google_calendar.list(calendarId=calendar_id, timeMin=now, maxResults=50, singleEvents=True,
                                                  orderBy='startTime').execute()
    return events['items']


def update_saints_calendar():
    fixtures = get_home_fixtures()
    my_events = get_calendar_events()
    for match in fixtures:
        # find existing event in my calendar
        match_title = f'{match.home} vs {match.away}'
        event = {'summary': match_title,
                 'description': match.id,
                 'start': {'dateTime': match.time.isoformat()},
                 'end': {'dateTime': (match.time + timedelta(hours=2)).isoformat()}}
        print(match_title, match.time)
        try:
            calendar_event = next(event for event in my_events if event['description'] == match.id)
            # date/time changed?
            start_time = calendar_event['start']
            start = datetime.strptime(start_time['dateTime'], '%Y-%m-%dT%H:%M:%SZ')
            start = start.replace(tzinfo=timezone.utc)
            if start != match.time:
                print(f'Updated {match_title} to {start}')
                google_calendar.update(calendarId=calendar_id, eventId=calendar_event['id'], body=event).execute()
        except StopIteration:  # not found
            print(f'New match: {match_title} at {match.time}')
            google_calendar.insert(calendarId=calendar_id, body=event).execute()

if __name__ == '__main__':
    update_saints_calendar()
