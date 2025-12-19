from datetime import timedelta, datetime
from time import sleep

import requests

from google_routing_credentials import api_key
from locations import home, katie_yr2


def get_directions():
    home_lat_lng = {"location": {"latLng": home}}
    dest = {"location": {"latLng": katie_yr2}}
    url = 'https://routes.googleapis.com/directions/v2:computeRoutes'

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.description,routes.warnings",
    }

    payload = {
        "origin": home_lat_lng,
        "destination": dest,
        "computeAlternativeRoutes": False,
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL"
    }

    while True:
        response = requests.post(url, json=payload, headers=headers).json()
        for route in response['routes']:
            duration = timedelta(seconds=int(route['duration'].rstrip('s')))
            km = route['distanceMeters'] / 1000
            now = datetime.now()
            eta = now + duration
            print(now.strftime('%H:%M'),
                  str(duration)[:-3],  # don't need seconds
                  f"ETA {eta.strftime('%H:%M')}",
                  f"{km:.0f} km",
                  route['description'],
                  *route['warnings'],
                  sep='\t')
        sleep(60 * 5)


if __name__ == '__main__':
    get_directions()
