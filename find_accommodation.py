import os
import re
from time import sleep

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
    target = 'Endcliffe Vale'

    if not show_window:  # try to open an invisible browser window
        os.environ['MOZ_HEADLESS'] = '1'
    web = WebDriver()
    web.implicitly_wait(10)  # add an automatic wait to the browser handling
    web.get('https://sheffield.starrezhousing.com/StarRezPortalX/Login?returnUrl=%2FStarRezPortalX%2F53ED1745%2F10%2F462%2FAccommodation_Applic-Room_List%3FUrlToken%3D63296FB3%26LowerRoomRateValue%3D0%26UpperRoomRateValue%3D0%26TermID%3D244%26ClassificationID%3D11%26RoomLocationAreaID%3D7%26CurrentPageNumber%3D1%26DateStart%3D20%2520September%25202026%26DateEnd%3D11%2520July%25202027&isContact=False')
    web.find_element(By.CLASS_NAME, 'ui-btn-external-provider').click()
    web.find_element(By.CLASS_NAME, 'ui-btn-external-provider').click()
    web.find_element(By.ID, 'username').send_keys(username)
    web.find_element(By.ID, 'password').send_keys(password)
    web.find_element(By.ID, 'submitBtn').click()
    for element in web.find_elements(By.CLASS_NAME, 'ui-nav-process'):
        if element.text == 'Accommodation Application':
            element.click()
            break
    for element in web.find_elements(By.CLASS_NAME, 'sr_button_primary'):
        if element.text == 'CONTINUE':
            element.click()
            break
    sleep(60)
    web.find_element(By.XPATH, '//button[@aria-label="Select Ranmoor/Endcliffe"]').click()
    sleep(60)
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
    report = flat_search(show_window=False)
    print(report)