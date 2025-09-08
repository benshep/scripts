import os

user_profile = os.path.expanduser('~')
downloads_folder = os.path.join(user_profile, 'Downloads')

music_folder = os.path.join(user_profile, 'Music')
misc_folder = os.path.join(user_profile, 'Misc')
radio_folder = os.path.join(user_profile, 'Radio')
docs_folder = os.path.join(user_profile, 'STFC', 'Documents')
if os.path.exists(docs_folder):
    hr_info_folder = os.path.join(user_profile, 'UKRI', 'Science and Technology Facilities Council - HR')
else:  # not on a work PC
    docs_folder = None
    hr_info_folder = None
