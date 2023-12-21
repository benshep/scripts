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
from itertools import accumulate
from math import ceil  # calculation of mosaic dimensions
from random import randint

import screeninfo
from PIL import Image, ImageDraw, ImageFont

on_windows = os.name == 'nt'
if on_windows:
    import ctypes.wintypes

# Get EXIF orientation and transpose the image accordingly
# http://stackoverflow.com/questions/4228530/pil-thumbnail-is-rotating-my-image

flip_horizontal = lambda im: im.transpose(Image.FLIP_LEFT_RIGHT)
flip_vertical = lambda im: im.transpose(Image.FLIP_TOP_BOTTOM)
rotate_180 = lambda im: im.transpose(Image.ROTATE_180)
rotate_90 = lambda im: im.transpose(Image.ROTATE_90)
rotate_270 = lambda im: im.transpose(Image.ROTATE_270)
transpose = lambda im: im.rotate_90(flip_horizontal(im))
transverse = lambda im: im.rotate_90(flip_vertical(im))
orientation_funcs = [None, lambda x: x, flip_horizontal, rotate_180,
                     flip_vertical, transpose, rotate_270, transverse, rotate_90]


def apply_orientation(im):
    """
    Extract the orientation EXIF tag from the image, which should be a PIL Image instance,
    and if there is an orientation tag that would rotate the image, apply that rotation to
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


def change_wallpaper(target='desktop'):
    """Pick a random image for a new desktop wallpaper image from the user's Pictures folder.
    target can be desktop, lockscreen or phone."""
    print(f'Wallpaper Changer, {target=}')

    pics_folder, wallpaper_dir = get_folders(target)
    pf_len = len(pics_folder) + 1

    if on_windows and target == 'lockscreen' and on_remote_desktop():
        return

    monitors = get_monitors(target)
    # print(monitors)
    if not monitors:
        return
    canvas, left, top = create_canvas(monitors)

    image_list = find_images(pics_folder)

    # font: Segoe UI, as on Windows logon screen, or Roboto for phone screen, or Ubuntu
    font_name = 'Roboto-Regular' if target == 'phone' else 'segoeui' if on_windows else 'Ubuntu-R'
    font = ImageFont.truetype(f'{font_name}.ttf', 24)

    def write_caption(im, text, x, y, align_right=False):
        draw = ImageDraw.Draw(im)
        print(f' Caption "{text}" at {x}, {y}')
        # put a black drop shadow behind so the text can be read on any background
        anchor = 'rt' if align_right else 'lt'  # top left or top right
        draw.text((x + 1, y + 1), text, 'black', font=font, anchor=anchor)
        draw.text((x, y), text, 'white', font=font, anchor=anchor)

    exclude_list = get_exclude_list(pics_folder)

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
            if any(exc in full_name for exc in exclude_list):
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

            dir_files = find_mosaic_images(full_name, image.size, image_list, num_in_mosaic)
            if dir_files is None:
                continue

            print(f" Resizing {num_in_mosaic} images to {eff_width}x{eff_height} each")
            mosaic_left = mon.x + (mon.width - mosaic_width) // 2 - left
            mosaic_top = mon.y + (mon.height - mosaic_height) // 2 - top
            file_path, _ = os.path.split(full_name)
            for i, name in enumerate(dir_files):
                image = apply_orientation(Image.open(os.path.join(file_path, name)))
                image = image.resize((eff_width, eff_height))
                if num_in_mosaic > 1:  # label individual pics
                    write_caption(image, name, 20, 20)

                image_x = mosaic_left + eff_width * (i % num_across)
                image_y = mosaic_top + eff_height * (i // num_across)
                # print(f' Placing image {i} at {image_x}, {image_y}')
                canvas.paste(image, (image_x, image_y))
            # don't show the root folder name
            # replace slashes with middle dots - they look nicer
            caption = (file_path if num_in_mosaic > 1 else full_name)[pf_len:].replace(os.path.sep, ' · ')
            # replace months with short names
            if target == 'phone':
                for long, short in [datetime.date(2016, m + 1, 1).strftime('%B %b').split(' ') for m in range(12)]:
                    caption = caption.replace(long, short)

            caption_x, caption_y = (108, 60) if target == 'phone' else (
            mosaic_left + 20, mosaic_top + mosaic_height - 60)
            write_caption(canvas, caption, caption_x, caption_y)
            if target == 'phone':  # save each time rather than one big mosaic - want separate portrait/landscape images
                # Also write the date and time into the image
                now = datetime.datetime.now()
                caption = now.strftime('%d/%m %H:%M')
                write_caption(canvas, caption, caption_x, mon.height - 60)
                # Save into a numbered filename every run (max 200), in the appropriate folder (Landscape or Portrait)
                # Find the most recent
                wallpaper_subfolder = os.path.join(wallpaper_dir, 'Landscape' if mon_landscape else 'Portrait')
                os.makedirs(wallpaper_subfolder, exist_ok=True)
                os.chdir(wallpaper_subfolder)
                image_files = [f for f in os.listdir('.') if f[-3:] == 'jpg']
                if image_files:
                    newest = max(image_files, key=os.path.getmtime)
                    # Increment by 1
                    file_num = (int(newest[:-4]) + 1) % 200
                else:
                    file_num = 0
                wallpaper_filename = f'{file_num:03d}.jpg'
                # How long between the oldest and the newest?
                if os.path.exists(wallpaper_filename):
                    dt = now - datetime.datetime.fromtimestamp(os.path.getmtime(wallpaper_filename))
                    hours, _ = divmod(dt.seconds, 3600)
                    dt_text = f'{dt.days:d}d {hours:d}h'
                    write_caption(canvas, dt_text, mon.width - caption_x, mosaic_height - 60, align_right=True)

                print(f' Saving as {wallpaper_filename}')
                canvas.save(wallpaper_filename)
            break

    if target != 'phone':
        wallpaper_filename = os.path.join(wallpaper_dir, 'wallpaper.jpg')
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
            os.chdir(wallpaper_dir)
            canvas.save('00.jpg')
            canvas.save('01.jpg')  # save another one, since Win10 needs >1 file in a lockscreen slideshow folder

        elif on_windows:  # use USER32 call to set desktop background
            ctypes.windll.user32.SystemParametersInfoW(20, 0, wallpaper_filename, 3)


def find_mosaic_images(full_name, image_size, image_list, num_in_mosaic):
    file_path, filename = os.path.split(full_name)
    if num_in_mosaic == 1:
        return [filename]
    #     print(f" Looking for {num_in_mosaic} images with dimensions {image_size}")
    dir_files = [os.path.basename(name) for name, _ in image_list if os.path.dirname(name) == file_path]
    # Fetch files from list starting with the chosen one and working outwards
    index = dir_files.index(filename)
    indices = sorted(range(len(dir_files)), key=lambda j: abs(index - j))
    if len(indices) < num_in_mosaic:
        # print(f'Only {len(indices)} files in {file_path}, needed {num_in_mosaic} for mosaic')
        return None

    return_list = []
    for i in indices:
        new_im = apply_orientation(Image.open(os.path.join(file_path, dir_files[i])))
        if new_im.size == image_size:
            return_list.append(i)
            if len(return_list) == num_in_mosaic:
                break
    else:
        # print(f'Only found {len(return_list)} files in {file_path} with size {image_size}, needed {num_in_mosaic} for mosaic')
        return None

    return [dir_files[i] for i in sorted(return_list)]


def get_random_image(image_list):
    _, total_weight = image_list[-1]
    weight_index = randint(0, int(total_weight))
    return next(name for name, csize in image_list if csize >= weight_index)


def is_out_of_season(full_name, today):
    file_date = datetime.date.fromtimestamp(os.path.getmtime(full_name))
    diff = abs(file_date.timetuple().tm_yday - today.timetuple().tm_yday)  # tm_yday is "day of year"
    # print(f' {diff=:}')
    return diff > 30


def get_exclude_list(pics_folder):
    # read in exclude list
    exclude_list = [line.rstrip('\n') for line in open(os.path.join(pics_folder, 'exclude.txt'), 'r')]
    # ensure each item with a path separator uses the correct one for this OS
    exclude_list = [item.replace('\\', os.sep).replace('/', os.sep) for item in exclude_list]
    return exclude_list


def find_images(pics_folder):
    # weight by sum of size and date:
    # bigger files (likely to be better quality) get a higher weighting
    # as do more recent files (we've already seen older ones quite a lot, so they get a lower weighting)
    file_list = [os.path.join(root, file) for root, _, files in os.walk(pics_folder)
                 for file in files if file.lower().endswith(('.jpg', '.jpeg'))]
    sizes = [os.path.getsize(f) for f in file_list]
    dates = [os.path.getmtime(f) for f in file_list]
    min_date = min(dates)
    # for date, weighting is (minutes since first pic) - this gives a comparable number to size in bytes
    # e.g. 2019 photos will get a size weighting of order 8 million
    weights = [s + (d - min_date) / 60 for s, d in zip(sizes, dates)]
    # half-weighting for photos in girls' folders (lower quality control standards!)
    bad_quality_folders = tuple(os.path.join(pics_folder, name) for name in ('Emma', 'Jess'))
    weights = [w / 2 if f.startswith(bad_quality_folders) else w for f, w in zip(file_list, weights)]
    # print('total size: {:.1f} GB ({:,d} bytes)'.format(total_weight / 1024**3, total_weight))
    # with open('file_size_date_list.csv', 'w') as f:
    #     [f.write('"{}",{},{}\n'.format(n, s, d)) for n, s, d in zip(file_list, sizes, dates)]
    return list(zip(file_list, accumulate(weights)))


def create_canvas(monitors):
    left = min(m.x for m in monitors)
    right = max(m.x + m.width for m in monitors)
    top = min(m.y for m in monitors)
    bottom = max(m.y + m.height for m in monitors)
    # print(f'{left=}, {right=}, {top=}, {bottom=}')
    canvas_width, canvas_height = right - left, bottom - top
    # print(f'Canvas size: {canvas_width}x{canvas_height}')
    canvas = Image.new('RGB', (canvas_width, canvas_height), 'black')
    return canvas, left, top


def get_monitors(target):
    """Figure out monitor geometry."""
    if target == 'phone':
        width, height = 800, 1560
        monitors = [screeninfo.Monitor(x=0, width=width, y=0, height=height),
                    screeninfo.Monitor(x=0, width=height, y=0, height=width)]  # landscape one for tablet screen
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


def get_folders(target):
    # find user's "My Documents" dir
    user_home = os.environ['UserProfile' if on_windows else 'HOME']
    # where pictures are kept
    pics_folder = os.path.join(user_home, 'Pictures')
    # in case it's a symlink
    try:
        pics_folder = os.readlink(pics_folder)
    except OSError:
        pass  # not a link!
    # print(pics_folder)
    subfolder = {'desktop': 'wallpaper', 'lockscreen': 'lockscreen', 'phone': 'phone-pics'}[target]
    wallpaper_dir = os.path.join(user_home, subfolder)
    os.makedirs(wallpaper_dir, exist_ok=True)
    return pics_folder, wallpaper_dir


if __name__ == '__main__':
    if len(sys.argv) <= 1:  # argument supplied?
        change_wallpaper()
    else:
        change_wallpaper(sys.argv[1])
