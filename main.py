from dotenv import load_dotenv
import email
import imaplib
import os
import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Optional
from time import sleep
from requests.adapters import HTTPAdapter, Retry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

EMAIL_USERNAME = os.getenv("EMAIL")
EMAIL_PASSWORD = os.getenv("PASSWORD")
IMAP_SERVER = "imap.gmail.com"
SEARCH_CRITERIA = '(BODY "unsubscribe")'

class EmailProcessor:
    """Processes email content to find and access unsubscribe links."""

    def __init__(self):
        self.mail = self._establish_email_connection()

    def _establish_email_connection(self) -> imaplib.IMAP4_SSL:
        """Establishes a connection to the email server and logs in."""
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER)
            mail.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            mail.select("inbox")
            logging.info("Successfully connected to the email inbox.")
            return mail
        except imaplib.IMAP4.error as e:
            logging.error(f"Failed to connect to the email server: {e}")
            raise

    def _fetch_email_data(self, email_id: str) -> Optional[email.message.Message]:
        """Fetches and returns email data by email ID."""
        try:
            _, data = self.mail.fetch(email_id, "(RFC822)")
            return email.message_from_bytes(data[0][1])
        except Exception as e:
            logging.error(f"Failed to fetch email ID {email_id}: {e}")
            return None

    def _parse_html_for_links(self, html_content: str) -> List[str]:
        """Extracts unsubscribe links from HTML content."""
        soup = BeautifulSoup(html_content, 'html.parser')
        return [link['href'] for link in soup.find_all('a', href=True) if "unsubscribe" in link["href"].lower()]

    def find_unsubscribe_links(self) -> List[str]:
        """Searches emails for unsubscribe links and returns a list of those links."""
        try:
            _, search_data = self.mail.search(None, SEARCH_CRITERIA)
            email_ids = search_data[0].split()
            unsubscribe_links = []

            for email_id in email_ids:
                msg = self._fetch_email_data(email_id)
                if msg:
                    unsubscribe_links.extend(self._extract_links_from_email(msg))

            logging.info(f"Total unsubscribe links found: {len(unsubscribe_links)}")
            return unsubscribe_links
        finally:
            self.mail.logout()
            logging.info("Logged out from the email server.")

    def _extract_links_from_email(self, msg: email.message.Message) -> List[str]:
        """Extracts unsubscribe links from a single email."""
        unsubscribe_links = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html_content = part.get_payload(decode=True)
                    unsubscribe_links.extend(self._parse_html_for_links(html_content))
        else:
            content = msg.get_payload(decode=True).decode()
            if msg.get_content_type() == "text/html":
                unsubscribe_links.extend(self._parse_html_for_links(content))
        return unsubscribe_links

class LinkHandler:
    """Handles HTTP requests to access unsubscribe links."""

    def __init__(self, retries: int = 3, backoff_factor: float = 0.3):
        self.session = self._setup_session(retries, backoff_factor)

    def _setup_session(self, retries: int, backoff_factor: float) -> requests.Session:
        """Sets up an HTTP session with retry logic."""
        session = requests.Session()
        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def access_links(self, links: List[str]):
        """Attempts to access each unsubscribe link."""
        for link in links:
            try:
                response = self.session.get(link, timeout=10)
                if response.status_code == 200:
                    logging.info(f"Successfully accessed unsubscribe link: {link}")
                else:
                    logging.warning(f"Failed to access unsubscribe link: {link} (Status: {response.status_code})")
            except requests.RequestException as e:
                logging.error(f"Error accessing link {link}: {e}")

    def __del__(self):
        self.session.close()

def main():
    email_processor = EmailProcessor()
    unsubscribe_links = email_processor.find_unsubscribe_links()

    if unsubscribe_links:
        link_handler = LinkHandler()
        link_handler.access_links(unsubscribe_links)
    else:
        logging.info("No unsubscribe links found.")

if __name__ == "__main__":
    main()
