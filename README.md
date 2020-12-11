# scripts
Miscellaneous scripts that I use and may be useful to others.  Comments and contributions welcome.

## change-wallpaper.pyw
A Python 3 script to change your desktop wallpaper. Works on Linux and Windows. Adds a caption showing the original filename. Can also change the lockscreen on your desktop (in Windows and LXDE). With a little setup, you can even get a rotating wallpaper on your phone.

See [here](change-wallpaper.md) for full manual and instructions.

## update-60-minutes.pyw, copy-60-minutes.pyw
**update-60-minutes** scans various network folders to find albums around the 60 minute length, and adds them to a list.

**copy-60-minutes** copies one of these albums to a 'Commute' folder in your %UserProfile% folder. I sync this using [Syncthing](https://syncthing.net/) to my phone so that I have a ready selection of albums to listen to on my hour-long cycle commute.

## random_cd.py
Crawl your music folder and find a CD to listen to. Scrobbles to last.fm using [pylast](https://github.com/pylast/pylast). The `from lastfm import lastfm` line imports a bit of code that looks like this:

````
import pylast
lastfm = pylast.LastFMNetwork(api_key='MY_API_KEY', api_secret='MY_API_SECRET',
                              username='ning', password_hash='MY_PASSWORD_HASH')
````

For obvious reasons, the real code isn't posted here.

## best-cycle-days.py
Check the upcoming forecast and work calendar to find the best days to cycle to work. I don't cycle every day so I want an easy summary of when the best time will be.