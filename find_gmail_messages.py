import os
from time import sleep
import google_api


def list_messages():
    log_file = 'message_counter.txt'
    counter = {}
    if os.path.exists(log_file):
        for line in open(log_file).read().splitlines():
            from_address, count = line.split('\t')
            counter[from_address] = count
    service = google_api.build('gmail', 'v1', credentials=google_api.creds)
    messages_api = service.users().messages()
    next_page_token = ''
    log = open(log_file, 'a')
    while True:
        all_mail = messages_api.list(userId='me', q='', pageToken=next_page_token, maxResults=500).execute()  # 5 quota units
        print(len(all_mail['messages']), 'messages listed')
        for message in all_mail['messages']:
            # usage limit: 250 quota units per second, moving average
            sleep(20 / 250)
            message_detail = messages_api.get(userId='me', id=message['id']).execute()  # 5 quota units
            try:
                from_address = next(h['value'] for h in message_detail['payload']['headers'] if h['name'] == 'From')
            except StopIteration:  # no from address(?)
                continue
            if '<' in from_address:  # strip out Name <from@server.com>
                from_address = from_address[from_address.find('<') + 1:from_address.find('>')]
            if from_address in counter:
                continue
            msgs_from_this = messages_api.list(userId='me', q=f'from:{from_address}').execute()  # 5 quota units
            message_count = msgs_from_this['resultSizeEstimate']
            counter[from_address] = message_count
            log.write(f'{from_address}\t{message_count}\n')
            if message_count > 200:
                print(from_address)
        if 'nextPageToken' not in all_mail:
            break
        next_page_token = all_mail['nextPageToken']
    log.close()


if __name__ == '__main__':
    list_messages()
