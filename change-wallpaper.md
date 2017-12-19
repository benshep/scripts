# change-wallpaper.pyw

This is a Python script to randomly switch your desktop wallpaper to a different image. It works under Windows and Linux. You can set this up on a timer (using `cron` on Linux or Task Scheduler on Windows) to change your wallpaper every hour (or as often as you like), or just run it when you feel like a change.

# Features

- **Cross-platform**. Written in Python, and works on Windows and Linux.
- **Multi-monitor**. It will detect the placement of your monitors and automatically produce an image that covers all of them.
- **Space filling**. If your monitor is *landscape* and the image chosen by the script is *portrait*, the script will look for another image in the same folder to fill the space, ensuring you don't have big empty spaces surrounding your image on the desktop.
- **Captions**. The script places a caption at the bottom of the picture with the original filename of the chosen image. (The original image is unaffected.)
- **Seasonal**. At random, 50% of the time, the script will only pick images that were taken around the same time of year as the current date.
- **Lockscreen**. It can change your lockscreen wallpaper.

# Requirements

- Python. I use Python 3, but it will probably work on Python 2.
- [Pillow](https://python-pillow.org/)
- [screeninfo](https://github.com/rr-/screeninfo)
- For Linux, you need [Nitrogen](https://github.com/l3ib/nitrogen) to change the background

Installation of these requirements **should** be as simple as

`pip install pillow https://github.com/rr-/screeninfo`

(screeninfo is on PyPI but this ensures you get the newest version.)

# Usage

`python change-wallpaper.pyw [lockscreen | phone]`

Used without arguments, the script will pick a random JPG image from your Pictures folder (`~/Pictures` on Linux, `%USERPROFILE%\Pictures` on Windows). Half the time, this will be completely random. The rest of the time, a *seasonal* image will be chosen - i.e. one from the same time of year as the current date (but from any year).

It will add a caption to your image showing the filename relative to your Pictures folder.

This will be repeated for each of your monitors, and a big image will be produced to cover all the monitors. The resulting image is saved as `wallpaper.jpg` in the `wallpaper` folder under your home folder.

It will then set this wallpaper, using a system call in Windows, or by invoking [Nitrogen](https://github.com/l3ib/nitrogen) on Linux. It just uses Nitrogen's `--restore` option, so you'll need to run Nitrogen yourself to actually set the wallpaper.

## Lockscreen

Add the `lockscreen` argument to pick a wallpaper for your lockscreen. This works on Windows 7, and on Linux using the LXDE desktop environment. (Not working under Windows 10 yet.) The lockscreen wallpaper is saved as `lockscreen.jpg` under the folder described above.

Under Windows 7, you need a little trick to get Windows to use this wallpaper on the lockscreen. The lockscreen wallpaper is stored as `C:\Windows\System32\oobe\INFO\backgrounds\backgrounddefault.jpg`. To change this, set up a *symbolic link*. The process is as follows:

1. Run the script with the `lockscreen` argument to generate a `lockscreen.jpg` file
2. Open an Administrator Command Prompt
3. `cd C:\Windows\System32\oobe\INFO\backgrounds`
4. `ren backgrounddefault.jpg backgrounddefault2.jpg` (to make a backup copy)
5. `mklink backgrounddefault.jpg C:\Users\XXXX\wallpaper\lockscreen.jpg` (where `XXXX` is your user name)

(I am not responsible for anything that happens to your computer when you're running as admin!)

## Phone

You can also use this to generate background images for your phone. I use [Syncthing](https://syncthing.net/) and [SB Wallpaper Changer](https://play.google.com/store/apps/details?id=com.shirobakama.wpchanger&hl=en_GB) to rotate my phone's wallpaper; this script generates a series of images in a folder that is synced to my phone.

Run the script with the `phone` argument. It will produce a single image in the `phone-pics` subfolder of your home folder. This image will be numbered `000.jpg`. The next time it runs, it will produce one numbered `001.jpg` and so on up to 199, at which point it will go back to 000.

These images are all *portrait* orientation, and won't be made up of several smaller images (it will reject *landscape* images) due to the small screen size. The image size is fixed in the script at 720x1280 (10:16 aspect ratio).
