import os
from contextlib import suppress

import pandas  # also need lxml, openpyxl

from folders import downloads_folder


def get_statement(pattern: str, header_rows: int = 0, ac_no_location: tuple[int, int] | None = None) -> pandas.DataFrame:
    """Get one set of statement data."""
    files = downloads_folder.glob(pattern)
    latest = max(files, key=os.path.getmtime)

    read_file = {'.csv': pandas.read_csv,
                 '.xls': pandas.read_html,  # hack: Santander returns a .XLS file that's actually HTML
                 '.xlsx': pandas.read_excel}[latest.suffix]

    account_number = None
    with suppress(UserWarning):
        if header_rows and ac_no_location and read_file != pandas.read_html:
            header = read_file(latest, header=None, nrows=header_rows - 1)
            account_number = header.at[*ac_no_location]
        transactions = read_file(latest, header=0, skiprows=header_rows)
    if isinstance(transactions, list):  # read_html returns a list
        transactions = transactions[0]
    # Drop any rows or columns that are all N/A
    transactions = (transactions
                    .dropna(how='all', axis=0)
                    .dropna(how='all', axis=1)
                    .rename(columns={
        'Transaction Date': 'Date',
        'Transaction type': 'Type',
        'Transaction Type': 'Type',
        'Subcategory': 'Type',
        'Category': 'Type',
        'Debit Amount': 'Paid out',
        'Credit Amount': 'Paid in',
        'Money out': 'Paid out',
        'Money Out': 'Paid out',
        'Money in': 'Paid in',
        'Account/Card No': 'Account Number',
        'Card': 'Account Number',
        'Memo': 'Description',
        'Transaction Description': 'Description',
    }))
    for column in ['Paid out', 'Paid in', 'Balance']:
        if column in transactions.columns and isinstance(transactions[column].dtype, pandas.StringDtype):
            transactions[column] = transactions[column].str.replace('£', '').astype(float)
    if 'Amount' not in transactions.columns:
        transactions['Amount'] = transactions['Paid in'].fillna(0) - transactions['Paid out'].fillna(0)
    if account_number:
        transactions['Account Number'] = account_number
    transactions['Date'] = pandas.to_datetime(transactions['Date'], dayfirst=True)
    print(transactions)
    # print(transactions[transactions.columns[0]])
    min_date, max_date = transactions['Date'].min(), transactions['Date'].max()
    print(min_date, 'to', max_date)
    assert min_date.month == max_date.month
    return transactions

def get_statements():
    """Get all statement data."""
    nationwide = get_statement('Statement Download *.csv', header_rows=4, ac_no_location=(0, 1))
    lloyds = get_statement('1930*_20*_*.csv')
    barclaycard = get_statement('Transactions - 20*T*Z.csv')
    barclaycard['Amount'] = -barclaycard['Amount']  # debits are reversed!
    amex = get_statement('activity.xlsx', header_rows=6, ac_no_location=(4, 0))
    amex['Amount'] = -amex['Amount']  # debits are reversed!
    santander = get_statement('Report_*NUMERO_DE_PERSONA *.xls', header_rows=3)
    pass

if __name__ == '__main__':
    get_statements()