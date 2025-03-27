import re
import requests
import json
from datetime import datetime, timedelta
from typing import TypedDict
import google_api
from merseyflow_auth import token, account_id

Crossing = TypedDict('Crossing', {'Direction': str,
                                  'Fare': float,
                                  'PlateNo': str,
                                  'TransactionDate': str,  # e.g. '/Date(1738496168763-0000)/'
                                  'TransactionId': int
                                  })

def get_recent_crossings(days_back=30) -> list[Crossing]:
    """Fetch data on my recent Mersey Gateway crossings from the Merseyflow website."""
    url = 'https://api-bridge.merseyflow.co.uk/GetCrossingHistory?format=json'
    now = datetime.now()
    start_date = now - timedelta(days=days_back)
    payload = {"AccountId": account_id,
               "PageSize": 50,
               "PageNumber": 1,
               "StartDate": str(start_date.date()),  # yyyy-mm-dd
               "EndDate": str(now.date()),
               "Sorting": "",
               "PlateNumber": ""
               }
    headers = {'X-Authentication-Token': token}
    response = requests.post(url, payload, headers=headers)
    response_json = json.loads(response.text)
    crossings = response_json['CrossingHistories']
    return crossings


def log_crossings():
    """Log the most recent crossings to a Google spreadsheet."""
    sheet_id = '13mso0bRg1PUVeojM2-d31yf71-3HaNfQ7cpxant7aAU'  # 🌉 Mersey Gateway spreadsheet
    sheet_name = 'Sheet1'
    headers, *data = google_api.get_data(sheet_id, sheet_name, f'A:E')
    assert headers == ['ID', 'Date', 'Direction', 'Plate number', 'Cost']
    id_list = [int(row[0].replace(',', '')) for row in data]
    new_row = len(data) + 2  # one-based when using update_cell function - this is the first empty row
    last_date = data[-1][1]

    crossings = get_recent_crossings()
    total_added = 0
    toast = ''
    for crossing in crossings:
        transaction_id = crossing['TransactionId']
        if transaction_id in id_list:
            continue
        timestamp = crossing['TransactionDate']  # e.g. '/Date(1738496168763-0000)/' - a Javascript timestamp
        match = re.match(r'/Date\((\d+)[+\-]\d+\)/', timestamp)
        crossing_date = datetime.fromtimestamp(int(match.group(1)) / 1000)
        date_str = crossing_date.strftime('%d/%m/%y %H:%M:%S')
        fare = crossing['Fare']
        row_data = [[transaction_id,
                     date_str,
                     crossing['Direction'],
                     crossing['PlateNo'],
                     fare
                     ]]
        if fare > 2.15:  # flag unexpectedly high fares
            toast += f'{date_str}: £{fare:.02f}\n'
        print(row_data)
        google_api.update_cells(sheet_id, sheet_name, f'A{new_row}:E{new_row}', row_data)
        new_row += 1
        total_added += 1
    if total_added > 0:
        toast += f'{total_added} crossings since {last_date}'
    return toast


if __name__ == '__main__':
    print(log_crossings())