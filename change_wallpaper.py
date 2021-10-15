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
from random import randint, choice

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


def getFilesInPath(folder):
    """Use os.walk to get JPG files and sizes in the given folder."""
    filename_list = []
    for root, directory, files in os.walk(folder):
        filename_list += [os.path.join(root, file) for file in files if file.lower().endswith(('.jpg', '.jpeg'))]
    return filename_list


def change_wallpaper(target='desktop'):
    """Pick a random image for a new desktop wallpaper image from the user's Pictures folder.
    target can be desktop, lockscreen or phone."""
    print('\nWallpaper Changer')

    # find user's "My Documents" dir
    user_home = os.environ['USERPROFILE' if on_windows else 'HOME']
    # where pictures are kept
    pics_folder = os.path.join(user_home, 'Pictures')
    # in case it's a symlink
    try:
        pics_folder = os.readlink(pics_folder)
    except OSError:
        pass  # not a link!
    pf_len = len(pics_folder) + 1
    print(pics_folder)

    lockscreen = target == 'lockscreen'
    for_phone = target == 'phone'
    wallpaper_dir = os.path.join(user_home, 'phone-pics' if for_phone else 'lockscreen' if lockscreen else 'wallpaper')
    os.makedirs(wallpaper_dir, exist_ok=True)
    wallpaper_filename = os.path.join(wallpaper_dir, 'wallpaper.jpg')
    print(wallpaper_filename)

    if on_windows and lockscreen:
        # Check if we are on Remote Desktop - not interested in changing the lockscreen
        # (it will look weird when you come back)
        output = b''
        try:
            # shell=True makes sure the netstat command doesn't show a console window
            # 3389 is the Remote Desktop port
            output = subprocess.Popen('netstat -n | find ":3389"', shell=True, stdout=subprocess.PIPE).stdout.read()
        except:
            pass  # ignore error
        if b'ESTABLISHED' in output:
            return

    # figure out monitor geometry
    if for_phone:
        width, height = 800, 1560
        monitors = [screeninfo.Monitor(x=0, width=width, y=0, height=height),
                    screeninfo.Monitor(x=0, width=height, y=0, height=width)]  # landscape one for tablet screen
    else:
        monitors = screeninfo.get_monitors()  # 'windows' if on_windows else 'drm')
        if lockscreen:
            # primary monitor has coordinates (0,0)
            primaries = [mon for mon in monitors if mon.x == mon.y == 0]
            # fallback in case none have these coordinates
            monitors = monitors[:1] if len(primaries) == 0 else primaries

    print(monitors)
    if not monitors:
        return
    lMin = min([m.x for m in monitors])
    rMax = max([m.x + m.width for m in monitors])
    tMin = min([m.y for m in monitors])
    bMax = max([m.y + m.height for m in monitors])
    print(f'left: {lMin}, right: {rMax}, top: {tMin}, bottom: {bMax}')
    canvas_width, canvas_height = rMax - lMin, bMax - tMin
    print(f'canvas size: {canvas_width}x{canvas_height}')
    canvas = Image.new('RGB', (canvas_width, canvas_height), 'black')

    # weight by sum of size and date:
    # bigger files (likely to be better quality) get a higher weighting
    # as do more recent files (we've already seen older ones quite a lot, so they get a lower weighting)
    file_list = getFilesInPath(pics_folder)
    sizes = [os.path.getsize(f) for f in file_list]
    dates = [os.path.getmtime(f) for f in file_list]
    min_date = min(dates)
    # for date, weighting is (minutes since first pic) - this gives a comparable number to size in bytes
    # e.g. 2019 photos will get a size weighting of order 8 million
    weights = [s + (d - min_date) / 60 for s, d in zip(sizes, dates)]
    # half-weighting for photos in girls' folders (lower quality control standards!)
    weights = [w / 2 if ('\\Jess\\' in f or '\\Emma\\' in f) else w for f, w in zip(file_list, weights)]
    cumulative_weight = list(accumulate(weights))
    image_list = list(zip(file_list, cumulative_weight))
    total_weight = int(cumulative_weight[-1])
    # print('total size: {:.1f} GB ({:,d} bytes)'.format(total_weight / 1024**3, total_weight))
    # with open('file_size_date_list.csv', 'w') as f:
    #     [f.write('"{}",{},{}\n'.format(n, s, d)) for n, s, d in zip(file_list, sizes, dates)]

    # font: Segoe UI, as on Windows logon screen, or Roboto for phone screen, or Ubuntu
    font_name = 'Roboto-Regular' if for_phone else 'segoeui' if on_windows else 'Ubuntu-R'
    font = ImageFont.truetype(font_name + '.ttf', 24)

    def write_caption(im, text, x, y, align_right=False):
        draw = ImageDraw.Draw(im)
        if align_right:
            w, h = draw.textsize(text, font=font)
            x -= w
        print(f'Caption "{text}" at {x}, {y}')
        # put a black drop shadow behind so the text can be read on any background
        draw.text((x + 1, y + 1), text, 'black', font=font)
        draw.text((x, y), text, 'white', font=font)

    # read in exclude list
    exclude_list = [line.rstrip('\n') for line in open(os.path.join(pics_folder, 'exclude.txt'), 'r')]
    # ensure each item with a path separator uses the correct one for this OS
    exclude_list = [item.replace('\\', os.sep).replace('/', os.sep) for item in exclude_list]

    today = datetime.date.today()

    for mon in monitors:
        # Want a seasonal image? (one that was taken in the same month)
        # Only do this in holiday periods
        seasonal = today.month in (4, 5, 8, 10, 12)  # choice((True, False))

        print('\nmonitor', mon)
        # portrait or landscape?
        mon_landscape = mon.width > mon.height
        print(f"{mon.width}x{mon.height}, {mon_landscape=}")
        if for_phone:  # separate canvases for each phone 'monitor' (landscape and portrait)
            canvas = Image.new('RGB', (mon.width, mon.height), 'black')

        found_correct_ornt = False
        rotate_angle = 0

        while not found_correct_ornt:
            weight_index = randint(0, total_weight)
            full_name = next(name for name, csize in image_list if csize >= weight_index)

            # for debugging!
            # full_name = r"C:\Users\bjs54\Pictures\WhatsApp\IMG-20190225-WA0003.jpg"
            # seasonal = False

            print(f"{full_name}, {weight_index:,d}")
            if any(exc in full_name for exc in exclude_list):
                print('on excluded list')
                continue

            if seasonal:
                file_date = datetime.date.fromtimestamp(os.path.getmtime(full_name))
                diff = abs(file_date.replace(year=today.year) - today)
                print(f'{diff.days=:}')
                if datetime.timedelta(days=30) < diff < datetime.timedelta(days=335):
                    continue

            image = apply_orientation(Image.open(full_name))

            im_width, im_height = image.size
            print(f"{im_width}x{im_height}")  # returns (width, height) tuple
            im_landscape = im_width > im_height
            print(f'{im_landscape=}')

            # calculate factor to scale larger images down - is 1 if image is smaller
            # just use height for phone - chop off left/right borders if necessary
            width_sf = 1 if (for_phone and not im_landscape) else (mon.width / im_width)
            height_sf = 1 if (for_phone and im_landscape) else (mon.height / im_height)
            scale_factor = min(width_sf, height_sf, 1)
            eff_width, eff_height = int(im_width * scale_factor), int(im_height * scale_factor)
            print(f"scaled image size: {eff_width}x{eff_height}")

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
            width_sf = 1 if (for_phone and not im_landscape) else (mon.width / mosaic_width)
            height_sf = 1 if (for_phone and im_landscape) else (mon.height / mosaic_height)
            scale_factor = min(width_sf, height_sf, 1)
            mosaic_width, mosaic_height = int(scale_factor * mosaic_width), int(scale_factor * mosaic_height)
            eff_width, eff_height = int(eff_width * scale_factor), int(eff_height * scale_factor)
            print(f"rescaled image size: {eff_width}x{eff_height}")

            print(f"mosaic dimensions: {mosaic_width}x{mosaic_height}")
            print(f"number of images: {num_across}x{num_down}")
            num_in_mosaic = num_across * num_down
            if for_phone and num_in_mosaic > 1:
                print('only one image wanted for phone screen!')
                continue

            file_path, filename = os.path.split(full_name)
            print(f"looking for {num_in_mosaic} images with dimensions {im_width}x{im_height}")

            dir_files = [os.path.basename(name) for name, fsize in image_list if os.path.dirname(name) == file_path]
            dir_indices = [dir_files.index(filename)]
            i = dir_indices[0]
            direction = 1
            while len(dir_indices) < num_in_mosaic and not direction == 0:
                i += direction
                if i == len(dir_files):
                    direction = -1
                    i = dir_indices[0]
                    continue
                elif i == -1:
                    direction = 0
                    break
                new_im = apply_orientation(Image.open(os.path.join(file_path, dir_files[i])))
                new_im_width, new_im_height = new_im.size
                if new_im_width == im_width and new_im_height == im_height:
                    print(f"adding {dir_files[i]} {new_im_width}x{new_im_height}")
                    dir_indices.insert(0 if direction == -1 else len(dir_indices), i)

            if direction == 0:  # didn't find enough
                print(f'only found {len(dir_indices)}, needed {num_in_mosaic}')
                continue

            found_correct_ornt = True
            print(f"resizing images to {eff_width}x{eff_height}")
            mosaic_left = mon.x + (mon.width - mosaic_width) // 2 - lMin
            mosaic_top = mon.y + (mon.height - mosaic_height) // 2 - tMin
            for i, index in enumerate(dir_indices):
                image = apply_orientation(Image.open(os.path.join(file_path, dir_files[index])))
                image = image.resize((eff_width, eff_height))
                if num_in_mosaic > 1:  # label individual pics
                    write_caption(image, dir_files[index], 20, 20)

                image_x = mosaic_left + eff_width * (i % num_across)
                image_y = mosaic_top + eff_height * (i // num_across)
                print(f'placing image {i} at {image_x}, {image_y}')
                canvas.paste(image, (image_x, image_y))
                # Deal with the secondary monitor being above / to the left of the primary
                # It means we need an extra 'strip' of image at the bottom/left of the rest
                # No - shouldn't need to do that any more
                # if image_x < 0 and not for_phone:
                # print('... and at {}, {}'.format(canvas_width + image_x, image_y))
                # canvas.paste(image, (canvas_width + image_x, image_y))
                # if image_y < 0 and not for_phone:
                # print('... and at {}, {}'.format(image_x, canvas_height + image_y))
                # canvas.paste(image, (image_x, canvas_height + image_y))
            # don't show the root folder name
            # replace slashes with middle dots - they look nicer
            caption = (file_path if num_in_mosaic > 1 else full_name)[pf_len:].replace(os.path.sep, ' · ')
            # replace months with short names
            if for_phone:
                for long_month, short_month in [datetime.date(2016, m + 1, 1).strftime('%B %b').split(' ') for m in
                                                range(12)]:
                    caption = caption.replace(long_month, short_month)

            caption_x, caption_y = (108, 60) if for_phone else (mosaic_left + 20, mosaic_top + mosaic_height - 60)
            write_caption(canvas, caption, caption_x, caption_y)
            if for_phone:  # save each time rather than one big mosaic - want separate portrait/landscape images
                # Also write the date and time into the image
                now = datetime.datetime.now()
                caption = now.strftime('%d/%m %H:%M')
                write_caption(canvas, caption, caption_x, mon.height - 60)
                # Save into a numbered filename every run (max 200), in the appropriate folder (Landscape or Portrait)
                # Find the most recent
                wallpaper_subfolder = os.path.join(wallpaper_dir, 'Landscape' if mon_landscape else 'Portrait')
                os.makedirs(wallpaper_subfolder, exist_ok=True)
                os.chdir(wallpaper_subfolder)
                try:
                    newest = max([f for f in os.listdir('.') if f[-3:] == 'jpg'], key=os.path.getmtime)
                    # Increment by 1
                    file_num = (int(newest[:-4]) + 1) % 200
                except ValueError:  # max throws exception if dir listing is empty
                    file_num = 0
                wallpaper_filename = '{:03d}.jpg'.format(file_num)
                # How long between the oldest and the newest?
                not_found_exception = WindowsError if on_windows else FileNotFoundError
                try:
                    dt = now - datetime.datetime.fromtimestamp(os.path.getmtime(wallpaper_filename))
                    hours, rem = divmod(dt.seconds, 3600)
                    dt_text = '{:d}d {:d}h'.format(dt.days, hours)
                    write_caption(canvas, dt_text, mon.width - caption_x, mosaic_height - 60, align_right=True)
                except not_found_exception:
                    pass  # this file doesn't exist - never mind

                print(f'Saving as {wallpaper_filename}')
                canvas.save(wallpaper_filename)

    if not for_phone:
        if not lockscreen:
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

        if lockscreen:  # save as lockscreen filename - symlinked from C:\Windows\System32\oobe\INFO\backgrounds (Windows 7)
            os.chdir(wallpaper_dir)
            wallpaper_filename = '00.jpg'
            # file can be no more than 256kB (Windows 7 limitation, lifted in Windows 10)
            q = 75  # default
            canvas.save(wallpaper_filename, quality=q)
            # while os.path.getsize(wallpaper_filename) > 250 * 1024 and q > 0:
            #     q -= 5
            #     print('resaving with quality', q)
            #     canvas.save(wallpaper_filename, quality=q)
            canvas.save('01.jpg', quality=q)  # save another one, since Win10 needs >1 file in a lockscreen slideshow folder

        elif on_windows:  # use USER32 call to set desktop background
            ctypes.windll.user32.SystemParametersInfoW(20, 0, wallpaper_filename, 3)
        else:
            pass # subprocess.Popen('nitrogen --restore', shell=True)


if __name__ == '__main__':
    if len(sys.argv) <= 1:  # argument supplied?
        change_wallpaper()
    else:
        change_wallpaper(sys.argv[1])

