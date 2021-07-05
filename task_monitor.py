import win32com.client
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!

scheduler = win32com.client.Dispatch('Schedule.Service')
scheduler.Connect()
root_folder = scheduler.GetFolder('\\')
toast = ''
for task_name in ('Change wallpaper', 'Change lockscreen background', 'Copy photos to phone', 'Update phone music'):
    task = root_folder.GetTask(task_name)
    if result := task.LastTaskResult != 0:
        toast += f'{task_name}, result {hex(result & (2**32-1))}\n'

if toast:
    Pushbullet(api_key).push_note('Task Monitor', toast)
