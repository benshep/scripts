import win32com.client
from platform import node
from pushbullet import Pushbullet  # to show notifications
from pushbullet_api_key import api_key  # local file, keep secret!

scheduler = win32com.client.Dispatch('Schedule.Service')
scheduler.Connect()
toast = '\n'.join(f'{task.Name}, result {hex(task.LastTaskResult & (2 ** 32 - 1))}' for task in
                  scheduler.GetFolder('Monitored').GetTasks(0) if task.LastTaskResult)

if toast:
    Pushbullet(api_key).push_note(f'👁️ Task Monitor {node()}', toast)
