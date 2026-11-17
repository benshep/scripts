from selenium import webdriver
from selenium.webdriver.common.by import By

from lebara_credentials import username, password

def get_phone_usage():
    """Log in to Lebara and download phone usage (calls, texts, data).
    Record usage to Google Sheets."""
    web = webdriver.Edge()
    web.get('https://www.lebara.co.uk/en/mylebara/register.html')
    web.find_element(By.ID, 'onetrust-accept-btn-handler').click()
    web.find_element(By.ID, 'email').send_keys(username)
    web.find_element(By.ID, 'password').send_keys(password)
    input('Fulfil reCAPTCHA prompt:')
    web.find_element(By.CLASS_NAME, 'css-a3ce8k').click()

    web.quit()

if __name__ == '__main__':
    get_phone_usage()
