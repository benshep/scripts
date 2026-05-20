import re
import subprocess
from shutil import copyfile

import requests
from send2trash import send2trash
from folders import user_profile, misc_folder


def replace_in_tag(text: str, tag_name: str, new_inner: str) -> str:
    start_tag, end_tag = f'<{tag_name}>', f'</{tag_name}>'
    tag_start_pos, tag_end_pos = text.find(start_tag), text.find(end_tag)
    return text[:tag_start_pos] + start_tag + new_inner + text[tag_end_pos:]


def new_version():
    """Update get_iplayer to new version."""
    # folders
    app_name = 'get_iplayer'
    choco_name = 'getiplayer'
    app_folder = user_profile / 'GitHub' / app_name
    wiki_folder = user_profile / 'GitHub' / f'{app_name}.wiki'
    choco_folder = misc_folder / choco_name
    [send2trash(filename) for filename in choco_folder.glob('*.nupkg')]
    releases_latest = "https://api.github.com/repos/get-iplayer/get_iplayer_win32/releases/latest"

    print('Updating GitHub and wiki folders')
    assert subprocess.call('git pull', cwd=app_folder) == 0
    assert subprocess.call('git pull', cwd=wiki_folder) == 0

    nuspec_filename = choco_folder / f'{choco_name}.nuspec'
    encoding = 'utf-8'
    nuspec = nuspec_filename.read_text(encoding=encoding)

    authors = (app_folder / 'CONTRIBUTORS').read_text().replace('\n', ', ')[:-2]
    nuspec = replace_in_tag(nuspec, 'authors', authors)

    release_notes = (wiki_folder / 'releasenotes.md').read_text()
    # find first link - should point to the newest version
    for link_name, release_detail_file, anchor in re.findall(
            r'\[(.*)]\((.*)#(.*)\)', release_notes):  # e.g. [get_iplayer 3.36](release330to339#release336)
        if link_name.startswith(app_name):
            version = link_name.split(' ')[1]  # e.g. get_iplayer 3.36
            break
    else:  # didn't break out
        print('Version info not found in release notes')
        return

    print(f'{app_name} {version=}')
    nuspec = replace_in_tag(nuspec, 'version', version)

    # get info from readme
    readme = (app_folder / 'README.md').read_text().splitlines()

    # get first two sections (title and 'Features')
    description = ''
    sections = 0
    for line in readme:
        if line.startswith('## '):
            sections += 1
            if sections > 2:
                break
        description += re.sub('[<>]', '`', line) + '\n'

    nuspec = replace_in_tag(nuspec, 'description', description)

    release_notes = (wiki_folder / f'{release_detail_file}.md').read_text(encoding=encoding).splitlines()
    new_release_notes = ''
    in_section = False
    for line in release_notes:
        if line.startswith(f'<a name="{anchor}"/>'):  # look for the anchor name we found in the main release notes
            in_section = True
            continue
        if in_section:
            if line.startswith('<a name="'):  # next section
                break
            # < and > need to be escaped
            new_release_notes += re.sub('[<>]', '`', line) + '\n'

    print(new_release_notes)
    nuspec = replace_in_tag(nuspec, 'releaseNotes', new_release_notes)
    copyfile(nuspec_filename, f'{nuspec_filename}.bak')
    nuspec_filename.write_text(nuspec, encoding=encoding)

    # get binary info
    release = requests.get(releases_latest).json()
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
    install_file = choco_folder / 'tools' / 'chocolateyinstall.ps1'
    install_file.write_text(ps1_text, encoding=encoding)

    # package and push to server
    assert subprocess.call('choco pack', cwd=choco_folder) == 0
    assert subprocess.call('choco push', cwd=choco_folder) == 0


if __name__ == '__main__':
    new_version()
