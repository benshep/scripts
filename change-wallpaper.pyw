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
                    places in phone-pics\Landscape and phone-pics\Portrait folders of user profile dir (max 200)
                    to be synced outside this script
"""

import os
on_windows = os.name == 'nt'
import screeninfo
from math import ceil #calculation of mosaic dimensions
from random import randint, choice
from PIL import Image, ImageDraw, ImageFont
from itertools import accumulate
import datetime
from time import time
import sys
import subprocess
import ctypes
if on_windows:
    import ctypes.wintypes

def getFilesInPath(folder):
    """Use os.walk to get JPG files and sizes in the given folder."""
    file_list = []
    for root, dir, files in os.walk(folder):
        file_list.extend([os.path.join(root, file) for file in files if file.lower().endswith(('.jpg', '.jpeg'))])
    return file_list

print('\nWallpaper Changer')

# find user's "My Documents" dir
user_home = os.environ['USERPROFILE' if on_windows else 'HOME']
# where pictures are kept
pics_folder = os.path.join(user_home, 'Pictures')
# in case it's a symlink
try:
    pics_folder = os.readlink(pics_folder)
except:
    pass # not a link!
pf_len = len(pics_folder) + 1
print(pics_folder)

lockscreen = 'lockscreen' in sys.argv
for_phone = 'phone' in sys.argv
wallpaper_folder = os.path.join(user_home, ('phone-pics' if for_phone else 'wallpaper'))
wallpaper_filename = os.path.join(wallpaper_folder, ('lockscreen.jpg' if lockscreen else 'wallpaper.jpg'))
print(wallpaper_filename)

if on_windows and lockscreen:
    # Check if we are on Remote Desktop - not interested in changing the lockscreen
    # (it will look weird when you come back)
    output = b''
    try:
        # shell=True makes sure the netstat command doesn't show a console window
        output = subprocess.Popen('netstat -n', shell=True, stdout=subprocess.PIPE).stdout.read()
    except:
        pass #ignore error
    if b':3389' in output:
        raise NotImplementedError('on Remote Desktop, not changing lockscreen')

# Get EXIF orientation and transpose the image accordingly
# http://stackoverflow.com/questions/4228530/pil-thumbnail-is-rotating-my-image
def flip_horizontal(im): return im.transpose(Image.FLIP_LEFT_RIGHT)
def flip_vertical(im): return im.transpose(Image.FLIP_TOP_BOTTOM)
def rotate_180(im): return im.transpose(Image.ROTATE_180)
def rotate_90(im): return im.transpose(Image.ROTATE_90)
def rotate_270(im): return im.transpose(Image.ROTATE_270)
def transpose(im): return rotate_90(flip_horizontal(im))
def transverse(im): return rotate_90(flip_vertical(im))
orientation_funcs = [None,
                 lambda x: x,
                 flip_horizontal,
                 rotate_180,
                 flip_vertical,
                 transpose,
                 rotate_270,
                 transverse,
                 rotate_90]
                
def apply_orientation(im):
    """
    Extract the orientation EXIF tag from the image, which should be a PIL Image instance,
    and if there is an orientation tag that would rotate the image, apply that rotation to
    the Image instance given to do an in-place rotation.

    :param Image im: Image instance to inspect
    :return: A possibly transposed image instance
    """

    try:
        kOrientationEXIFTag = 0x0112
        if hasattr(im, '_getexif'): # only present in JPEGs
            e = im._getexif()       # returns None if no EXIF data
            if e is not None:
                #log.info('EXIF data found: %r', e)
                orientation = e[kOrientationEXIFTag]
                f = orientation_funcs[orientation]
                return f(im)
    except:
        # We'd be here with an invalid orientation value or some random error?
        pass # log.exception("Error applying EXIF Orientation tag")
    return im

# figure out monitor geometry
if for_phone:
    width = 720 #540
    height = 1280 #960
    monitors = [screeninfo.Monitor(x=0, width=width, y=0, height=height)]
else:
    monitors = screeninfo.get_monitors('windows' if on_windows else 'drm')
    if lockscreen:
        # primary monitor has coordinates (0,0)
        primaries = [mon for mon in monitors if mon.x == mon.y == 0]
        # fallback in case none have these coordinates
        monitors = monitors[0:1] if len(primaries) == 0 else primaries

print(monitors)
lMin = min([m.x for m in monitors])
rMax = max([m.x + m.width for m in monitors])
tMin = min([m.y for m in monitors])
bMax = max([m.y + m.height for m in monitors])
print('left:', lMin, 'right:', rMax, 'top:', tMin, 'bottom:', bMax)
canvas_width = rMax - lMin
canvas_height = bMax - tMin
print('canvas size', canvas_width, 'x', canvas_height)
canvas = Image.new('RGB', (canvas_width, canvas_height), 'black')

file_list = getFilesInPath(pics_folder)
cumulative_size = list(accumulate([os.path.getsize(f) for f in file_list]))
image_list = list(zip(file_list, cumulative_size))
total_size = cumulative_size[-1]
print('total size: {:.1f} GB ({:,d} bytes)'.format(total_size / 1024**3, total_size))

# font: Segoe UI, as on Windows logon screen, or Roboto for phone screen, or Ubuntu
if for_phone:
    font_name = 'Roboto-Regular.ttf'
elif on_windows:
    font_name = 'segoeui.ttf'
else:
    font_name = 'Ubuntu-R.ttf'
font = ImageFont.truetype(font_name, 28)
def write_caption(image, caption, x, y):
    draw = ImageDraw.Draw(image)
    # put a black drop shadow behind so the text can be read on any background
    draw.text((x + 1, y + 1), caption, 'black', font=font)    
    draw.text((x, y), caption, 'white', font=font)    
        
# read in exclude list
exclude_list = [line.rstrip('\n') for line in open(os.path.join(pics_folder, 'exclude.txt'), 'r')]

today = datetime.date.today()

for mon in monitors:
    # Want a seasonal image? (one that was taken in the same month)
    seasonal = choice((True, False))
    
    print('\nmonitor', mon)
    # portrait or landscape?
    mon_landscape = mon.width > mon.height
    print(mon.width, 'x', mon.height, 'landscape?', mon_landscape)
    if for_phone: # separate canvases for each phone 'monitor' (landscape and portrait)
        canvas = Image.new('RGB', (mon.width, mon.height), 'black')

    found_correct_ornt = False
    rotate_angle = 0
    
    while not found_correct_ornt:
        size_index = randint(0, total_size)
        full_name = next(name for name, csize in image_list if csize >= size_index)
        
        # for debugging!
#        file_path = r"E:\Pictures\2015\Lake District - Easter"
#        filename = 'P1130971.JPG'
#        seasonal = False
        
        print(full_name, '{:,d}'.format(size_index))
        if any(exc in full_name for exc in exclude_list):
            print('on excluded list')
            continue
        
        if seasonal:
            file_date = datetime.date.fromtimestamp(os.path.getmtime(full_name))
            days_diff = abs(file_date.replace(year=today.year) - today)
            if days_diff > datetime.timedelta(days=30):
                print('not seasonal enough! days_diff = ', days_diff)
                continue
        
        im = apply_orientation(Image.open(full_name))
        
        im_width, im_height = im.size
        print(im_width, 'x', im_height) # returns (width, height) tuple
        im_landscape = im_width > im_height
        print('landscape?',im_landscape)
        
        # calculate factor to scale larger images down - is 1 if image is smaller
        # just use height for phone - chop off left/right borders if necessary
        width_sf = 1 if for_phone else (mon.width / im_width)
        height_sf = mon.height / im_height
        scale_factor = min(width_sf, height_sf, 1)
        eff_width, eff_height = int(im_width * scale_factor), int(im_height * scale_factor)
        print('scaled image size:', eff_width, 'x', eff_height)
        
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
        width_sf = 1 if for_phone else (mon.width / mosaic_width)
        height_sf = mon.height / mosaic_height
        scale_factor = min(width_sf, height_sf, 1)
        mosaic_width, mosaic_height = int(scale_factor * mosaic_width), int(scale_factor * mosaic_height)
        eff_width, eff_height = int(eff_width * scale_factor), int(eff_height * scale_factor)
        print('rescaled image size:', eff_width, 'x', eff_height)
        
        print('mosaic dimensions', mosaic_width, 'x', mosaic_height)
        print('number of images:', num_across, 'x', num_down)
        num_in_mosaic = num_across * num_down
        if for_phone and num_in_mosaic > 1:
            print('only one image wanted for phone screen!')
            continue
        
        file_path, filename = os.path.split(full_name)
        print('looking for', num_in_mosaic, 'images with same dimensions')

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
                print('adding', dir_files[i])
                dir_indices.insert(0 if direction == -1 else len(dir_indices), i)
    
        if direction == 0: #didn't find enough
            print("only found", len(dir_indices), 'needed', num_in_mosaic)
            continue

        found_correct_ornt = True
        print('resizing images to', eff_width, 'x', eff_height)
        mosaic_left = mon.x + (mon.width - mosaic_width) // 2
        mosaic_top = mon.y + (mon.height - mosaic_height) // 2
        for i, index in enumerate(dir_indices):
            im = apply_orientation(Image.open(os.path.join(file_path, dir_files[index])))
            im = im.resize((eff_width, eff_height))
            if num_in_mosaic > 1: #label individual pics
                write_caption(im, dir_files[index], 20, 20)         

            image_x = mosaic_left + eff_width * (i % num_across)
            image_y = mosaic_top + eff_height * (i // num_across)
            print('placing image {} at {}, {}'.format(i, image_x, image_y))
            canvas.paste(im, (image_x, image_y))
            # Deal with the secondary monitor being above / to the left of the primary
            # It means we need an extra 'strip' of image at the bottom/left of the rest
            if image_x < 0 and not for_phone:
                print('... and at {}, {}'.format(canvas_width + image_x, image_y))
                canvas.paste(im, (canvas_width + image_x, image_y))
            if image_y < 0 and not for_phone:
                print('... and at {}, {}'.format(image_x, canvas_height + image_y))
                canvas.paste(im, (image_x, canvas_height + image_y))
        # don't show the root folder name
        # replace slashes with middle dots - they look nicer
        caption = (file_path if num_in_mosaic > 1 else full_name)[pf_len:].replace(os.path.sep, ' · ')
        # replace months with short names
        if for_phone:
            for long_month, short_month in [datetime.date(2016, m+1, 1).strftime('%B %b').split(' ') for m in range(12)]:
                caption = caption.replace(long_month, short_month)
            
        caption_x = 30 if for_phone else mosaic_left + 20
        caption_y = mosaic_top + (60 if for_phone else mosaic_height - 60)
        write_caption(canvas, caption, caption_x, caption_y)
        if for_phone: # save each time rather than one big mosaic - want separate portrait/landscape images
            # Also write the date and time into the image
            caption = datetime.datetime.now().strftime('%d/%m %H:%M')
            write_caption(canvas, caption, caption_x, mosaic_height - 60)
            # Save into a numbered filename every run (max 200), in the appropriate folder (Landscape or Portrait)
            # Find the most recent
            os.chdir(os.path.join(wallpaper_folder, 'Landscape' if mon_landscape else 'Portrait'))
            newest = max([f for f in os.listdir('.') if f[-3:] == 'jpg'], key=os.path.getmtime)
            # Increment by 1
            file_num = (int(newest[:-4]) + 1) % 200
            wallpaper_filename = '{:03d}.jpg'.format(file_num)
            print('Saving as', wallpaper_filename)
            canvas.save(wallpaper_filename)
            
if not for_phone:
    canvas.save(wallpaper_filename)
    
    if lockscreen: #save as lockscreen filename - symlinked from C:\Windows\System32\oobe\INFO\backgrounds
        # file can be no more than 256kB (Windows limitation)
        q = 75 #default
        while os.path.getsize(wallpaper_filename) > 250 * 1024 and q > 0:
            q -= 5
            print('resaving with quality', q)
            canvas.save(wallpaper_filename, quality=q)
        
    elif on_windows: #use USER32 call to set desktop background
        ctypes.windll.user32.SystemParametersInfoW(20, 0, wallpaper_filename, 3)

    else:
        subprocess.Popen('nitrogen --restore', shell=True)
