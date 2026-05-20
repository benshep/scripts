#!python3
# -*- coding: utf-8 -*-
"""
Wallpaper Changer, Python version
Ben Shepherd, October 2016

Sets wallpaper for each monitor separately, and produces a canvas to cover all
Command line options:
    (no arguments)  set desktop background
    lockscreen      set wallpaper for lockscreen
                    assumes symlink set up from Windows default folder to lockscreen.jpg in user profile dir
    phone           produce a new wallpaper for phone, in landscape and portrait
                    places in phone-pics/Landscape and phone-pics/Portrait folders of user profile dir (max 200)
                    to be synced outside this script
"""

import ctypes
import datetime
import os
import subprocess
import sys
import time
from pathlib import Path

from send2trash import send2trash
from itertools import accumulate
from math import ceil  # calculation of mosaic dimensions
from random import randint

import screeninfo
from PIL import Image, ImageDraw, ImageFont

from folders import user_profile, pics_folder

pics_folder = pics_folder.resolve()  # in case of symlinks

on_windows = os.name == 'nt'
if on_windows:
    from win32api import GetMonitorInfo, MonitorFromPoint  # to find taskbar height
    import ctypes.wintypes

# Get EXIF orientation and transpose the image accordingly
# http://stackoverflow.com/questions/4228530/pil-thumbnail-is-rotating-my-image

flip_horizontal = lambda im: im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
flip_vertical = lambda im: im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
rotate_180 = lambda im: im.transpose(Image.Transpose.ROTATE_180)
rotate_90 = lambda im: im.transpose(Image.Transpose.ROTATE_90)
rotate_270 = lambda im: im.transpose(Image.Transpose.ROTATE_270)
transpose = lambda im: im.rotate_90(flip_horizontal(im))
transverse = lambda im: im.rotate_90(flip_vertical(im))
orientation_funcs = [None, lambda x: x, flip_horizontal, rotate_180,
                     flip_vertical, transpose, rotate_270, transverse, rotate_90]


def apply_orientation(im: Image) -> Image:
    """
    Extract the orientation EXIF tag from the image, which should be a PIL Image instance.
    If there is an orientation tag that would rotate the image, apply that rotation to
    the Image instance given to do an in-place rotation.

    :param Image im: Image instance to inspect
    :return: A possibly transposed image instance
    """

    try:
        if (exif := im._getexif()) is not None:
            return orientation_funcs[exif[0x0112]](im)  # orientation tag number
    except:
        # We'd be here with an invalid orientation value or some random error?
        pass  # log.exception("Error applying EXIF Orientation tag")
    return im


