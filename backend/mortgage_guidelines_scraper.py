#!/usr/bin/env python3
"""
Mortgage Guidelines Scraper - Real-time scraping from my.mortgageguidelines.com
Automatically logs in and retrieves the latest guideline updates
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import hashlib
import logging
import re
from typing import List, Dict, Optional
from database import SessionLocal
from guideline_updates_models import GuidelineUpdate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MortgageGuidelinesScraper:
    """Scraper for my.mortgageguidelines.com with authentication"""

    BASE_URL = "https://my.mortgageguidelines.com"
    LOGIN_URL = f"{BASE_URL}/account-login/"

    # Credentials
    USERNAME = "tloss@cmghomeloans.com"
    PASSWORD = "Woodwindow00!"

    # Source URLs after login
    SOURCES = {
        'fannie_mae': '/fannie-mae-updates/',
        'freddie_mac': '/freddie-mac-updates/',
        'fha': '/fha-updates/',
        'va': '/va-updates/',
        'usda': '/usda-updates/'
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.is_logged_in = False

    def login(self) -> bool:
        """
        Log into my.mortgageguidelines.com
        Returns True if login successful
        """
        try:
            logger.info("Attempting to log in to Mortgage Guidelines...")

            # First, get the login page to retrieve any CSRF tokens
            login_page = self.session.get(self.LOGIN_URL)
            soup = BeautifulSoup(login_page.content, 'html.parser')

            # Look for CSRF token or nonce
            csrf_token = None
            csrf_input = soup.find('input', {'name': 'csrf_token'}) or \
                        soup.find('input', {'name': '_wpnonce'}) or \
                        soup.find('input', {'name': 'token'})

            if csrf_input:
                csrf_token = csrf_input.get('value')
                logger.info(f"Found CSRF token: {csrf_token[:20]}...")

            # Prepare login data
            login_data = {
                'username': self.USERNAME,
                'password': self.PASSWORD,
                'log': self.USERNAME,  # WordPress often uses 'log' for username
                'pwd': self.PASSWORD,  # WordPress often uses 'pwd' for password
                'wp-submit': 'Log In',
                'redirect_to': self.BASE_URL,
                'testcookie': '1'
            }

            if csrf_token:
                login_data['_wpnonce'] = csrf_token
                login_data['csrf_token'] = csrf_token

            # Attempt login
            response = self.session.post(
                self.LOGIN_URL,
                data=login_data,
                allow_redirects=True
            )

            # Check if login was successful
            # Look for logout link or user dashboard
            if 'logout' in response.text.lower() or 'dashboard' in response.text.lower() or 'my account' in response.text.lower():
                logger.info("✅ Successfully logged in to Mortgage Guidelines!")
                self.is_logged_in = True
                return True
            else:
                logger.warning("⚠️  Login may have failed - checking session...")
                # Sometimes login succeeds but redirect doesn't show those keywords
                # Try accessing a protected page
                test_response = self.session.get(f"{self.BASE_URL}/fannie-mae-updates/")
                if test_response.status_code == 200 and 'login' not in test_response.url.lower():
                    logger.info("✅ Session is valid!")
                    self.is_logged_in = True
                    return True
                else:
                    logger.error("❌ Login failed - please check credentials")
                    return False

        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return False

    def parse_update_date(self, date_str: str) -> datetime:
        """Parse various date formats from the website"""
        try:
            # Try common formats
            formats = [
                '%B %d, %Y',      # January 15, 2024
                '%b %d, %Y',      # Jan 15, 2024
                '%m/%d/%Y',       # 01/15/2024
                '%Y-%m-%d',       # 2024-01-15
                '%d %B %Y',       # 15 January 2024
            ]

            date_str = date_str.strip()

            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue

            # If all else fails, return recent date
            logger.warning(f"Could not parse date: {date_str}, using current date")
            return datetime.utcnow()

        except Exception as e:
            logger.error(f"Date parsing error: {e}")
            return datetime.utcnow()

    def scrape_source_updates(self, source_name: str, source_path: str, limit: int = 5) -> List[Dict]:
        """
        Scrape updates from a specific source page
        Returns list of update dictionaries
        """
        if not self.is_logged_in:
            logger.error("Not logged in! Call login() first.")
            return []

        updates = []

        try:
            url = f"{self.BASE_URL}{source_path}"
            logger.info(f"Scraping {source_name} from {url}...")

            response = self.session.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for update entries - adjust selectors based on actual HTML structure
            # Common patterns for update listings
            update_containers = (
                soup.find_all('article', class_=re.compile(r'post|update|entry')) or
                soup.find_all('div', class_=re.compile(r'post|update|entry|item')) or
                soup.find_all('li', class_=re.compile(r'post|update|entry'))
            )

            if not update_containers:
                # Try finding by heading tags
                update_containers = soup.find_all(['h2', 'h3'], limit=limit * 2)
                logger.info(f"Found {len(update_containers)} heading-based containers")

            logger.info(f"Found {len(update_containers)} potential updates for {source_name}")

            for container in update_containers[:limit]:
                try:
                    # Extract title
                    title_elem = (
                        container.find(['h1', 'h2', 'h3', 'h4']) or
                        container.find('a', class_=re.compile(r'title|headline'))
                    )

                    if title_elem:
                        title = title_elem.get_text(strip=True)
                    else:
                        title = container.get_text(strip=True)[:100]

                    if not title or len(title) < 5:
                        continue

                    # Extract URL
                    link_elem = container.find('a', href=True)
                    if link_elem:
                        update_url = link_elem['href']
                        if not update_url.startswith('http'):
                            update_url = f"{self.BASE_URL}{update_url}"
                    else:
                        update_url = url

                    # Extract date
                    date_elem = (
                        container.find('time') or
                        container.find(class_=re.compile(r'date|time|published')) or
                        container.find('span', class_=re.compile(r'date|time'))
                    )

                    if date_elem:
                        date_str = date_elem.get('datetime') or date_elem.get_text(strip=True)
                        published_date = self.parse_update_date(date_str)
                    else:
                        # Default to recent date if not found
                        published_date = datetime.utcnow() - timedelta(days=len(updates))

                    # Extract description/excerpt
                    desc_elem = (
                        container.find('p') or
                        container.find(class_=re.compile(r'excerpt|summary|description'))
                    )

                    description = desc_elem.get_text(strip=True)[:500] if desc_elem else title

                    # Extract section code if present (e.g., "SEL-2024-08", "ML 2024-11")
                    section_code = None
                    code_match = re.search(r'(SEL|ML|CIRC|BULL|RD)[\s-]?\d{4}[-]?\d{1,2}', title, re.IGNORECASE)
                    if code_match:
                        section_code = code_match.group(0)

                    update = {
                        'source': source_name,
                        'title': title,
                        'section_code': section_code,
                        'description': description,
                        'url': update_url,
                        'published_date': published_date,
                        'is_new': True
                    }

                    updates.append(update)
                    logger.info(f"  ✅ {source_name}: {title[:60]}... ({published_date.date()})")

                except Exception as e:
                    logger.error(f"Error parsing update container: {e}")
                    continue

            logger.info(f"Successfully scraped {len(updates)} updates from {source_name}")

        except Exception as e:
            logger.error(f"Error scraping {source_name}: {e}")

        return updates

    def scrape_all_sources(self, limit_per_source: int = 5) -> int:
        """
        Scrape all guideline sources and save to database
        Returns number of new updates added
        """
        # Login first
        if not self.is_logged_in:
            if not self.login():
                logger.error("Failed to login - cannot scrape")
                return 0

        db = SessionLocal()
        total_added = 0

        try:
            for source_name, source_path in self.SOURCES.items():
                logger.info(f"\n{'='*60}")
                logger.info(f"Scraping {source_name.upper()}...")
                logger.info(f"{'='*60}")

                updates = self.scrape_source_updates(source_name, source_path, limit_per_source)

                for update_data in updates:
                    # Generate unique hash
                    content_hash = hashlib.sha256(
                        f"{update_data['title']}{update_data['url']}".encode()
                    ).hexdigest()

                    update_data['content_hash'] = content_hash

                    # Check if already exists
                    existing = db.query(GuidelineUpdate).filter_by(
                        content_hash=content_hash
                    ).first()

                    if existing:
                        logger.info(f"  ⏭️  Already exists: {update_data['title'][:50]}...")
                        continue

                    try:
                        # Add new update
                        new_update = GuidelineUpdate(**update_data)
                        db.add(new_update)
                        db.commit()
                        total_added += 1
                        logger.info(f"  ✅ Added: {update_data['title'][:50]}...")
                    except Exception as e:
                        db.rollback()
                        logger.error(f"  ❌ Error adding update: {e}")

            logger.info(f"\n{'='*60}")
            logger.info(f"✅ Scraping complete: {total_added} new updates added")
            logger.info(f"{'='*60}")

        finally:
            db.close()

        return total_added

    def logout(self):
        """Clean logout"""
        try:
            logout_url = f"{self.BASE_URL}/wp-login.php?action=logout"
            self.session.get(logout_url)
            self.is_logged_in = False
            logger.info("Logged out successfully")
        except Exception as e:
            logger.error(f"Logout error: {e}")


def run_scraper(limit_per_source: int = 5) -> int:
    """
    Convenience function to run the scraper
    Returns number of new updates added
    """
    scraper = MortgageGuidelinesScraper()

    try:
        count = scraper.scrape_all_sources(limit_per_source)
        return count
    finally:
        scraper.logout()


if __name__ == "__main__":
    print("Starting Mortgage Guidelines Scraper...")
    print(f"Target: {MortgageGuidelinesScraper.BASE_URL}")
    print(f"Username: {MortgageGuidelinesScraper.USERNAME}")
    print("\nScraping top 5 updates from each source...\n")

    count = run_scraper(limit_per_source=5)

    print(f"\n✅ Complete! Added {count} new guideline updates to database.")
