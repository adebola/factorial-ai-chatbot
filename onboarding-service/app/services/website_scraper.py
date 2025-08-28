import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session
from typing import List, Set, Optional
import time
import hashlib
from datetime import datetime

from ..models.tenant import WebsiteIngestion, WebsitePage, IngestionStatus, DocumentStatus
from ..core.config import settings
from ..core.database import get_vector_db
from .pg_vector_ingestion import PgVectorIngestionService


class WebsiteScraper:
    """Service for scraping websites and extracting content"""
    
    def __init__(self, db: Session):
        self.db = db
        # Get vector database session for vector ingestion service
        self.vector_db = next(get_vector_db())
        self.vector_ingestion_service = PgVectorIngestionService(db=self.vector_db)
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
        
        # Create an ingestion record
        ingestion = WebsiteIngestion(
            tenant_id=tenant_id,
            base_url=base_url,
            status=IngestionStatus.PENDING,
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
    
    def process_existing_ingestion(self, ingestion: WebsiteIngestion) -> List[Document]:
        """Process an existing ingestion record"""
        
        try:
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
            
            while urls_to_visit and pages_processed < settings.MAX_PAGES_PER_SITE:
                current_url = urls_to_visit.pop(0)
                
                if current_url in visited_urls:
                    continue
                
                visited_urls.add(current_url)
                
                try:
                    # Scrape page
                    page_doc = self._scrape_single_page(
                        tenant_id=ingestion.tenant_id,
                        ingestion_id=ingestion.id,
                        url=current_url
                    )
                    
                    if page_doc:
                        # Split into chunks
                        chunks = self.text_splitter.split_documents([page_doc])
                        
                        # Add metadata
                        for chunk in chunks:
                            chunk.metadata.update({
                                "tenant_id": ingestion.tenant_id,
                                "source": current_url,
                                "ingestion_id": ingestion.id,
                                "scraped_date": datetime.now().isoformat()
                            })
                        
                        all_documents.extend(chunks)
                        pages_processed += 1
                        
                        # Find more URLs to scrape (only from same domain)
                        new_urls = self._extract_links(current_url, base_domain)
                        for url in new_urls:
                            if url not in visited_urls and url not in urls_to_visit:
                                urls_to_visit.append(url)
                    
                    else:
                        pages_failed += 1
                
                except Exception as e:
                    print(f"Error scraping {current_url}: {e}")
                    pages_failed += 1
                
                # Rate limiting
                time.sleep(settings.SCRAPING_DELAY)
            
            # Update ingestion record
            ingestion.status = IngestionStatus.COMPLETED
            ingestion.pages_discovered = len(visited_urls)
            ingestion.pages_processed = pages_processed
            ingestion.pages_failed = pages_failed
            ingestion.completed_at = datetime.now()
            self.db.commit()
            
            return all_documents
            
        except Exception as e:
            ingestion.status = IngestionStatus.FAILED
            ingestion.error_message = str(e)
            ingestion.completed_at = datetime.now()
            self.db.commit()
            raise
    
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
            response = self.session.get(url, timeout=10)
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
            
            # Remove unwanted elements that don't contribute to meaningful content
            unwanted_elements = [
                "script", "style", "noscript", "iframe", "object", "embed",  # Code/embeds
                "nav", "header", "footer", "aside",  # Navigation/layout
                "form", "input", "button", "select", "textarea",  # Forms
                "img", "svg", "canvas", "video", "audio",  # Media
                "link", "meta", "base",  # Head elements
                "[class*='ad']", "[class*='advertisement']", "[class*='banner']",  # Ads
                "[class*='cookie']", "[class*='popup']", "[class*='modal']",  # Popups
                "[class*='sidebar']", "[class*='menu']", "[class*='navigation']"  # Layout
            ]
            
            for element_selector in unwanted_elements:
                for element in soup.select(element_selector):
                    element.decompose()
            
            # Focus on main content areas
            main_content = None
            content_selectors = ['main', 'article', '[role="main"]', '.content', '.main-content', '#content', '#main']
            
            for selector in content_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            # Use main content if found, otherwise use body
            content_source = main_content if main_content else soup.find('body')
            if not content_source:
                content_source = soup
            
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
            
            # Create document
            document = Document(
                page_content=content,
                metadata={
                    "title": title_text,
                    "url": url,
                    "content_hash": content_hash
                }
            )
            
            return document
            
        except Exception as e:
            page_record.status = DocumentStatus.FAILED
            page_record.error_message = str(e)
            self.db.commit()
            return None
    
    def _extract_links(self, base_url: str, allowed_domain: str) -> List[str]:
        """Extract links from a page that belong to the same domain and are likely HTML pages"""
        try:
            response = self.session.get(base_url, timeout=10)
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
            print(f"Error extracting links from {base_url}: {e}")
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
            if vector_deleted:
                print(f"✅ Deleted vectors from ChromaDB for ingestion {ingestion_id}")
            else:
                print(f"⚠️ Failed to delete vectors for ingestion {ingestion_id}")
            
            # Delete related pages first (foreign key constraint)
            pages_deleted = self.db.query(WebsitePage).filter(
                WebsitePage.tenant_id == tenant_id,
                WebsitePage.ingestion_id == ingestion_id
            ).delete()
            cleanup_results["pages_deleted"] = pages_deleted > 0
            print(f"✅ Deleted {pages_deleted} website pages from database")
            
            # Delete the ingestion
            deleted_count = self.db.query(WebsiteIngestion).filter(
                WebsiteIngestion.id == ingestion_id,
                WebsiteIngestion.tenant_id == tenant_id
            ).delete()
            cleanup_results["ingestion_deleted"] = deleted_count > 0
            
            self.db.commit()
            
            # Log cleanup summary
            print(f"📋 Ingestion {ingestion_id} deletion summary:")
            print(f"   - Vectors (PgVector): {'✅' if cleanup_results['vectors_deleted'] else '❌'}")
            print(f"   - Website Pages: {'✅' if cleanup_results['pages_deleted'] else 'ℹ️ No pages'}")
            print(f"   - Ingestion Record: {'✅' if cleanup_results['ingestion_deleted'] else '❌'}")
            
            return deleted_count > 0
            
        except Exception as e:
            self.db.rollback()
            print(f"Error deleting ingestion: {e}")
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
            print(f"Error resetting ingestion: {e}")
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
            print(f"Error calculating content stats: {e}")
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