def change_wallpaper(target: str = 'desktop') -> None:
    """Pick a random image for a new desktop wallpaper image from the user's Pictures folder.
    The parameter target can be desktop, lockscreen or phone."""
    print(f'Wallpaper Changer, {target=}')

    wallpaper_dir = get_wallpaper_dir(target)

    if on_windows and target == 'lockscreen' and on_remote_desktop():
        return

    monitors = get_monitors(target)
    # print(monitors)
    if not monitors:
        return
    canvas, left, top = create_canvas(monitors)

    image_list = find_images()

    # font: Segoe UI, as on Windows logon screen, or Roboto for phone screen, or Ubuntu
    font_name = 'Roboto-Regular' if target == 'phone' else 'segoeui' if on_windows else 'Ubuntu-R'
    font = ImageFont.truetype(f'{font_name}.ttf', 24)

    def write_caption(im: Image, text: str, x: int, y: int, align_right: bool = False):
        draw = ImageDraw.Draw(im)
        print(f' Caption "{text}" at {x}, {y}')
        # put a black drop shadow behind so the text can be read on any background
        anchor = 'rt' if align_right else 'lt'  # top left or top right
        draw.text((x + 1, y + 1), text, 'black', font=font, anchor=anchor)
        draw.text((x, y), text, 'white', font=font, anchor=anchor)

    exclude_list = (pics_folder / 'exclude.txt').read_text().splitlines()

    today = datetime.date.today()

    for mon in monitors:
        # Want a seasonal image? (one that was taken in the same month)
        # Only do this in holiday periods
        seasonal = today.month in (4, 5, 8, 10, 12)  # choice((True, False))

        # print('monitor', mon)
        # portrait or landscape?
        mon_landscape = mon.width > mon.height
        print(f"{mon.width}x{mon.height}")
        if target == 'phone':  # separate canvases for each phone 'monitor' (landscape and portrait)
            canvas = Image.new('RGB', (mon.width, mon.height), 'black')

        while True:  # loop until break
            full_name = get_random_image(image_list)

            # for debugging!
            # full_name = r"C:\Users\bjs54\Pictures\WhatsApp\IMG-20190225-WA0003.jpg"
            # seasonal = False

            # print(f"{full_name[len(pics_folder) + 1:]}")
            if any(exc in full_name.as_posix() for exc in exclude_list):
                # print(' On excluded list')
                continue

            if seasonal and is_out_of_season(full_name, today):
                continue

            image = apply_orientation(Image.open(full_name))

            im_width, im_height = image.size
            im_landscape = im_width > im_height
            # print(f" {im_width}x{im_height}, {im_landscape=}")

            # calculate factor to scale larger images down - is 1 if image is smaller
            # just use height for phone - chop off left/right borders if necessary
            width_sf = 1 if (target == 'phone' and not im_landscape) else (mon.width / im_width)
            height_sf = 1 if (target == 'phone' and im_landscape) else (mon.height / im_height)
            scale_factor = min(width_sf, height_sf, 1)
            eff_width, eff_height = int(im_width * scale_factor), int(im_height * scale_factor)
            # print(f" Scaled image size: {eff_width}x{eff_height}")

            if im_width < mon.width and im_height < mon.height:
                num_across, num_down = int(ceil(mon.width / eff_width)), int(ceil(mon.height / eff_height))
            elif mon_landscape and not im_landscape:
                num_across, num_down = 2, 1
            elif im_landscape and not mon_landscape:
                num_across, num_down = 1, 2
            else:
                num_across, num_down = 1, 1
            mosaic_width, mosaic_height = num_across * eff_width, num_down * eff_height
            # just use height for phone - chop off left/right borders if necessary
            width_sf = 1 if (target == 'phone' and not im_landscape) else (mon.width / mosaic_width)
            height_sf = 1 if (target == 'phone' and im_landscape) else (mon.height / mosaic_height)
            scale_factor = min(width_sf, height_sf, 1)
            mosaic_width, mosaic_height = int(scale_factor * mosaic_width), int(scale_factor * mosaic_height)
            eff_width, eff_height = int(eff_width * scale_factor), int(eff_height * scale_factor)
            # print(f" Rescaled image size: {eff_width}x{eff_height}")

            # print(f" Mosaic dimensions: {mosaic_width}x{mosaic_height}")
            # print(f" Number of images: {num_across}x{num_down}")
            num_in_mosaic = num_across * num_down
            if target == 'phone' and num_in_mosaic > 1:
                # print(' Only one image wanted for phone screen!')
                continue

            if (dir_files := find_mosaic_images(full_name, image.size, image_list, num_in_mosaic)) is None:
                continue

            print(f" Resizing {num_in_mosaic} images to {eff_width}x{eff_height} each")
            mosaic_left = mon.x + (mon.width - mosaic_width) // 2 - left
            mosaic_top = mon.y + (mon.height - mosaic_height) // 2 - top
            # file_path, _ = os.path.split(full_name)
            for i, name in enumerate(dir_files):
                image = apply_orientation(Image.open(name))
                image = image.resize((eff_width, eff_height))
                if num_in_mosaic > 1:  # label individual pics
                    write_caption(image, name.stem, 20, 20)

                image_x = mosaic_left + eff_width * (i % num_across)
                image_y = mosaic_top + eff_height * (i // num_across)
                # print(f' Placing image {i} at {image_x}, {image_y}')
                canvas.paste(image, (image_x, image_y))
            # don't show the root folder name
            # replace slashes with middle dots - they look nicer
            caption = ' · '.join(full_name.relative_to(pics_folder).parts[:-1 if num_in_mosaic > 1 else None])
            # replace months with short names
            if target == 'phone':
                for long, short in [datetime.date(2016, m + 1, 1).strftime('%B %b').split(' ') for m in range(12)]:
                    caption = caption.replace(long, short if len(long) > 4 else long)

            if target == 'phone':
                caption_x, caption_y = 108, 75
            else:
                caption_x = mosaic_left + 20
                caption_y = mosaic_top + mosaic_height - 60
                if on_windows:
                    monitor_info = GetMonitorInfo(MonitorFromPoint((mon.x, mon.y)))
                    monitor_top, monitor_height = monitor_info['Monitor'][1::2]
                    work_area_top, work_area_height = monitor_info['Work'][1::2]
                    if monitor_top == work_area_top:
                        taskbar_height = monitor_height - work_area_height
                        caption_y -= (taskbar_height - 22)
            write_caption(canvas, caption, caption_x, caption_y)
            if target == 'phone':  # save each time rather than one big mosaic - want separate portrait/landscape images
                # Also write the date and time into the image
                now = datetime.datetime.now()
                caption = now.strftime('%d/%m %H:%M')
                write_caption(canvas, caption, caption_x, mon.height - 50)
                # Save into a numbered filename every run (max 200), in the appropriate folder (Landscape or Portrait)
                # Find the most recent
                wallpaper_subfolder = wallpaper_dir / ('Landscape' if mon_landscape else 'Portrait')
                wallpaper_subfolder.mkdir(exist_ok=True)
                image_files = []
                for filename in wallpaper_subfolder.glob('*.jpg'):
                    if 'sync-conflict' in filename:
                        # Android date issue, sync conflicts get erroneously generated every so often - safe to delete
                        print(' Removing', filename)
                        send2trash(filename)
                    else:
                        image_files.append(filename)
                if image_files:
                    newest = max(image_files, key=lambda file: file.stat().st_mtime)
                    # Increment by 1
                    file_num = (int(newest[:-4]) + 1) % 200
                else:
                    file_num = 0
                wallpaper_filename = wallpaper_subfolder / f'{file_num:03d}.jpg'
                # How long between the oldest and the newest?
                if wallpaper_filename.exists():
                    dt = now - datetime.datetime.fromtimestamp(wallpaper_filename.stat().st_mtime)
                    hours, _ = divmod(dt.seconds, 3600)
                    dt_text = f'{dt.days:d}d {hours:d}h'
                    write_caption(canvas, dt_text, mon.width - caption_x, mosaic_height - 50, align_right=True)

                print(f' Saving as {wallpaper_filename.name}')
                canvas.save(wallpaper_filename)
            break

    if target != 'phone':
        wallpaper_filename = wallpaper_dir / 'wallpaper.jpg'
        if target == 'desktop':
            for _ in range(5):
                try:
                    canvas.save(wallpaper_filename)
                    break
                except OSError as error:
                    # sometimes get 'Invalid argument' error - is the file locked?
                    if error.errno != 22:
                        raise  # something else went wrong instead!
                    time.sleep(5)
            else:  # tried 5 times and failed
                raise RuntimeError(f"Couldn't save image in {wallpaper_filename}")

        if target == 'lockscreen':  # save as lockscreen filename
            # registry key to disable changing this:
            # HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\Personalization
            canvas.save(wallpaper_dir / '00.jpg')
            # save another one, since Win10 needs >1 file in a lockscreen slideshow folder
            canvas.save(wallpaper_dir / '01.jpg')

        elif on_windows:  # use USER32 call to set a desktop background
            ctypes.windll.user32.SystemParametersInfoW(20, 0, str(wallpaper_filename), 3)


def find_mosaic_images(full_name: Path, image_size,
                       image_list: list[tuple[Path, float]], num_in_mosaic: int) -> list[Path] | None:
    if num_in_mosaic == 1:
        return [full_name]
    #     print(f" Looking for {num_in_mosaic} images with dimensions {image_size}")
    dir_files = sorted(file for file, _ in image_list if file.parent == full_name.parent)
    # Fetch files from a list starting with the chosen one and working outwards
    index = dir_files.index(full_name)
    indices = sorted(range(len(dir_files)), key=lambda j: abs(index - j))
    if len(indices) < num_in_mosaic:
        # print(f'Only {len(indices)} files in {file_path}, needed {num_in_mosaic} for mosaic')
        return None

    return_list = []
    for i in indices:
        new_im = apply_orientation(Image.open(dir_files[i]))
        if new_im.size == image_size:
            return_list.append(i)
            if len(return_list) == num_in_mosaic:
                break
    else:
        # print(f'Only found {len(return_list)} files in {file_path} with size {image_size}, needed {num_in_mosaic} for mosaic')
        return None

    return [dir_files[i] for i in sorted(return_list)]


def get_random_image(image_list: list[tuple[Path, float]]) -> Path:
    _, total_weight = image_list[-1]
    weight_index = randint(0, int(total_weight))
    return next(name for name, csize in image_list if csize >= weight_index)


def is_out_of_season(full_name: Path, today):
    file_date = datetime.date.fromtimestamp(full_name.stat().st_mtime)
    diff = abs(file_date.timetuple().tm_yday - today.timetuple().tm_yday)  # tm_yday is "day of year"
    # print(f' {diff=:}')
    return diff > 30


def find_images() -> list[tuple[Path, float]]:
    # weight by sum of size and date:
    # bigger files (likely to be better quality) get a higher weighting
    # as do more recent files (we've already seen older ones quite a lot, so they get a lower weighting)

    file_list = list(pics_folder.rglob('*.jp*g'))
    stats = [f.stat() for f in file_list]
    min_date = datetime.datetime(2002, 1, 1).timestamp()
    # for date, weighting is (minutes since first pic) - this gives a comparable number to size in bytes
    # e.g. 2019 photos will get a size weighting of order 8 million
    weights = [stat.st_size + (stat.st_mtime - min_date) / 60 for stat in stats]
    # half-weighting for photos in girls' folders (lower quality control standards!)
    bad_quality_folders = ('Emma', 'Jess')
    weights = [w / 2 if any(f.relative_to(pics_folder).parts[0] == bqf for bqf in bad_quality_folders) else w
               for f, w in zip(file_list, weights)]
    # print('total size: {:.1f} GB ({:,d} bytes)'.format(total_weight / 1024**3, total_weight))
    # with open('file_size_date_list.csv', 'w') as f:
    #     [f.write('"{}",{},{}\n'.format(n, s, d)) for n, s, d in zip(file_list, sizes, dates)]
    return list(zip(file_list, accumulate(weights)))


def create_canvas(monitors: list[screeninfo.Monitor]) -> tuple[Image, int, int]:
    left = min(m.x for m in monitors)
    right = max(m.x + m.width for m in monitors)
    top = min(m.y for m in monitors)
    bottom = max(m.y + m.height for m in monitors)
    # print(f'{left=}, {right=}, {top=}, {bottom=}')
    canvas_width, canvas_height = right - left, bottom - top
    # print(f'Canvas size: {canvas_width}x{canvas_height}')
    canvas = Image.new('RGB', (canvas_width, canvas_height), 'black')
    return canvas, left, top


def get_monitors(target: str) -> list[screeninfo.Monitor]:
    """Figure out monitor geometry."""
    if target == 'phone':
        width, height = 720, 1612  # Motorola G24
        # Change every hour i.e. ~15 per day. Run once per day now
        monitors = [screeninfo.Monitor(x=0, width=width, y=0, height=height)] * 15
        # screeninfo.Monitor(x=0, width=height, y=0, height=width)]  # landscape one for tablet screen
    else:
        monitors = screeninfo.get_monitors()  # 'windows' if on_windows else 'drm')
        if target == 'lockscreen':
            # primary monitor has coordinates (0,0)
            primaries = [mon for mon in monitors if mon.x == mon.y == 0]
            # fallback in case none have these coordinates
            monitors = primaries or monitors[:1]
    return monitors


def on_remote_desktop():
    """Check if we are on Remote Desktop - not interested in changing the lockscreen
    (it will look weird when you come back)."""
    output = b''
    try:
        # shell=True makes sure the netstat command doesn't show a console window
        # 3389 is the Remote Desktop port
        output = subprocess.Popen('netstat -n | find ":3389"', shell=True, stdout=subprocess.PIPE).stdout.read()
    except:
        pass  # ignore error
    return b'ESTABLISHED' in output


def get_wallpaper_dir(target) -> Path:
    subfolder = {'desktop': 'wallpaper', 'lockscreen': 'lockscreen', 'phone': 'phone-pics'}[target]
    wallpaper_dir = user_profile / subfolder
    wallpaper_dir.mkdir(exist_ok=True)
    return wallpaper_dir


if __name__ == '__main__':
    if len(sys.argv) <= 1:  # argument supplied?
        change_wallpaper()
    else:
        change_wallpaper(sys.argv[1])
