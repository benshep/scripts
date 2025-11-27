import json
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import google_api

google_calendar = google_api.calendar.events()
calendar_id = 'family07468001989407757250@group.calendar.google.com'


class Fixture:
    """Store information about a sport fixture."""

    def __init__(self, fixture_id: str, time: datetime, home: str, away: str, tournament: str,
                 time_fixed: bool = True):
        self.id = fixture_id
        self.time = time
        self.home = home
        self.away = away
        self.tournament = tournament
        self.time_fixed = time_fixed

    def __repr__(self):
        return f'Fixture(id={self.id}, time={self.time}, {self.home} vs {self.away}, {self.tournament})'


def ymd(date, time=False):
    """Convert datetime into yyyy-mm-dd format (ISO 8601), and optionally THH:MM."""
    return date.strftime('%Y-%m-%d' + ('T%H:%MZ' if time else ''))


def get_home_fixtures(sport: str, team: str, team_full_name: str) -> list[Fixture]:
    """Get a list of home fixtures for the St Helens rugby league teams using the BBC Sports API."""
    today = datetime.today()
    end_date = today + timedelta(weeks=12)
    params = {'selectedEndDate': ymd(end_date),
              'selectedStartDate': ymd(today),
              'todayDate': ymd(today),
              'urn': f'urn:bbc:sportsdata:{sport}:team:{team}'}
    url = 'https://www.bbc.co.uk/wc-data/container/sport-data-scores-fixtures?' + urllib.parse.urlencode(params)
    print(url)
    data = json.loads(requests.get(url).text)
    fixtures = []
    for event in data['eventGroups']:
        match = event['secondaryGroups'][0]['events'][0]
        tournament = match['tournament']['name']
        for sponsor in ['Betfred ']:
            if tournament.startswith(sponsor):
                tournament = tournament[len(sponsor):]
                break
        home_team = match['home']['fullName']
        away_team = match['away']['fullName']
        start_date_time = match["startDateTime"].replace('.000', '')  # sometimes we get ms, sometimes not!
        print(f'{home_team} vs {away_team} at {start_date_time}')
        # datetime format: 2025-02-15T17:30:00.000+00:00
        definite_time = 'T' in start_date_time
        if definite_time:
            start_time = datetime.strptime(start_date_time, '%Y-%m-%dT%H:%M:%S%z')
        else:  # start time TBA: just parse the date and assume a 12:00 kick-off
            start_time = datetime.strptime(start_date_time, '%Y-%m-%d').replace(hour=12,
                                                                                tzinfo=ZoneInfo('Europe/London'))
        bbc_id = match['id']
        if home_team == team_full_name:
            fixtures.append(Fixture(bbc_id, start_time, home_team, away_team, tournament, definite_time))
    return fixtures


def get_local_fixtures():
    """Get a list of fixtures to be held at the St Helens stadium using the BBC Sports API."""
    today = datetime.today()  # - timedelta(days=3)
    end_date = today + timedelta(weeks=12)
    params = {'selectedEndDate': ymd(end_date),
              'selectedStartDate': ymd(today),
              'todayDate': ymd(today),
              'urn': 'urn:bbc:sportsdata:rugby-league'}
    url = 'https://www.bbc.co.uk/wc-data/container/sport-data-scores-fixtures?' + urllib.parse.urlencode(params)
    print(url)
    data = json.loads(requests.get(url).text)
    fixtures = []
    for event_group in data['eventGroups']:
        competition = event_group['displayLabel']  # e.g. Betfred Super League
        for sponsor in ['Betfred ']:
            if competition.startswith(sponsor):
                competition = competition[len(sponsor):]
                break
        for secondary_group in event_group['secondaryGroups']:
            competition_round = secondary_group['displayLabel']  # e.g. Semi-final (but can be empty)
            competition_round = f'{competition} {competition_round}' if competition_round else competition
            # print(competition_round)
            for match in secondary_group['events']:
                home_team = match['home']['fullName']
                away_team = match['away']['fullName']
                venue = match['venue'].get('name', '')
                # datetime format: 2025-02-15T17:30:00.000+00:00
                start_time = datetime.strptime(match['startDateTime'], '%Y-%m-%dT%H:%M:%S.000%z')
                # print(f'- {home_team} vs {away_team} at {venue}, {start_time}')
                if not venue:
                    if home_team != 'St Helens':
                        continue
                elif venue != 'Totally Wicked Stadium':
                    continue
                bbc_id = match['id']
                fixtures.append(Fixture(bbc_id, start_time, home_team, away_team, competition_round))
    return fixtures


def get_calendar_events():
    now = datetime.now().isoformat() + 'Z'
    events = google_calendar.list(calendarId=calendar_id, timeMin=now, maxResults=50,
                                  singleEvents=True, orderBy='startTime').execute()
    return events['items']


def format_time(time: datetime):
    return time.strftime('%d %b %H:%M')  # e.g. 15 Mar 14:00


def update_saints_calendar():
    toast = ''
    my_events = get_calendar_events()
    fixture_list = get_local_fixtures() + \
                   get_home_fixtures('rugby-league', 'st-helens', 'St Helens') + \
                   get_home_fixtures('football', 'liverpool-ladies', 'Liverpool')

    for match in fixture_list:
        # find existing event in my calendar
        match_title = f'{match.home} vs {match.away} ({match.tournament})'
        event = {'summary': match_title + ('' if match.time_fixed else ' (time TBA)'),
                 'description': match.id,
                 'start': {'dateTime': match.time.isoformat()},
                 'end': {'dateTime': (match.time + timedelta(hours=2)).isoformat()}}
        if not (calendar_event := next((event for event in my_events
                                        if event.get('description', '') == match.id), None)):
            toast += f'New match: {match_title}, {format_time(match.time)}\n'
            google_calendar.insert(calendarId=calendar_id, body=event).execute()
            continue
        # date/time changed?
        start = datetime.fromisoformat(calendar_event['start']['dateTime'])
        if start != match.time:
            toast += f'Updated {match_title} to {format_time(match.time)} (was {format_time(start)})\n'
            google_calendar.update(calendarId=calendar_id, eventId=calendar_event['id'], body=event).execute()
    return toast


if __name__ == '__main__':
    # print(*get_home_fixtures('rugby-league', 'st-helens', 'St Helens'), sep='\n')
    # print(*get_home_fixtures('football', 'liverpool-ladies', 'Liverpool'), sep='\n')
    print(update_saints_calendar())
