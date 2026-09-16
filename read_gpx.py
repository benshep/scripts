import gpxpy

from folders import downloads_folder

with open(downloads_folder / 'onthegomap-24-km-route.gpx') as f:
    gpx = gpxpy.parse(f)

points = []
distance = 0
prev_point = None

for track in gpx.tracks:
    for segment in track.segments:
        for p in segment.points:
            if prev_point:
                distance += p.distance_2d(prev_point) or 0
            print(distance / 1000, p.elevation, sep='\t')
            prev_point = p