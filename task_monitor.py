import win32com.client
from platform import node
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!

scheduler = win32com.client.Dispatch('Schedule.Service')
scheduler.Connect()
toast = '\n'.join(f'{task.Name}' for task in
                  scheduler.GetFolder('Monitored').GetTasks(0) if task.LastTaskResult == 1)

if toast:
    Pushbullet(api_key).push_note(f'👁️ Failed tasks {node()}', toast)
