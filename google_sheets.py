import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# If modifying these scopes, delete the file token.pickle.
scopes = ['https://www.googleapis.com/auth/spreadsheets']

creds = None
# The file token.json stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first time.
token_file = 'google-api-token.json'
creds_file = 'google-api-credentials.json'
if os.path.exists(token_file):
    creds = Credentials.from_authorized_user_file(token_file, scopes)
# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        creds = InstalledAppFlow.from_client_secrets_file(creds_file, scopes).run_local_server(port=0)
    # Save the credentials for the next run
    open(token_file, 'w').write(creds.to_json())

# Call the Sheets API
sheets = build('sheets', 'v4', credentials=creds).spreadsheets().values()


def update_cell(sheet_id, sheet_name, cell, value):
    """Update a cell in a specified sheet with the given value."""
    payload = {'values': [[value]], 'majorDimension': "ROWS", 'range': f'{sheet_name}!{cell}'}
    sheets.update(spreadsheetId=sheet_id, range=f'{sheet_name}!{cell}', valueInputOption='USER_ENTERED', body=payload).execute(num_retries=5)


def update_cells(workbook_id, sheet_name, cell_range, values):
    """Update a cell range in a specified sheet with the given values."""
    cells = {'range': f'{sheet_name}!{cell_range}', 'values': values}
    sheets.batchUpdate(spreadsheetId=workbook_id, body={'value_input_option': 'USER_ENTERED', 'data': cells}).execute(num_retries=5)


def get_column(i):
    """Return a column label A-Z for i in the range 1-26."""
    assert i in range(1, 27)
    return chr(64 + i)
