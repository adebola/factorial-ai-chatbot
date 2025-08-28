import requests
import chromadb
from typing import List, Optional
from ..core.config import settings


class VectorCleanupService:
    """Service for cleaning up vectors from ChromaDB in chat service"""
    
    def __init__(self):
        pass
    
    def delete_all_tenant_vectors(self, tenant_id: str) -> bool:
        """Delete all vectors for a tenant (used when tenant is deleted)"""
        try:
            # Test ChromaDB accessibility first
            heartbeat_url = f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}/api/v1/heartbeat"
            response = requests.get(heartbeat_url, timeout=5)
            response.raise_for_status()
            
            # Connect to ChromaDB
            client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                settings=chromadb.config.Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            collection_name = f"tenant_{tenant_id}"
            
            try:
                # Delete the entire collection
                client.delete_collection(collection_name)
                
                print(f"✅ Deleted entire tenant collection from ChromaDB: {collection_name}")
                return True
                
            except Exception as collection_error:
                if "does not exist" in str(collection_error):
                    print(f"ℹ️ Collection does not exist, nothing to clean: {collection_name}")
                    return True
                raise collection_error
                
        except Exception as e:
            print(f"❌ Failed to delete tenant vectors from chat service: {tenant_id}, error: {e}")
            return False
    
    def delete_document_vectors(self, tenant_id: str, document_id: str) -> bool:
        """Delete vectors associated with a specific document"""
        try:
            # Test ChromaDB accessibility first
            heartbeat_url = f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}/api/v1/heartbeat"
            response = requests.get(heartbeat_url, timeout=5)
            response.raise_for_status()
            
            # Connect to ChromaDB
            client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                settings=chromadb.config.Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            collection_name = f"tenant_{tenant_id}"
            
            try:
                collection = client.get_collection(collection_name)
                
                # Query vectors with the document_id in metadata
                results = collection.get(
                    where={"document_id": document_id},
                    include=["metadatas"]
                )
                
                if results['ids']:
                    # Delete the vectors
                    collection.delete(ids=results['ids'])
                    print(f"✅ Deleted {len(results['ids'])} document vectors from chat service ChromaDB")
                    return True
                else:
                    print(f"ℹ️ No vectors found for document {document_id} in chat service")
                    return True
                    
            except Exception as collection_error:
                if "does not exist" in str(collection_error):
                    print(f"ℹ️ Collection does not exist in chat service: {collection_name}")
                    return True
                raise collection_error
                
        except Exception as e:
            print(f"❌ Failed to delete document vectors from chat service: {document_id}, error: {e}")
            return False
    
    def delete_ingestion_vectors(self, tenant_id: str, ingestion_id: str) -> bool:
        """Delete vectors associated with a specific website ingestion"""
        try:
            # Test ChromaDB accessibility first
            heartbeat_url = f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}/api/v1/heartbeat"
            response = requests.get(heartbeat_url, timeout=5)
            response.raise_for_status()
            
            # Connect to ChromaDB
            client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                settings=chromadb.config.Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            collection_name = f"tenant_{tenant_id}"
            
            try:
                collection = client.get_collection(collection_name)
                
                # Query vectors with the ingestion_id in metadata
                results = collection.get(
                    where={"ingestion_id": ingestion_id},
                    include=["metadatas"]
                )
                
                if results['ids']:
                    # Delete the vectors
                    collection.delete(ids=results['ids'])
                    print(f"✅ Deleted {len(results['ids'])} ingestion vectors from chat service ChromaDB")
                    return True
                else:
                    print(f"ℹ️ No vectors found for ingestion {ingestion_id} in chat service")
                    return True
                    
            except Exception as collection_error:
                if "does not exist" in str(collection_error):
                    print(f"ℹ️ Collection does not exist in chat service: {collection_name}")
                    return True
                raise collection_error
                
        except Exception as e:
            print(f"❌ Failed to delete ingestion vectors from chat service: {ingestion_id}, error: {e}")
            return False