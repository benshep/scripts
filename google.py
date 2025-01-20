import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# If modifying these scopes, delete the file token.pickle.
apis_url = 'https://www.googleapis.com/auth'
scopes = [f'{apis_url}/spreadsheets', f"{apis_url}/calendar"]

creds = None
# The file token.json stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first time.
script_dir = os.path.dirname(os.path.abspath(__file__))
token_file = os.path.join(script_dir, 'google-api-token.json')
creds_file = os.path.join(script_dir, 'google-api-credentials.json')
if os.path.exists(token_file):
    creds = Credentials.from_authorized_user_file(token_file, scopes)
# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        print(os.getcwd())
        creds = InstalledAppFlow.from_client_secrets_file(creds_file, scopes).run_local_server(port=0)
    # Save the credentials for the next run
    # open(token_file, 'w').write(creds.to_json())


# Call the Sheets API
spreadsheets = build('sheets', 'v4', credentials=creds).spreadsheets()
sheets = spreadsheets.values()

# Call the Calendar API
calendar = build('calendar', 'v3', credentials=creds)


def get_data(sheet_id, sheet_name, data_range):
    """Fetch a range of data from a specified workbook and worksheet."""
    return sheets.get(spreadsheetId=sheet_id, range=f'{sheet_name}!{data_range}').execute()['values']


def update_cell(sheet_id, sheet_name, cell, value):
    """Update a cell in a specified sheet with the given value."""
    range_spec = f'{sheet_name}!{cell}' if sheet_name else cell
    payload = {'values': [[value]], 'majorDimension': "ROWS", 'range': range_spec}
    sheets.update(spreadsheetId=sheet_id, range=range_spec,
                  valueInputOption='USER_ENTERED', body=payload).execute(num_retries=5)


def update_cells(workbook_id, sheet_name, cell_range, values):
    """Update a cell range in a specified sheet with the given values."""
    cells = {'range': f'{sheet_name}!{cell_range}' if sheet_name else cell_range, 'values': values}
    sheets.batchUpdate(spreadsheetId=workbook_id,
                       body={'value_input_option': 'USER_ENTERED', 'data': cells}).execute(num_retries=5)


def fill_down(sheet_id, grid_id, start_column, column_count, from_row, fill_row_count):
    """Fill a range down from a starting row. Rows and columns are zero-based."""
    request_body = {'requests': [{'autoFill': {'useAlternateSeries': False,
                                               'sourceAndDestination': {
                                                   'source': {'sheetId': grid_id,
                                                              'startRowIndex': from_row,
                                                              'endRowIndex': from_row + 1,  # half-open
                                                              'startColumnIndex': start_column,
                                                              'endColumnIndex': start_column + column_count - 1,
                                                              }, 'dimension': 'ROWS', 'fillLength': fill_row_count}}}]}
    spreadsheets.batchUpdate(spreadsheetId=sheet_id, body=request_body).execute(num_retries=5)


def get_column(col):
    """Return a column label A-Z for i in the range 1-26, or AA-ZZ for i in the range 27-702."""
    # https://stackoverflow.com/questions/19153462/get-excel-style-column-names-from-column-number
    column_name = ''
    div = col
    while div:
        div, mod = divmod(div - 1, 26)  # will return (x, 0 .. 25)
        column_name = chr(mod + 65) + column_name
    return column_name


def get_range_spec(first_col, first_row, last_col, last_row):
    """Return a range spec like A1:E5. Rows and columns are 1-based."""
    return f'{get_column(first_col)}{first_row}:{get_column(last_col)}{last_row}'
