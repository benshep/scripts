import os
from urllib.parse import parse_qs

import requests

from folders import pics_folder


def image_list_download():
    """Download a list of images."""
    folder = os.path.join(pics_folder, '2026', '03-01 St Helens 10k')
    os.chdir(folder)
    link_list = open('download.txt').read().splitlines()
    print(len(link_list), 'links found')
    for i, link in enumerate(link_list):
        query = parse_qs(link)
        path = query['key'][0]
        filename = os.path.basename(path)
        print(i, filename)
        response = requests.get(link)
        open(filename, 'wb').write(response.content)

if __name__ == '__main__':
    image_list_download()
