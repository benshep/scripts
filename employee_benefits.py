import os

from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By
from googleapiclient.discovery import build
import google
import benefits_credentials

benefits_sheet = '1o6Y41H0RAZXNxhNJlVqHh-xlATaVdst2T1QuWctf-MM'


def get_benefits(test_mode=True):
    if not test_mode:
        os.environ['MOZ_HEADLESS'] = '1'
    web = webdriver.Firefox()
    web.maximize_window()
    web.implicitly_wait(10)
    get_vivup(web)
    get_lebara(web)
    web.quit()


def get_vivup(web):
    vivup_url = 'https://ukri.vivup.co.uk/organisations/2885-uk-research-and-innovation-ukri/employee/lifestyle_savings/products?results_per_page=120'
    web.get(vivup_url)
    web.find_element(By.ID, 'email').send_keys(benefits_credentials.vivup['username'])
    web.find_element(By.ID, 'password').send_keys(benefits_credentials.vivup['password'])
    web.find_element(By.XPATH, '//div[@class="MuiBox-root css-rp2cmc"]/button').click()  # Sign in
    # web.find_element(By.LINK_TEXT, 'Enter a Two-factor Backup/Recovery code').click()
    # web.find_element(By.ID, 'user_recovery_attempt').send_keys(benefits_credentials.vivup['recovery_code'])
    # web.find_element(By.XPATH, '//div[@class="col-md-offset-3 col-md-9"]/input').click()
    sleep(10)  # wait for email to arrive
    # pythoncom.CoInitialize()  # try to combat the "CoInitialize has not been called" error
    # outlook = win32com.client.Dispatch('Outlook.Application')
    # namespace = outlook.GetNamespace('MAPI')
    # inbox = namespace.GetDefaultFolder(6)
    emails = build('gmail', 'v1', credentials=google.google_creds()).users().messages()
    results = emails.list(userId='me', labelIds=['INBOX'], q='subject:"Vivup - Please verify your device"').execute()
    messages = results.get('messages', [])
    msg = emails.get(userId='me', id=messages[0]['id']).execute()
    # otp_emails = inbox.Items.Restrict("[Subject] = 'Vivup - Please verify your device'")
    # otp_emails.Sort("[CreationTime]", True)
    # body = otp_emails[0].Body
    find_text = 'One-Time Password (OTP) token: '
    snippet = msg['snippet']
    str_pos = snippet.index(find_text)
    otp_token = snippet[str_pos + len(find_text): str_pos + len(find_text) + 6]
    print(f'{otp_token=}')
    web.find_element(By.ID, 'user_otp_attempt').send_keys(otp_token)
    web.find_element(By.XPATH, '//div[@class="col-md-offset-3 col-md-9"]/input').click()  # Login
    web.find_element(By.LINK_TEXT, 'View All').click()
    result_summary = web.find_element(By.XPATH,
                                      '//p[@class="MuiTypography-root MuiTypography-body1 css-z4pozx"]/strong')
    total_results = int(result_summary.text.split(' ')[-1])  # e.g. 1 - 120 of 831
    stored_names, stored_values = get_stored_benefits('Vivup')
    new_row = len(stored_names) + 2
    for page in range(total_results + 1):
        web.get(f'{vivup_url}&page={page + 1}')
        sleep(5)
        page_text = web.find_elements(By.CLASS_NAME, 'shiitake-children')
        page_names = [element.text for element in page_text[::2]]
        page_values = [element.text for element in page_text[1::2]]
        for name, value in zip(page_names, page_values):
            if name in stored_names:
                index = stored_names.index(name)
                if stored_values[index] != value:
                    print(f'Update for {name}: {value}')
                    google.update_cell(benefits_sheet, 'Vivup', f'B{index + 2}', value)
                    sleep(1)  # quota limit: 60/min
            else:
                print(f'New: {name}: {value}')
                google.update_cell(benefits_sheet, 'Vivup', f'A{new_row}', name)
                google.update_cell(benefits_sheet, 'Vivup', f'B{new_row}', value)
                new_row += 1
                sleep(2)  # quota limit: 60/min


def get_stored_benefits(sheet_name):
    stored_names = [row[0] for row in google.get_data(benefits_sheet, sheet_name, 'A2:A')]
    stored_values = [row[0] for row in google.get_data(benefits_sheet, sheet_name, 'B2:B')]
    return stored_names, stored_values


def get_lebara(web: webdriver.Firefox):
    page = 1
    stored_names, stored_values = get_stored_benefits('Lebara')
    new_row = len(stored_names) + 2
    while True:
        lebara_url = f'https://rewards.lebara.co.uk/all-offers?page={page}'
        web.get(lebara_url)
        titles = [element.text for element in web.find_elements(By.CLASS_NAME, 'perk-title')]
        if not titles:
            break
        descriptions = [element.text for element in web.find_elements(By.CLASS_NAME, 'perk-pill')]
        for name, value in zip(titles, descriptions):
            if name in stored_names:
                index = stored_names.index(name)
                if stored_values[index] != value:
                    print(f'Update for {name}: {value}')
                    google.update_cell(benefits_sheet, 'Lebara', f'B{index + 2}', value)
                    sleep(1)  # quota limit: 60/min
            else:
                print(f'New: {name}: {value}')
                google.update_cell(benefits_sheet, 'Lebara', f'A{new_row}', name)
                google.update_cell(benefits_sheet, 'Lebara', f'B{new_row}', value)
                new_row += 1
                sleep(2)  # quota limit: 60/min
        page += 1


if __name__ == '__main__':
    get_benefits(test_mode=True)
