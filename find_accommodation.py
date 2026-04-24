import os
import re
from time import sleep

import urllib.parse
import requests
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.common.by import By

from sheffield_credentials import username, password

prices = {  # https://sheffield.ac.uk/accommodation/rents
    'Birchen Apartments': ('En-suite', '£195.72'),
    'Burbage Apartments': ('En-suite', '£195.72'),
    'Cratcliffe Apartments': ('En-suite', '£195.72'),
    'Curbar Apartments': ('En-suite', '£195.72'),
    'Derwent Apartments': ('En-suite', '£195.72'),
    'Froggatt Apartments': ('En-suite', '£195.72'),
    'Howden Apartments': ('En-suite', '£195.72'),
    'Kinder Apartments': ('En-suite', '£195.72'),
    'Lawrencefield Apartments': ('En-suite', '£195.72'),
    'Millstone Apartments': ('En-suite', '£195.72'),
    'Ramshaw Apartments': ('En-suite', '£195.72'),
    'Ravenstone Apartments': ('En-suite', '£195.72'),
    'Rivelin Apartments': ('En-suite', '£195.72'),
    'Stanage Apartments': ('En-suite', '£195.72'),
    'Wimberry Apartments': ('En-suite', '£195.72'),
    'Windgather Apartments': ('En-suite', '£195.72'),
    'Yarncliffe Apartments': ('En-suite', '£195.72'),
    'Kinder Studios': ('Studios', '£227.68'),
    'Windgather Studios': ('Studios', '£227.68'),
    'Wimberry Studios': ('Studios', '£227.68'),
    'Laddow Studios': ('Studio', '£240.38'),
    'Crescent Flats': ('Shared Bathroom', '£151.41'),
    'Endcliffe Vale Flats': ('Shared Bathroom', '£151.41'),
    'Crewe Flats': ('Shared Bathroom', '£151.90 - £162.33'),
    'Endcliffe Crescent Houses': ('Shared Bathroom', '£157.10 - £174.89'),
    'Stephenson': ('Shared bathroom, catered', '£194.46'),
}


def flat_search(show_window: bool = False):
    """Open the University of Sheffield accommodation booking page, and check which rooms are available."""
    target = 'Endcliffe Vale Flats'

    if not show_window:  # try to open an invisible browser window
        os.environ['MOZ_HEADLESS'] = '1'
    print('Logging in to accommodation website')
    web = WebDriver()
    web.implicitly_wait(60)  # add an automatic wait to the browser handling
    params = {'UrlToken': '63296FB3', 'LowerRoomRateValue': 0, 'UpperRoomRateValue': 0, 'TermID': 244,
              'ClassificationID': 11, 'RoomLocationAreaID': 7, 'CurrentPageNumber': 1,
              'DateStart': '20 September 2026', 'DateEnd': '11 July 2027'}
    path = '/StarRezPortalX/53ED1745/10/462/Accommodation_Applic-Room_List?'
    quoted_address = urllib.parse.quote_plus(path + urllib.parse.urlencode(params))
    url = 'https://sheffield.starrezhousing.com/StarRezPortalX/Login?returnUrl=' + quoted_address

    web.get(url)
    web.find_element(By.CLASS_NAME, 'ui-btn-external-provider').click()
    web.find_element(By.CLASS_NAME, 'ui-btn-external-provider').click()
    web.find_element(By.ID, 'username').send_keys(username)
    web.find_element(By.ID, 'password').send_keys(password)
    web.find_element(By.ID, 'submitBtn').click()
    sleep(2)
    web.get(url)
    location_selector = web.find_element(By.CLASS_NAME, 'ui-room-selection-location-filter')
    availability = get_availability()
    max_length = max(len(name) for name in prices)
    for line in location_selector.text.splitlines():
        name = line[:-11] if line.endswith(' Apartments') else line
        print('\t'.join([
            line,
            *prices.get(line, ('', '')),
            availability.get(name, '')
        ]).expandtabs(max_length + 2))
    report = ''
    for label in location_selector.find_elements(By.XPATH, '//label'):
        if target in label.text:
            label.click()
            results = web.find_elements(By.CLASS_NAME, 'ui-card-result')
            report = f'{len(results)} rooms available in {target}'
            break
    web.quit()
    return report


def get_availability() -> dict[str, str]:
    """Fetch the accommodation availability page, and return a dict with percentage availability for each flat type."""
    url = 'https://sheffield.ac.uk/accommodation/availability'
    response = requests.get(url)
    table_matches = re.findall(r'<td>([^<]*?)</td><td>[^&]*?</td><td>(\d\d?%)</td>', response.text)
    return {name: availability for name, availability in table_matches}


if __name__ == '__main__':
    # print(*get_availability().items(), sep='\n')
    # max_length = max(len(name) for name in prices)
    # for name, info in prices.items():
    #     print('\t'.join([name, *info]).expandtabs(max_length + 2))
    report = flat_search(show_window=True)
    print(report)
