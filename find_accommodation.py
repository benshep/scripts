import os
from time import sleep

from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.common.by import By

from sheffield_credentials import username, password

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
    print(location_selector.text)
    report = ''
    for label in location_selector.find_elements(By.XPATH, '//label'):
        if target in label.text:
            label.click()
            results = web.find_elements(By.CLASS_NAME, 'ui-card-result')
            report = f'{len(results)} rooms available in {target}'
            break
    web.quit()
    return report

if __name__ == '__main__':
    report = flat_search(show_window=True)
    print(report)