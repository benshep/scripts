# Update get_iplayer to new version

import subprocess
import os
from shutil import copyfile
import requests
from send2trash import send2trash


def replace_in_tag(text, tag_name, new_inner):
    start_tag, end_tag = f'<{tag_name}>', f'</{tag_name}>'
    tag_start_pos, tag_end_pos = text.find(start_tag), text.find(end_tag)
    return text[:tag_start_pos] + start_tag + new_inner + text[tag_end_pos:]


def new_version():
    # folders
    user_dir = os.environ['UserProfile']
    app_name = 'get_iplayer'
    choco_name = 'getiplayer'
    app_folder = os.path.join(user_dir, 'GitHub', app_name)
    wiki_folder = f'{app_folder}.wiki'
    choco_folder = os.path.join(user_dir, 'OneDrive - Science and Technology Facilities Council',
                                'Documents', 'Scripts', choco_name)
    os.chdir(choco_folder)
    [send2trash(filename) for filename in os.listdir() if filename.endswith('.nupkg')]

    print('Updating GitHub and wiki folders')
    assert subprocess.call('git pull', cwd=app_folder) == 0
    assert subprocess.call('git pull', cwd=wiki_folder) == 0

    nuspec_filename = os.path.join(choco_folder, f'{choco_name}.nuspec')
    encoding = 'utf-8'
    nuspec = open(nuspec_filename, encoding=encoding).read()

    authors = open(os.path.join(app_folder, 'CONTRIBUTORS')).read().replace('\n', ', ')[:-2]
    nuspec = replace_in_tag(nuspec, 'authors', authors)

    release_notes = open(os.path.join(wiki_folder, 'releasenotes.md')).read().splitlines()

    # find first link - should point to the newest version
    for line in release_notes:
        start_pos, mid_pos, end_pos = line.find('['), line.find(']('), line.find(')')
        if -1 in (start_pos, mid_pos, end_pos):
            continue
        link_name = line[start_pos+1:mid_pos]
        link_dest = line[mid_pos+2:end_pos]
        if link_name.startswith(app_name):
            version = link_name.split(' ')[1]
            break

    print(f'{app_name} {version=}')
    nuspec = replace_in_tag(nuspec, 'version', version)

    # get info from readme
    readme = open(os.path.join(app_folder, 'README.md')).read().splitlines()

    # get first two sections (title and 'Features')
    description = ''
    sections = 0
    for line in readme:
        if line.startswith('## '):
            sections += 1
            if sections > 2:
                break
        description += line.replace('<', '`').replace('>', '`') + '\n'

    nuspec = replace_in_tag(nuspec, 'description', description)

    release_notes_file, link_name = link_dest.split('#')
    release_notes = open(os.path.join(wiki_folder, f'{release_notes_file}.md'), encoding=encoding).read().splitlines()

    new_release_notes = ''
    in_section = False
    for line in release_notes:
        if line.startswith(f'<a name="{link_name}"/>'):
            in_section = True
            continue
        if in_section:
            if line.startswith('<a name="'):  # next section
                break
            # < and > need to be escaped
            new_release_notes += line.replace('<', '`').replace('>', '`') + '\n'

    print(new_release_notes)
    nuspec = replace_in_tag(nuspec, 'releaseNotes', new_release_notes)
    copyfile(nuspec_filename, f'{nuspec_filename}.bak')
    open(nuspec_filename, 'w', encoding=encoding).write(nuspec)

    # get binary info
    json = requests.get("https://api.github.com/repos/get-iplayer/get_iplayer_win32/releases/latest").content
    release = eval(json.replace(b'false', b'False')
                   .replace(b'null', b'None')
                   .replace(b'true', b'True'))

    urls = [asset['browser_download_url'] for asset in release['assets']]

    def get_url_sha(arch):
        suffix = f'-x{arch}-setup.exe'
        address = next(url for url in urls if url.endswith(suffix))
        checksum_url = next(url for url in urls if f'{suffix}.sha' in url)
        checksum = requests.get(checksum_url).content.decode(encoding).split(' ')[0]
        checksum_type = checksum_url.split('.')[-1]
        return address, checksum, checksum_type

    x86_url, x86_checksum, x86_checksum_type = get_url_sha('86')
    x64_url, x64_checksum, x64_checksum_type = get_url_sha('64')
    ps1_text = f'''
$ErrorActionPreference = 'Stop';

$packageName= '{choco_name}'
$toolsDir   = "$(Split-Path -parent $MyInvocation.MyCommand.Definition)"
$url        = '{x86_url}'
$url64      = '{x64_url}'

$packageArgs = @{{
  packageName   = $packageName
  unzipLocation = $toolsDir
  fileType      = 'exe'
  url           = $url
  url64bit      = $url64

  softwareName  = '{choco_name}*'

  checksum      = '{x86_checksum}'
  checksumType  = '{x86_checksum_type}'
  checksum64    = '{x64_checksum}'
  checksumType64= '{x64_checksum_type}'

  silentArgs   = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-'
}}

Install-ChocolateyPackage @packageArgs
'''
    print('Updating the exe URL and checksums in the install file')
    install_file = os.path.join(choco_folder, 'tools', 'chocolateyinstall.ps1')
    open(install_file, 'w', encoding=encoding).write(ps1_text)

    # package and push to server
    assert subprocess.call('choco pack', cwd=choco_folder) == 0
    assert subprocess.call('choco push', cwd=choco_folder) == 0


if __name__ == '__main__':
    new_version()
