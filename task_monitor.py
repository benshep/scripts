import win32com.client
from platform import node
# from pushbullet import Pushbullet  # to show notifications
# from pushbullet_api_key import api_key  # local file, keep secret!


def check_tasks():
    scheduler = win32com.client.Dispatch('Schedule.Service')
    scheduler.Connect()
    toast = '\n'.join(f'{task.Name}' for task in
                      scheduler.GetFolder('Monitored').GetTasks(0) if task.LastTaskResult == 1)

    if toast:
        Pushbullet(api_key).push_note(f'👁️ Failed tasks {node()}', toast)


def walk_task_folders():
    # https://stackoverflow.com/questions/36634214/python-check-for-completed-and-failed-task-windows-scheduler#answer-36635050
    import win32com.client

    TASK_ENUM_HIDDEN = 1
    TASK_STATE = {0: 'Unknown',
                  1: 'Disabled',
                  2: 'Queued',
                  3: 'Ready',
                  4: 'Running'}

    scheduler = win32com.client.Dispatch('Schedule.Service')
    scheduler.Connect()

    n = 0
    folders = [scheduler.GetFolder('\\')]
    while folders:
        folder = folders.pop(0)
        folders += list(folder.GetFolders(0))
        tasks = list(folder.GetTasks(TASK_ENUM_HIDDEN))
        n += len(tasks)
        for task in tasks:
            if task.Definition.Settings.WakeToRun:
                print(f'{task.Path}')
            # print(f'Path       : {task.Path}')
            # print(f'Hidden     : {settings.Hidden}')
            # print(f'State      : {TASK_STATE[task.State]}')
            # print(f'Last Run   : {task.LastRunTime}')
            # print(f'Last Result: {task.LastTaskResult}\n')
    print('Listed %d tasks.' % n)


if __name__ == '__main__':
    walk_task_folders()
