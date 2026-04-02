"""
Automated Guideline Update Scraper
Checks for new updates from all 5 sources and stores them in database
Run this as a scheduled task (daily)
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import hashlib
import logging
from typing import List, Dict
from database import SessionLocal
from guideline_updates_models import GuidelineUpdate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# URLs/domains to exclude (tracking links, newsletters, redirects)
EXCLUDED_URL_PATTERNS = [
    'list-manage.com',      # Mailchimp tracking
    'mailchimp.com',        # Mailchimp
    'click.email',          # Email tracking
    'track.click',          # Click tracking
    'utm_source',           # UTM tracking params
    'unsubscribe',          # Unsubscribe links
    'constantcontact.com',  # Constant Contact
    'sendgrid.net',         # SendGrid tracking
    'mailgun.org',          # Mailgun tracking
    'click.pstmrk.it',      # Postmark tracking
    '/track/',              # Generic tracking paths
    '/click/',              # Generic click paths
]


def is_excluded_url(url: str) -> bool:
    """Check if URL should be excluded (tracking links, newsletters, etc.)"""
    if not url:
        return True
    url_lower = url.lower()
    for pattern in EXCLUDED_URL_PATTERNS:
        if pattern in url_lower:
            logger.info(f"  ⏭️  Excluding tracking URL: {url[:60]}...")
            return True
    return False


class GuidelineUpdateScraper:
    """Scraper for guideline updates from all sources"""

    SOURCES = {
        'fannie_mae': {
            'name': 'Fannie Mae',
            'updates_url': 'https://selling-guide.fanniemae.com/Guide-Bulletins',
        },
        'freddie_mac': {
            'name': 'Freddie Mac',
            'updates_url': 'https://guide.freddiemac.com/app/guide/bulletins',
        },
        'fha': {
            'name': 'FHA',
            'mortgagee_letters': 'https://www.hud.gov/program_offices/administration/hudclips/letters/mortgagee'
        },
        'va': {
            'name': 'VA',
            'circulars': 'https://www.benefits.va.gov/HOMELOANS/circulars.asp'
        },
        'usda': {
            'name': 'USDA',
            'notices': 'https://www.rd.usda.gov/newsroom'
        }
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.db = SessionLocal()

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()

    def _generate_hash(self, content: str) -> str:
        """Generate SHA256 hash for content deduplication"""
        return hashlib.sha256(content.encode()).hexdigest()

    def _is_duplicate(self, content_hash: str) -> bool:
        """Check if update already exists by content hash"""
        existing = self.db.query(GuidelineUpdate).filter_by(
            content_hash=content_hash
        ).first()
        return existing is not None

    def scrape_fannie_mae_updates(self) -> List[Dict]:
        """Scrape Fannie Mae Selling Guide bulletins"""
        logger.info("Scraping Fannie Mae updates...")
        updates = []

        try:
            response = self.session.get(self.SOURCES['fannie_mae']['updates_url'], timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find bulletin links
            bulletins = soup.find_all('a', href=True)[:10]

            for bulletin in bulletins:
                title = bulletin.get_text(strip=True)
                if 'bulletin' not in title.lower():
                    continue

                url = bulletin['href']
                if not url.startswith('http'):
                    url = 'https://selling-guide.fanniemae.com' + url

                # Skip tracking/newsletter URLs
                if is_excluded_url(url):
                    continue

                content_hash = self._generate_hash(title + url)

                if not self._is_duplicate(content_hash):
                    updates.append({
                        'source': 'fannie_mae',
                        'title': title,
                        'section_code': self._extract_bulletin_number(title),
                        'description': 'Fannie Mae Selling Guide update',
                        'url': url,
                        'published_date': datetime.now(timezone.utc),
                        'content_hash': content_hash
                    })

            logger.info(f"Found {len(updates)} new Fannie Mae updates")
        except Exception as e:
            logger.error(f"Error scraping Fannie Mae: {e}")

        return updates

    def scrape_freddie_mac_updates(self) -> List[Dict]:
        """Scrape Freddie Mac Guide bulletins"""
        logger.info("Scraping Freddie Mac updates...")
        updates = []

        try:
            response = self.session.get(self.SOURCES['freddie_mac']['updates_url'], timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            links = soup.find_all('a', href=True)[:10]

            for link in links:
                title = link.get_text(strip=True)
                if 'bulletin' not in title.lower():
                    continue

                url = link['href']
                if not url.startswith('http'):
                    url = 'https://guide.freddiemac.com' + url

                # Skip tracking/newsletter URLs
                if is_excluded_url(url):
                    continue

                content_hash = self._generate_hash(title + url)

                if not self._is_duplicate(content_hash):
                    updates.append({
                        'source': 'freddie_mac',
                        'title': title,
                        'section_code': self._extract_bulletin_number(title),
                        'description': 'Freddie Mac Guide Bulletin',
                        'url': url,
                        'published_date': datetime.now(timezone.utc),
                        'content_hash': content_hash
                    })

            logger.info(f"Found {len(updates)} new Freddie Mac updates")
        except Exception as e:
            logger.error(f"Error scraping Freddie Mac: {e}")

        return updates

    def scrape_fha_updates(self) -> List[Dict]:
        """Scrape FHA Mortgagee Letters"""
        logger.info("Scraping FHA updates...")
        updates = []

        try:
            response = self.session.get(self.SOURCES['fha']['mortgagee_letters'], timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            letters = soup.find_all('a', href=True)[:10]

            for letter in letters:
                title = letter.get_text(strip=True)
                if 'ml' not in title.lower():
                    continue

                url = letter['href']
                if not url.startswith('http'):
                    url = 'https://www.hud.gov' + url

                # Skip tracking/newsletter URLs
                if is_excluded_url(url):
                    continue

                content_hash = self._generate_hash(title + url)

                if not self._is_duplicate(content_hash):
                    updates.append({
                        'source': 'fha',
                        'title': title,
                        'section_code': self._extract_ml_number(title),
                        'description': 'FHA Mortgagee Letter',
                        'url': url,
                        'published_date': datetime.now(timezone.utc),
                        'content_hash': content_hash
                    })

            logger.info(f"Found {len(updates)} new FHA updates")
        except Exception as e:
            logger.error(f"Error scraping FHA: {e}")

        return updates

    def scrape_va_updates(self) -> List[Dict]:
        """Scrape VA Circulars"""
        logger.info("Scraping VA updates...")
        updates = []

        try:
            response = self.session.get(self.SOURCES['va']['circulars'], timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            circulars = soup.find_all('a', href=True)[:10]

            for circular in circulars:
                title = circular.get_text(strip=True)
                if 'circular' not in title.lower():
                    continue

                url = circular['href']
                if not url.startswith('http'):
                    url = 'https://www.benefits.va.gov' + url

                # Skip tracking/newsletter URLs
                if is_excluded_url(url):
                    continue

                content_hash = self._generate_hash(title + url)

                if not self._is_duplicate(content_hash):
                    updates.append({
                        'source': 'va',
                        'title': title,
                        'section_code': self._extract_circular_number(title),
                        'description': 'VA Circular',
                        'url': url,
                        'published_date': datetime.now(timezone.utc),
                        'content_hash': content_hash
                    })

            logger.info(f"Found {len(updates)} new VA updates")
        except Exception as e:
            logger.error(f"Error scraping VA: {e}")

        return updates

    def scrape_usda_updates(self) -> List[Dict]:
        """Scrape USDA notices"""
        logger.info("Scraping USDA updates...")
        updates = []

        try:
            response = self.session.get(self.SOURCES['usda']['notices'], timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            articles = soup.find_all('article')[:10]

            for article in articles:
                title_elem = article.find(['h2', 'h3', 'h4'])
                link_elem = article.find('a', href=True)

                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    url = link_elem['href']

                    if not url.startswith('http'):
                        url = 'https://www.rd.usda.gov' + url

                    # Skip tracking/newsletter URLs
                    if is_excluded_url(url):
                        continue

                    content_hash = self._generate_hash(title + url)

                    if not self._is_duplicate(content_hash):
                        updates.append({
                            'source': 'usda',
                            'title': title,
                            'section_code': None,
                            'description': 'USDA Notice',
                            'url': url,
                            'published_date': datetime.now(timezone.utc),
                            'content_hash': content_hash
                        })

            logger.info(f"Found {len(updates)} new USDA updates")
        except Exception as e:
            logger.error(f"Error scraping USDA: {e}")

        return updates

    def scrape_all_sources(self) -> int:
        """Scrape all sources and save to database"""
        logger.info("Starting full guideline update scrape...")

        all_updates = []
        all_updates.extend(self.scrape_fannie_mae_updates())
        all_updates.extend(self.scrape_freddie_mac_updates())
        all_updates.extend(self.scrape_fha_updates())
        all_updates.extend(self.scrape_va_updates())
        all_updates.extend(self.scrape_usda_updates())

        saved_count = 0
        for update_data in all_updates:
            try:
                update = GuidelineUpdate(**update_data)
                self.db.add(update)
                self.db.commit()
                saved_count += 1
                logger.info(f"✓ Saved: {update_data['source']} - {update_data['title'][:50]}...")
            except Exception as e:
                self.db.rollback()
                logger.error(f"Error saving update: {e}")

        logger.info(f"✓ Saved {saved_count} new updates")
        return saved_count

    def _extract_bulletin_number(self, title: str) -> str:
        """Extract bulletin number from title"""
        import re
        match = re.search(r'(Bulletin|BUL)\s+(\d{4}-\d+)', title, re.IGNORECASE)
        return match.group(2) if match else None

    def _extract_ml_number(self, title: str) -> str:
        """Extract ML number from title"""
        import re
        match = re.search(r'ML\s*(\d{4}-\d+)', title, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_circular_number(self, title: str) -> str:
        """Extract circular number from title"""
        import re
        match = re.search(r'(\d{2}-\d+)', title)
        return match.group(1) if match else None


def run_scheduled_scrape():
    """Run the scraper (call this from a scheduled task)"""
    scraper = GuidelineUpdateScraper()
    new_count = scraper.scrape_all_sources()
    print(f"\n{'='*60}")
    print(f"✓ Scraping complete: {new_count} new updates found")
    print(f"{'='*60}")
    return new_count


if __name__ == "__main__":
    run_scheduled_scrape()
