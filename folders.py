import os

user_profile = os.environ['UserProfile' if os.name == 'nt' else 'HOME']
music_folder = os.path.join(user_profile, 'Music')
docs_folder = os.path.join(user_profile, 'STFC', 'Documents')
downloads_folder = os.path.join(user_profile, 'Downloads')
misc_folder = os.path.join(user_profile, 'Misc')
radio_folder = os.path.join(user_profile, 'Radio')
