"""
Management command to scrape NLL transactions from nll.com
"""
import os
from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
from datetime import datetime
from web.models import NLLTransaction, Player, Team as NLLTeam


def scrape_nll_transactions_task(headless=True):
    """
    Scrape NLL transactions from nll.com
    Returns count of transactions scraped
    """
    try:
        # Set up Chrome options
        chrome_options = webdriver.ChromeOptions()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--single-process')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # Initialize driver
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        
        driver.get('https://www.nll.com/news/transactions/')
        
        # Wait for page to load
        time.sleep(3)
        
        # Try to find transaction elements
        wait = WebDriverWait(driver, 10)
        
        # Look for common transaction container patterns
        try:
            # Wait for transaction items to load
            wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'transaction')))
            transactions_html = driver.find_elements(By.CLASS_NAME, 'transaction')
        except:
            # If that doesn't work, try alternate selectors
            try:
                wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'news-item')))
                transactions_html = driver.find_elements(By.CLASS_NAME, 'news-item')
            except:
                # Try to get all article elements
                transactions_html = driver.find_elements(By.TAG_NAME, 'article')
        
        # Get page HTML for manual parsing
        page_html = driver.page_source
        
        # Save HTML to file for inspection
        with open('transactions_page.html', 'w', encoding='utf-8') as f:
            f.write(page_html)
        
        driver.quit()
        
        return len(transactions_html), page_html
        
    except Exception as e:
        raise Exception(f'Error during scraping: {str(e)}')


class Command(BaseCommand):
    help = 'Scrape NLL transactions from nll.com'

    def add_arguments(self, parser):
        parser.add_argument(
            '--headless',
            action='store_true',
            help='Run browser in headless mode',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting NLL transactions scrape...'))
        
        try:
            count, html = scrape_nll_transactions_task(headless=options.get('headless', True))
            self.stdout.write(self.style.SUCCESS(f'Scraped {count} potential transactions'))
            self.stdout.write(self.style.SUCCESS('Saved page HTML to transactions_page.html for inspection'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during scraping: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
