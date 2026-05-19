from pathlib import Path

user_profile = Path('~').expanduser()
downloads_folder = user_profile.joinpath('Downloads')

music_folder = user_profile.joinpath('Music')
misc_folder = user_profile.joinpath('Misc')
pics_folder = user_profile.joinpath('Pictures')
radio_folder = user_profile.joinpath('Radio')
docs_folder = user_profile.joinpath('STFC', 'Documents')
if docs_folder.exists():
    hr_info_folder = user_profile.joinpath('UKRI', 'Science and Technology Facilities Council - HR')
else:  # not on a work PC
    docs_folder = None
    hr_info_folder = None
