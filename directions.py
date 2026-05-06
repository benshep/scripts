from datetime import timedelta, datetime
from time import sleep

import requests

import google_api
from google_routing_credentials import api_key
import locations


def get_directions() -> str | datetime:
    """Get expected time and best route for driving home."""
    # wait until late afternoon
    now = datetime.now()
    if now.hour < 16:
        return now.replace(hour=16, minute=0)
    sheet_id = '1GzhMCHv6vgi9R2LNhmdKg7Rjy967tC6XrqFBJGxcGXM'  # Exercise spreadsheet
    last_ride_date, last_ride_route = google_api.get_data(sheet_id, 'Cycling', 'lastRide')[0]
    last_ride_date = datetime.strptime(last_ride_date, "%d/%m/%Y %H:%M:%S")
    if last_ride_date.date() == now.date() and 'to work' in last_ride_route:  # it's a cycle day - don't need driving route
        return (now + timedelta(days=1)).replace(hour=16, minute=0)
    home = {"location": {"latLng": locations.home}}
    work = {"location": {"latLng": locations.bike_shed}}
    url = 'https://routes.googleapis.com/directions/v2:computeRoutes'
    km_cost = 0.107
    bridge_cost = 2.15
    hourly_rate = 4

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.description,routes.warnings",
    }

    payload = {
        "origin": work,
        "destination": home,
        "computeAlternativeRoutes": True,
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL"
    }

    response = requests.post(url, json=payload, headers=headers).json()
    for route in response['routes']:
        route['duration'] = timedelta(seconds=int(route['duration'].rstrip('s')))
        route['km'] = route['distanceMeters'] / 1000
        route['eta'] = now + route['duration']
        route['cost'] = km_cost * route['km']
        if 'This route has tolls.' in route['warnings']:
            route['cost'] += bridge_cost
        route['weighted_cost'] = route['cost'] + route['duration'].total_seconds() * hourly_rate / 3600
    response['routes'] = sorted(response['routes'], key=lambda route: route['weighted_cost'])
    for route in response['routes']:
        route['warnings'] = [concise_warning(warning) for warning in route['warnings']]
        print(now.strftime('%H:%M'),
              str(route['duration'])[:-3],  # don't need seconds
              f"ETA {route['eta'].strftime('%H:%M')}",
              f"£{route['cost']:.2f}",
              f"£{route['weighted_cost']:.2f}",
              f"{route['km']:.0f} km",
              route['description'],
              *route['warnings'],
              sep='\t')
    route = response['routes'][0]
    return f"ETA {route['eta'].strftime('%H:%M')} via {route['description']}"


def concise_warning(warning: str) -> str:
    """Return a shorter version of a warning."""
    if warning.startswith('This route has '):
        warning = warning[15:]
    if warning.startswith('This route includes '):
        warning = warning[20:]
    return warning.rstrip('.')

if __name__ == '__main__':
    while True:
        print(get_directions())
        sleep(60 * 5)
