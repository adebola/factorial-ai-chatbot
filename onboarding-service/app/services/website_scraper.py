import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session
from typing import List, Set, Optional, Dict
import time
import hashlib
from datetime import datetime
import asyncio
from enum import Enum
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from ..models.tenant import WebsiteIngestion, WebsitePage, IngestionStatus, DocumentStatus
from ..core.config import settings
from ..core.database import get_vector_db
from .pg_vector_ingestion import PgVectorIngestionService
from ..core.logging_config import get_logger

# Initialize logger
logger = get_logger("website_scraper")


class ScrapingStrategy(str, Enum):
    """Web scraping strategy options"""
    AUTO = "auto"  # Smart detection with fallback (recommended)
    REQUESTS_FIRST = "requests_first"  # Try requests, fallback to Playwright
    PLAYWRIGHT_ONLY = "playwright_only"  # Always use Playwright
    REQUESTS_ONLY = "requests_only"  # Only use requests


class WebsiteScraper:
    """Service for scraping websites and extracting content with intelligent fallback"""

    def __init__(
        self,
        db: Session,
        strategy: ScrapingStrategy = None,
        use_javascript: bool = None  # Deprecated, kept for backward compatibility
    ):
        self.db = db
        # Get vector database session for vector ingestion service
        self.vector_db = next(get_vector_db())
        self.vector_ingestion_service = PgVectorIngestionService(db=self.vector_db)

        # Determine scraping strategy
        if strategy:
            self.strategy = strategy
        elif use_javascript is not None:
            # Backward compatibility: convert old boolean to strategy
            self.strategy = ScrapingStrategy.PLAYWRIGHT_ONLY if use_javascript else ScrapingStrategy.REQUESTS_ONLY
        else:
            # Use config default
            self.strategy = ScrapingStrategy(getattr(settings, 'SCRAPING_STRATEGY', 'auto'))

        # Domain-level learning cache: remember which scraper works per domain
        self.domain_preferences: Dict[str, str] = {}  # domain -> "requests" | "playwright"

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
        )
    
    def start_website_ingestion(self, tenant_id: str, base_url: str) -> WebsiteIngestion:
        """Start website ingestion process"""

        # Create an ingestion record with the current scraping strategy
        ingestion = WebsiteIngestion(
            tenant_id=tenant_id,
            base_url=base_url,
            status=IngestionStatus.PENDING,
            scraping_strategy=self.strategy.value,
            started_at=datetime.now()
        )

        self.db.add(ingestion)
        self.db.commit()
        self.db.refresh(ingestion)

        return ingestion
    
    def scrape_website(self, tenant_id: str, base_url: str) -> List[Document]:
        """Scrape website and return processed documents (creates new ingestion record)"""
        
        ingestion = self.start_website_ingestion(tenant_id, base_url)
        return self.process_existing_ingestion(ingestion)
    
    async def process_existing_ingestion(self, ingestion: WebsiteIngestion) -> List[Document]:
        """Process an existing ingestion record (async)"""
        start_time = time.time()

        # Store IDs for fetching from this session
        tenant_id = ingestion.tenant_id
        ingestion_id = ingestion.id
        base_url = ingestion.base_url

        logger.info(
            "Starting website ingestion",
            tenant_id=tenant_id,
            ingestion_id=ingestion_id,
            base_url=base_url,
            strategy=self.strategy.value,
            max_pages=settings.MAX_PAGES_PER_SITE
        )

        try:
            # Re-fetch ingestion from this session to avoid detached instance issues
            ingestion = self.db.query(WebsiteIngestion).filter(
                WebsiteIngestion.id == ingestion_id,
                WebsiteIngestion.tenant_id == tenant_id
            ).first()

            if not ingestion:
                raise ValueError(f"Ingestion {ingestion_id} not found")

            ingestion.status = IngestionStatus.IN_PROGRESS
            self.db.commit()

            # Discover and scrape pages
            visited_urls = set()
            all_documents = []
            urls_to_visit = [ingestion.base_url]

            parsed_base = urlparse(ingestion.base_url)
            base_domain = f"{parsed_base.netloc}"

            pages_processed = 0
            pages_failed = 0
            page_number = 0

            logger.info(
                "Ingestion loop started",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                base_domain=base_domain
            )

            while urls_to_visit and pages_processed < settings.MAX_PAGES_PER_SITE:
                current_url = urls_to_visit.pop(0)
                page_number += 1

                if current_url in visited_urls:
                    logger.debug(
                        "Skipping already visited URL",
                        url=current_url,
                        tenant_id=ingestion.tenant_id
                    )
                    continue

                visited_urls.add(current_url)

                # Log before scraping
                logger.info(
                    f"📄 Page {page_number}/{settings.MAX_PAGES_PER_SITE}: Starting scrape",
                    tenant_id=tenant_id,
                    ingestion_id=ingestion_id,
                    url=current_url,
                    queue_size=len(urls_to_visit),
                    processed=pages_processed,
                    failed=pages_failed
                )

                page_start_time = time.time()

                try:
                    # Scrape page using smart strategy
                    page_doc = await self._scrape_page_with_strategy(
                        tenant_id=tenant_id,
                        ingestion_id=ingestion_id,
                        url=current_url
                    )

                    page_duration = time.time() - page_start_time

                    if page_doc:
                        # Split into chunks
                        chunks = self.text_splitter.split_documents([page_doc])

                        # Add metadata
                        for chunk in chunks:
                            chunk.metadata.update({
                                "tenant_id": tenant_id,
                                "source": current_url,
                                "ingestion_id": ingestion_id,
                                "scraped_date": datetime.now().isoformat()
                            })

                        all_documents.extend(chunks)
                        pages_processed += 1

                        logger.info(
                            f"✅ Page {page_number}: Successfully scraped",
                            tenant_id=tenant_id,
                            ingestion_id=ingestion_id,
                            url=current_url,
                            content_length=len(page_doc.page_content),
                            chunks_created=len(chunks),
                            duration_seconds=round(page_duration, 2),
                            scraping_method=page_doc.metadata.get("scraping_method")
                        )

                        # Find more URLs to scrape (only from same domain)
                        new_urls = await self._extract_links_with_strategy(current_url, base_domain)

                        links_added = 0
                        for url in new_urls:
                            if url not in visited_urls and url not in urls_to_visit:
                                urls_to_visit.append(url)
                                links_added += 1

                        if links_added > 0:
                            logger.debug(
                                f"Found {links_added} new URLs to visit",
                                tenant_id=tenant_id,
                                url=current_url,
                                new_links=links_added,
                                total_queue=len(urls_to_visit)
                            )

                    else:
                        pages_failed += 1
                        logger.warning(
                            f"❌ Page {page_number}: Scraping failed (no content returned)",
                            tenant_id=tenant_id,
                            ingestion_id=ingestion_id,
                            url=current_url,
                            duration_seconds=round(page_duration, 2)
                        )

                except Exception as e:
                    page_duration = time.time() - page_start_time
                    pages_failed += 1

                    logger.error(
                        f"❌ Page {page_number}: Exception during scraping",
                        tenant_id=tenant_id,
                        ingestion_id=ingestion_id,
                        url=current_url,
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_seconds=round(page_duration, 2),
                        exc_info=True
                    )

                # Log progress every 5 pages for more frequent UI updates
                if page_number % 5 == 0:
                    logger.info(
                        f"📊 Progress update",
                        tenant_id=tenant_id,
                        ingestion_id=ingestion_id,
                        pages_processed=pages_processed,
                        pages_failed=pages_failed,
                        queue_size=len(urls_to_visit),
                        total_visited=len(visited_urls)
                    )

                    # Update database with progress for UI polling
                    # pages_discovered = total unique URLs found (visited + still in queue)
                    ingestion.pages_discovered = len(visited_urls) + len(urls_to_visit)
                    ingestion.pages_processed = pages_processed
                    ingestion.pages_failed = pages_failed
                    self.db.commit()

                # Rate limiting
                await asyncio.sleep(settings.SCRAPING_DELAY)

            # Final update - DO NOT set status to COMPLETED here
            # Status will be set to COMPLETED by the background task after categorization finishes
            total_duration = time.time() - start_time
            # pages_discovered = total unique URLs found (visited + any remaining in queue)
            ingestion.pages_discovered = len(visited_urls) + len(urls_to_visit)
            ingestion.pages_processed = pages_processed
            ingestion.pages_failed = pages_failed
            self.db.commit()

            # Log session statistics
            self._log_session_statistics(tenant_id, ingestion_id)

            logger.info(
                "✅ Website ingestion completed successfully",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                base_url=base_url,
                pages_discovered=len(visited_urls),
                pages_processed=pages_processed,
                pages_failed=pages_failed,
                total_documents=len(all_documents),
                duration_seconds=round(total_duration, 2)
            )

            return all_documents

        except Exception as e:
            total_duration = time.time() - start_time
            ingestion.status = IngestionStatus.FAILED
            ingestion.error_message = str(e)
            ingestion.completed_at = datetime.now()
            self.db.commit()

            logger.error(
                "❌ Website ingestion failed with exception",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                base_url=base_url,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(total_duration, 2),
                exc_info=True
            )
            raise

    def _log_session_statistics(self, tenant_id: str, ingestion_id: str):
        """Log session-level statistics about domain preferences and scraping effectiveness"""
        if not self.domain_preferences:
            return

        requests_domains = sum(1 for method in self.domain_preferences.values() if method == "requests")
        playwright_domains = sum(1 for method in self.domain_preferences.values() if method == "playwright")
        total_domains = len(self.domain_preferences)

        logger.info(
            "📊 Session Statistics: Domain Preferences",
            tenant_id=tenant_id,
            ingestion_id=ingestion_id,
            total_domains_cached=total_domains,
            requests_preferred_domains=requests_domains,
            playwright_preferred_domains=playwright_domains,
            requests_percentage=round((requests_domains / total_domains) * 100, 1) if total_domains > 0 else 0,
            playwright_percentage=round((playwright_domains / total_domains) * 100, 1) if total_domains > 0 else 0,
            cache_effectiveness="high" if total_domains > 5 else "building"
        )

    async def _scrape_page_with_strategy(
        self, tenant_id: str, ingestion_id: str, url: str
    ) -> Optional[Document]:
        """Smart scraping with strategy-based fallback"""
        domain = urlparse(url).netloc
        strategy_start_time = time.time()

        # Strategy: AUTO - Smart detection with fallback
        if self.strategy == ScrapingStrategy.AUTO:
            # Check domain cache first
            if domain in self.domain_preferences:
                if self.domain_preferences[domain] == "playwright":
                    logger.info(
                        "🎭 Scraper Decision: Playwright (cached preference)",
                        tenant_id=tenant_id,
                        ingestion_id=ingestion_id,
                        url=url,
                        domain=domain,
                        decision_reason="domain_cache_hit",
                        cached_method="playwright",
                        strategy="AUTO",
                        cache_size=len(self.domain_preferences)
                    )
                    return await self._scrape_single_page_playwright(tenant_id, ingestion_id, url)
                else:
                    logger.info(
                        "⚡ Scraper Decision: Requests (cached preference)",
                        tenant_id=tenant_id,
                        ingestion_id=ingestion_id,
                        url=url,
                        domain=domain,
                        decision_reason="domain_cache_hit",
                        cached_method="requests",
                        strategy="AUTO",
                        cache_size=len(self.domain_preferences)
                    )
                    result = self._scrape_single_page(tenant_id, ingestion_id, url)
                    if result:
                        return result
                    # Cached method failed, try Playwright
                    logger.warning(
                        "↪️  Fallback Decision: Cached method failed, trying Playwright",
                        tenant_id=tenant_id,
                        ingestion_id=ingestion_id,
                        url=url,
                        domain=domain,
                        fallback_reason="cached_method_failed",
                        cached_method="requests",
                        strategy="AUTO"
                    )
                    return await self._scrape_single_page_playwright(tenant_id, ingestion_id, url)

            # No cache - try requests first (fast path)
            logger.info(
                "⚡ Scraper Decision: Requests (fast path attempt)",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                url=url,
                domain=domain,
                decision_reason="no_cache_fast_path",
                strategy="AUTO",
                will_fallback_if_insufficient="yes",
                content_threshold=500
            )
            result = self._scrape_single_page(tenant_id, ingestion_id, url)

            if result and len(result.page_content) > 500:
                # Success with requests! Cache this preference
                duration = time.time() - strategy_start_time
                logger.info(
                    "✅ Cache Update: Domain prefers Requests",
                    tenant_id=tenant_id,
                    ingestion_id=ingestion_id,
                    domain=domain,
                    cached_method="requests",
                    content_length=len(result.page_content),
                    duration_ms=round(duration * 1000, 2),
                    cache_operation="write",
                    cache_size_after=len(self.domain_preferences) + 1
                )
                self.domain_preferences[domain] = "requests"
                return result

            # Requests failed or returned minimal content - try Playwright
            logger.warning(
                "↪️  Fallback Decision: Switching to Playwright",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                url=url,
                domain=domain,
                fallback_reason="insufficient_content" if result else "no_content",
                requests_content_length=len(result.page_content) if result else 0,
                content_threshold=500,
                requests_duration_ms=round((time.time() - strategy_start_time) * 1000, 2),
                strategy="AUTO"
            )
            result = await self._scrape_single_page_playwright(tenant_id, ingestion_id, url)
            if result:
                duration = time.time() - strategy_start_time
                logger.info(
                    "✅ Cache Update: Domain prefers Playwright",
                    tenant_id=tenant_id,
                    ingestion_id=ingestion_id,
                    domain=domain,
                    cached_method="playwright",
                    content_length=len(result.page_content),
                    duration_ms=round(duration * 1000, 2),
                    cache_operation="write",
                    cache_size_after=len(self.domain_preferences) + 1
                )
                self.domain_preferences[domain] = "playwright"
            return result

        # Strategy: REQUESTS_FIRST - Try requests with fallback
        elif self.strategy == ScrapingStrategy.REQUESTS_FIRST:
            logger.info(
                "⚡ Scraper Decision: Requests (REQUESTS_FIRST strategy)",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                url=url,
                decision_reason="strategy_requests_first",
                strategy="REQUESTS_FIRST",
                fallback_enabled=getattr(settings, 'ENABLE_FALLBACK', True)
            )
            result = self._scrape_single_page(tenant_id, ingestion_id, url)
            if result:
                return result

            if getattr(settings, 'ENABLE_FALLBACK', True):
                logger.warning(
                    "↪️  Fallback Decision: Requests failed, switching to Playwright",
                    tenant_id=tenant_id,
                    ingestion_id=ingestion_id,
                    url=url,
                    fallback_reason="requests_failed",
                    strategy="REQUESTS_FIRST",
                    fallback_enabled=True
                )
                return await self._scrape_single_page_playwright(tenant_id, ingestion_id, url)
            return None

        # Strategy: PLAYWRIGHT_ONLY
        elif self.strategy == ScrapingStrategy.PLAYWRIGHT_ONLY:
            logger.info(
                "🎭 Scraper Decision: Playwright (PLAYWRIGHT_ONLY strategy)",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                url=url,
                decision_reason="strategy_playwright_only",
                strategy="PLAYWRIGHT_ONLY",
                fallback_enabled=False
            )
            return await self._scrape_single_page_playwright(tenant_id, ingestion_id, url)

        # Strategy: REQUESTS_ONLY
        elif self.strategy == ScrapingStrategy.REQUESTS_ONLY:
            logger.info(
                "⚡ Scraper Decision: Requests (REQUESTS_ONLY strategy)",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                url=url,
                decision_reason="strategy_requests_only",
                strategy="REQUESTS_ONLY",
                fallback_enabled=False
            )
            return self._scrape_single_page(tenant_id, ingestion_id, url)

        # Default fallback
        logger.debug(
            "Using default Playwright fallback",
            tenant_id=tenant_id,
            url=url
        )
        return await self._scrape_single_page_playwright(tenant_id, ingestion_id, url)

    async def _extract_links_with_strategy(self, base_url: str, allowed_domain: str) -> List[str]:
        """Extract links using appropriate strategy"""
        domain = urlparse(base_url).netloc

        # Use same method as page scraping for consistency
        if self.strategy == ScrapingStrategy.AUTO:
            if domain in self.domain_preferences and self.domain_preferences[domain] == "playwright":
                return await self._extract_links_playwright(base_url, allowed_domain)
            else:
                # Try requests first
                links = self._extract_links(base_url, allowed_domain)
                if links:
                    return links
                # Fallback to Playwright
                return await self._extract_links_playwright(base_url, allowed_domain)

        elif self.strategy == ScrapingStrategy.PLAYWRIGHT_ONLY:
            return await self._extract_links_playwright(base_url, allowed_domain)

        elif self.strategy in [ScrapingStrategy.REQUESTS_ONLY, ScrapingStrategy.REQUESTS_FIRST]:
            links = self._extract_links(base_url, allowed_domain)
            if links or self.strategy == ScrapingStrategy.REQUESTS_ONLY:
                return links
            # REQUESTS_FIRST with fallback
            if getattr(settings, 'ENABLE_FALLBACK', True):
                return await self._extract_links_playwright(base_url, allowed_domain)
            return links

        return self._extract_links(base_url, allowed_domain)

    def _scrape_single_page(self, tenant_id: str, ingestion_id: str, url: str) -> Optional[Document]:
        """Scrape a single page and return document"""
        
        # Create page record
        page_record = WebsitePage(
            tenant_id=tenant_id,
            ingestion_id=ingestion_id,
            url=url,
            status=DocumentStatus.PROCESSING
        )
        self.db.add(page_record)
        self.db.commit()
        self.db.refresh(page_record)
        
        try:
            requests_timeout = getattr(settings, 'REQUESTS_TIMEOUT', 10)
            response = self.session.get(url, timeout=requests_timeout)
            response.raise_for_status()
            
            # Check if the response is HTML content
            content_type = response.headers.get('content-type', '').lower()
            if not any(html_type in content_type for html_type in ['text/html', 'application/xhtml', 'text/plain']):
                page_record.status = DocumentStatus.FAILED
                page_record.error_message = f"Non-HTML content type: {content_type}"
                self.db.commit()
                return None
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract title
            title = soup.find('title')
            title_text = title.get_text().strip() if title else url

            # Focus on main content FIRST before removing elements
            main_content = None
            content_selectors = ['main', 'article', '[role="main"]', '.content', '.main-content', '#content', '#main', 'body']

            for selector in content_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break

            # If we found main content, work with that; otherwise use full soup
            content_source = main_content if main_content else soup

            # Remove only truly unwanted elements (be conservative)
            # Don't remove nav/header/footer/aside as they might contain content
            unwanted_elements = [
                "script", "style", "noscript", "iframe", "object", "embed",
                "img", "svg", "canvas", "video", "audio",
                "link", "meta", "base",
                "[class*='advertisement']", "[class*='banner']",
                "[class*='cookie-banner']", "[class*='cookie-consent']",
                "[class*='popup']", "[class*='modal']"
            ]

            for element_selector in unwanted_elements:
                for element in content_source.select(element_selector):
                    element.decompose()
            
            # Get text content
            content = content_source.get_text()
            
            # Advanced text cleaning
            lines = (line.strip() for line in content.splitlines())
            # Remove empty lines and lines with only special characters
            meaningful_lines = []
            for line in lines:
                if line and len(line.strip()) > 2 and not line.strip() in ['|', '-', '_', '*', '=', '+']:
                    # Remove excessive whitespace
                    cleaned_line = ' '.join(line.split())
                    if cleaned_line:
                        meaningful_lines.append(cleaned_line)
            
            content = ' '.join(meaningful_lines)
            
            if not content or len(content.strip()) < 50:
                page_record.status = DocumentStatus.FAILED
                page_record.error_message = "No meaningful content found"
                self.db.commit()
                return None
            
            # Calculate content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            # Update page record with content length
            page_record.title = title_text
            page_record.content_hash = content_hash
            page_record.status = DocumentStatus.COMPLETED
            page_record.scraped_at = datetime.now()
            self.db.commit()

            # Log successful scraping
            logger.info(
                "✅ Requests: Scraping successful",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                url=url,
                scraping_method="requests",
                content_length=len(content),
                title=title_text,
                content_hash=content_hash[:12] if len(content_hash) >= 12 else content_hash
            )

            # Create document
            document = Document(
                page_content=content,
                metadata={
                    "title": title_text,
                    "url": url,
                    "content_hash": content_hash,
                    "scraping_method": "requests",
                    "scraping_strategy": self.strategy.value
                }
            )

            return document
            
        except Exception as e:
            page_record.status = DocumentStatus.FAILED
            page_record.error_message = str(e)
            self.db.commit()
            return None

    async def _scrape_single_page_playwright(self, tenant_id: str, ingestion_id: str, url: str) -> Optional[Document]:
        """Scrape a single page using Playwright (handles JavaScript and popups)"""

        # Create page record
        page_record = WebsitePage(
            tenant_id=tenant_id,
            ingestion_id=ingestion_id,
            url=url,
            status=DocumentStatus.PROCESSING
        )
        self.db.add(page_record)
        self.db.commit()
        self.db.refresh(page_record)

        try:
            async with async_playwright() as p:
                # Launch browser in optimized headless mode
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-dev-shm-usage',  # Prevent crashes in Docker/low memory
                        '--no-sandbox',  # Required for Docker environments
                        '--disable-gpu',  # Not needed in headless
                        '--disable-setuid-sandbox',
                        '--disable-software-rasterizer',
                        '--disable-blink-features=AutomationControlled'  # Avoid detection
                    ]
                )
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()

                # Handle popups and modals by closing them
                async def close_popups(page_obj):
                    """Close common popup patterns"""
                    try:
                        # Wait a bit for popups to appear
                        await asyncio.sleep(2)

                        # Common popup close button selectors
                        close_selectors = [
                            'button[aria-label*="close" i]',
                            'button[aria-label*="dismiss" i]',
                            'button[class*="close" i]',
                            'button[class*="dismiss" i]',
                            'button[id*="close" i]',
                            '[class*="modal"] button',
                            '[class*="popup"] button',
                            '[class*="dialog"] button[aria-label*="close" i]',
                            '.modal-close',
                            '.popup-close',
                            '.close-button',
                            '[data-dismiss="modal"]',
                            'button:has-text("Close")',
                            'button:has-text("No thanks")',
                            'button:has-text("Maybe later")',
                            'button:has-text("×")',
                            'button:has-text("✕")',
                        ]

                        popups_closed = 0
                        for selector in close_selectors:
                            try:
                                # Try to find and click close button
                                element = await page_obj.query_selector(selector)
                                if element:
                                    await element.click(timeout=1000)
                                    await asyncio.sleep(0.5)
                                    popups_closed += 1
                                    logger.debug(
                                        f"Closed popup using selector: {selector}",
                                        tenant_id=tenant_id,
                                        url=url,
                                        selector=selector
                                    )
                            except:
                                continue

                        # Press Escape key to close modals
                        await page_obj.keyboard.press('Escape')
                        await asyncio.sleep(0.5)

                        if popups_closed > 0:
                            logger.debug(
                                f"✨ Closed {popups_closed} popup(s)",
                                tenant_id=tenant_id,
                                url=url,
                                popups_closed=popups_closed
                            )

                    except Exception as e:
                        logger.debug(
                            f"Error handling popups (non-critical)",
                            tenant_id=tenant_id,
                            url=url,
                            error=str(e)
                        )

                try:
                    # Navigate to the page
                    playwright_timeout = getattr(settings, 'PLAYWRIGHT_TIMEOUT', 30000)
                    # Use 'networkidle' instead of 'domcontentloaded' to support SPAs (React, Vue, Angular)
                    # networkidle waits for JavaScript bundles to load and React to render
                    response = await page.goto(url, wait_until='networkidle', timeout=playwright_timeout)

                    if not response or response.status >= 400:
                        page_record.status = DocumentStatus.FAILED
                        page_record.error_message = f"HTTP {response.status if response else 'no response'}"
                        self.db.commit()
                        await browser.close()
                        return None

                    # Wait for page to load and close any popups
                    await asyncio.sleep(2)  # Give time for dynamic content
                    await close_popups(page)

                    # Get page title
                    title_text = await page.title()
                    if not title_text:
                        title_text = url

                    # Get page content (HTML)
                    content_html = await page.content()

                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(content_html, 'html.parser')

                    # Focus on main content FIRST before removing elements
                    main_content = None
                    content_selectors = ['main', 'article', '[role="main"]', '.content', '.main-content', '#content', '#main', 'body']

                    for selector in content_selectors:
                        main_content = soup.select_one(selector)
                        if main_content:
                            break

                    # If we found main content, work with that; otherwise use full soup
                    content_source = main_content if main_content else soup

                    # Remove only truly unwanted elements (be conservative)
                    # Don't remove nav/header/footer/aside as they might contain content
                    unwanted_elements = [
                        "script", "style", "noscript", "iframe", "object", "embed",
                        "img", "svg", "canvas", "video", "audio",
                        "link", "meta", "base",
                        "[class*='advertisement']", "[class*='banner']",
                        "[class*='cookie-banner']", "[class*='cookie-consent']",
                        "[class*='popup']", "[class*='modal']"
                    ]

                    for element_selector in unwanted_elements:
                        for element in content_source.select(element_selector):
                            element.decompose()

                    # Get text content
                    content = content_source.get_text()

                    # Clean text
                    lines = (line.strip() for line in content.splitlines())
                    meaningful_lines = []
                    for line in lines:
                        if line and len(line.strip()) > 2 and not line.strip() in ['|', '-', '_', '*', '=', '+']:
                            cleaned_line = ' '.join(line.split())
                            if cleaned_line:
                                meaningful_lines.append(cleaned_line)

                    content = ' '.join(meaningful_lines)

                    # Log content extraction details
                    logger.debug(
                        "Playwright content extraction details",
                        tenant_id=tenant_id,
                        url=url,
                        raw_html_length=len(content_html),
                        after_cleaning_length=len(content),
                        meaningful_lines_count=len(meaningful_lines),
                        has_main_content=main_content is not None
                    )

                    if not content or len(content.strip()) < 50:
                        page_record.status = DocumentStatus.FAILED
                        page_record.error_message = f"No meaningful content found (extracted {len(content)} chars)"
                        self.db.commit()

                        logger.warning(
                            "Playwright: No meaningful content extracted",
                            tenant_id=tenant_id,
                            url=url,
                            content_length=len(content),
                            title=title_text,
                            html_size=len(content_html)
                        )

                        await browser.close()
                        return None

                    # Calculate content hash
                    content_hash = hashlib.sha256(content.encode()).hexdigest()

                    # Update page record
                    page_record.title = title_text
                    page_record.content_hash = content_hash
                    page_record.status = DocumentStatus.COMPLETED
                    page_record.scraped_at = datetime.now()
                    self.db.commit()

                    # Log successful scraping
                    logger.info(
                        "✅ Playwright: Scraping successful",
                        tenant_id=tenant_id,
                        ingestion_id=ingestion_id,
                        url=url,
                        scraping_method="playwright",
                        content_length=len(content),
                        title=title_text,
                        content_hash=content_hash[:12] if len(content_hash) >= 12 else content_hash
                    )

                    await browser.close()

                    # Create document
                    document = Document(
                        page_content=content,
                        metadata={
                            "title": title_text,
                            "url": url,
                            "content_hash": content_hash,
                            "scraping_method": "playwright",
                            "scraping_strategy": self.strategy.value
                        }
                    )

                    return document

                except PlaywrightTimeout as e:
                    page_record.status = DocumentStatus.FAILED
                    page_record.error_message = f"Timeout loading page: {str(e)}"
                    self.db.commit()
                    await browser.close()
                    return None

        except Exception as e:
            page_record.status = DocumentStatus.FAILED
            page_record.error_message = str(e)
            self.db.commit()
            return None

    def _extract_links(self, base_url: str, allowed_domain: str) -> List[str]:
        """Extract links from a page that belong to the same domain and are likely HTML pages"""
        try:
            requests_timeout = getattr(settings, 'REQUESTS_TIMEOUT', 10)
            response = self.session.get(base_url, timeout=requests_timeout)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # File extensions to exclude (images, documents, media files)
            excluded_extensions = {
                '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',  # Images
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',  # Documents
                '.zip', '.tar', '.gz', '.rar',  # Archives
                '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mp3', '.wav',  # Media
                '.js', '.css', '.xml', '.json',  # Web assets
                '.exe', '.dmg', '.deb', '.rpm'  # Executables
            }
            
            links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(base_url, href)
                
                # Check if URL belongs to allowed domain
                parsed_url = urlparse(full_url)
                if parsed_url.netloc == allowed_domain:
                    # Check if URL points to an excluded file type
                    path_lower = parsed_url.path.lower()
                    if any(path_lower.endswith(ext) for ext in excluded_extensions):
                        continue
                    
                    # Skip URLs with common non-HTML patterns
                    if any(pattern in path_lower for pattern in ['/download/', '/file/', '/asset/', '/static/', '/media/']):
                        continue
                    
                    # Remove fragments
                    clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                    if parsed_url.query:
                        clean_url += f"?{parsed_url.query}"
                    
                    if clean_url not in links:
                        links.append(clean_url)
            
            return links

        except Exception as e:
            logger.debug(
                "Error extracting links with requests",
                url=base_url,
                error=str(e),
                error_type=type(e).__name__
            )
            return []

    async def _extract_links_playwright(self, base_url: str, allowed_domain: str) -> List[str]:
        """Extract links using Playwright (handles JavaScript-loaded links)"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-gpu'
                    ]
                )
                page = await browser.new_page()

                try:
                    playwright_timeout = getattr(settings, 'PLAYWRIGHT_TIMEOUT', 30000)
                    await page.goto(base_url, wait_until='domcontentloaded', timeout=playwright_timeout // 2)  # Half timeout for link extraction
                    await asyncio.sleep(2)  # Wait for JavaScript to load links

                    # Get all links
                    links_data = await page.evaluate('''() => {
                        const links = Array.from(document.querySelectorAll('a[href]'));
                        return links.map(a => a.href);
                    }''')

                    await browser.close()

                    # File extensions to exclude
                    excluded_extensions = {
                        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
                        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                        '.zip', '.tar', '.gz', '.rar',
                        '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mp3', '.wav',
                        '.js', '.css', '.xml', '.json',
                        '.exe', '.dmg', '.deb', '.rpm'
                    }

                    filtered_links = []
                    for full_url in links_data:
                        parsed_url = urlparse(full_url)

                        # Check if URL belongs to allowed domain
                        if parsed_url.netloc == allowed_domain:
                            path_lower = parsed_url.path.lower()

                            # Skip excluded file types
                            if any(path_lower.endswith(ext) for ext in excluded_extensions):
                                continue

                            # Skip non-HTML patterns
                            if any(pattern in path_lower for pattern in ['/download/', '/file/', '/asset/', '/static/', '/media/']):
                                continue

                            # Remove fragments
                            clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                            if parsed_url.query:
                                clean_url += f"?{parsed_url.query}"

                            if clean_url not in filtered_links:
                                filtered_links.append(clean_url)

                    return filtered_links

                except Exception as e:
                    logger.debug(
                        "Error in Playwright link extraction (inner)",
                        url=base_url,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    await browser.close()
                    return []

        except Exception as e:
            logger.debug(
                "Error extracting links with Playwright",
                url=base_url,
                error=str(e),
                error_type=type(e).__name__
            )
            return []

    def get_ingestion_status(self, tenant_id: str, ingestion_id: str) -> Optional[WebsiteIngestion]:
        """Get ingestion status"""
        return self.db.query(WebsiteIngestion).filter(
            WebsiteIngestion.id == ingestion_id,
            WebsiteIngestion.tenant_id == tenant_id
        ).first()
    
    def get_tenant_ingestions(self, tenant_id: str) -> List[WebsiteIngestion]:
        """Get all ingestions for a tenant"""
        return self.db.query(WebsiteIngestion).filter(
            WebsiteIngestion.tenant_id == tenant_id
        ).order_by(WebsiteIngestion.created_at.desc()).all()
    
    def delete_ingestion(self, tenant_id: str, ingestion_id: str) -> bool:
        """Delete a website ingestion, related pages, and associated vectors"""
        try:
            cleanup_results = {
                "vectors_deleted": False,
                "pages_deleted": False,
                "ingestion_deleted": False
            }
            
            # Delete vectors from ChromaDB first
            vector_deleted = self.vector_ingestion_service.delete_ingestion_vectors(tenant_id, ingestion_id)
            cleanup_results["vectors_deleted"] = vector_deleted

            logger.info(
                "Vector deletion result",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                vectors_deleted=vector_deleted
            )

            # Delete related pages first (foreign key constraint)
            pages_deleted = self.db.query(WebsitePage).filter(
                WebsitePage.tenant_id == tenant_id,
                WebsitePage.ingestion_id == ingestion_id
            ).delete()
            cleanup_results["pages_deleted"] = pages_deleted > 0

            logger.info(
                f"Deleted {pages_deleted} website pages",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                pages_deleted=pages_deleted
            )

            # Delete the ingestion
            deleted_count = self.db.query(WebsiteIngestion).filter(
                WebsiteIngestion.id == ingestion_id,
                WebsiteIngestion.tenant_id == tenant_id
            ).delete()
            cleanup_results["ingestion_deleted"] = deleted_count > 0

            self.db.commit()

            # Log cleanup summary
            logger.info(
                "📋 Ingestion deletion completed",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                vectors_deleted=cleanup_results["vectors_deleted"],
                pages_deleted=cleanup_results["pages_deleted"],
                ingestion_deleted=cleanup_results["ingestion_deleted"]
            )

            return deleted_count > 0

        except Exception as e:
            self.db.rollback()
            logger.error(
                "Error deleting ingestion",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return False
    
    def reset_ingestion_for_retry(self, ingestion_id: str) -> bool:
        """Reset ingestion status for retry"""
        try:
            from datetime import datetime
            
            ingestion = self.db.query(WebsiteIngestion).filter(
                WebsiteIngestion.id == ingestion_id
            ).first()
            
            if ingestion:
                ingestion.status = IngestionStatus.PENDING
                ingestion.pages_processed = 0
                ingestion.pages_failed = 0
                ingestion.error_message = None
                ingestion.started_at = datetime.now()
                ingestion.completed_at = None
                
                # Reset related pages
                self.db.query(WebsitePage).filter(
                    WebsitePage.ingestion_id == ingestion_id
                ).update({
                    "status": DocumentStatus.PENDING,
                    "error_message": None
                })
                
                self.db.commit()
                return True
            
            return False

        except Exception as e:
            self.db.rollback()
            logger.error(
                "Error resetting ingestion",
                ingestion_id=ingestion_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return False
    
    def get_ingestion_content_stats(self, tenant_id: str, ingestion_id: str) -> dict:
        """Get content statistics for an ingestion"""
        try:
            # Get all pages for this ingestion
            pages = self.db.query(WebsitePage).filter(
                WebsitePage.tenant_id == tenant_id,
                WebsitePage.ingestion_id == ingestion_id
            ).all()
            
            stats = {
                "total_pages": len(pages),
                "successful_pages": 0,
                "failed_pages": 0,
                "processing_pages": 0,
                "pending_pages": 0,
                "unique_content_hashes": set(),
                "total_titles": 0
            }
            
            for page in pages:
                if page.status == DocumentStatus.COMPLETED:
                    stats["successful_pages"] += 1
                    if page.content_hash:
                        stats["unique_content_hashes"].add(page.content_hash)
                    if page.title:
                        stats["total_titles"] += 1
                elif page.status == DocumentStatus.FAILED:
                    stats["failed_pages"] += 1
                elif page.status == DocumentStatus.PROCESSING:
                    stats["processing_pages"] += 1
                else:
                    stats["pending_pages"] += 1
            
            # Convert set to count
            stats["unique_content_pages"] = len(stats["unique_content_hashes"])
            del stats["unique_content_hashes"]  # Remove set from return value
            
            return stats

        except Exception as e:
            logger.error(
                "Error calculating content stats",
                tenant_id=tenant_id,
                ingestion_id=ingestion_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return {"error": str(e)}
    
    # def _notify_chat_service_ingestion_deleted(self, tenant_id: str, ingestion_id: str) -> bool:
    #     """Notify chat service that an ingestion was deleted"""
    #     try:
    #         import httpx
    #
    #         # Get chat service URL from settings
    #         chat_service_url = getattr(settings, 'CHAT_SERVICE_URL', 'http://localhost:8000')
    #
    #         # Make synchronous HTTP request to chat service
    #         with httpx.Client() as client:
    #             response = client.delete(
    #                 f"{chat_service_url}/api/v1/vectors/ingestion/{ingestion_id}",
    #                 params={"tenant_id": tenant_id},
    #                 timeout=5
    #             )
    #             if response.status_code == 200:
    #                 print(f"✅ Notified chat service about ingestion deletion: {ingestion_id}")
    #                 return True
    #             else:
    #                 print(f"⚠️ Chat service notification failed: {response.status_code}")
    #                 return False
    #
    #     except Exception as e:
    #         print(f"⚠️ Failed to notify chat service about ingestion deletion: {e}")
    #         return False