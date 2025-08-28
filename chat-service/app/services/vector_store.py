# Import the PostgreSQL-based vector store
from .pg_vector_store import PgVectorStore

# Create an alias for backward compatibility
TenantVectorStore = PgVectorStore