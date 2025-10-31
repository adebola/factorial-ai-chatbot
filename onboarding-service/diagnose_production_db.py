#!/usr/bin/env python3
"""
Production Database Diagnostic Script
Run this script to diagnose database schema issues in production
"""

import os
import sys
import asyncpg
import psycopg2
from datetime import datetime

def test_database_schemas():
    """Test database schemas and table existence"""

    print("=== Production Database Schema Diagnostic ===")
    print(f"Test Time: {datetime.now()}")
    print()

    # Check environment variables
    print("1. Checking Environment Variables:")
    required_vars = ["DATABASE_URL", "VECTOR_DATABASE_URL"]

    missing_vars = []
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            # Mask password in URL
            if "postgresql://" in value:
                masked_value = value.split("@")[0].split(":")
                if len(masked_value) > 2:
                    masked_value = f"{masked_value[0]}:{masked_value[1]}:***@{value.split('@')[1]}"
                else:
                    masked_value = "postgresql://***@" + value.split("@")[1] if "@" in value else "***"
                print(f"   ✅ {var}: {masked_value}")
            else:
                print(f"   ✅ {var}: {value}")
        else:
            print(f"   ❌ {var}: NOT SET")
            missing_vars.append(var)

    if missing_vars:
        print(f"\n❌ Missing required variables: {missing_vars}")
        return False

    print("\n2. Testing Database Connections:")

    # Test onboard_db connection
    onboard_db_url = os.environ.get("DATABASE_URL")
    vector_db_url = os.environ.get("VECTOR_DATABASE_URL")

    print("\n   Testing Onboard Database Connection:")
    try:
        conn = psycopg2.connect(onboard_db_url)
        cursor = conn.cursor()

        # Check schemas
        cursor.execute("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name;")
        schemas = [row[0] for row in cursor.fetchall()]
        print(f"   ✅ Onboard DB Connected. Schemas: {schemas}")

        # Check main tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('tenants', 'users', 'documents', 'categories', 'tags')
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]
        print(f"   📋 Onboard DB Tables: {tables}")

        # Check if vectors schema exists (it shouldn't)
        if 'vectors' in schemas:
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'vectors'
                ORDER BY table_name;
            """)
            vector_tables = [row[0] for row in cursor.fetchall()]
            print(f"   ⚠️  UNEXPECTED: vectors schema exists in onboard_db with tables: {vector_tables}")

        conn.close()

    except Exception as e:
        print(f"   ❌ Onboard DB Connection failed: {e}")
        return False

    print("\n   Testing Vector Database Connection:")
    try:
        conn = psycopg2.connect(vector_db_url)
        cursor = conn.cursor()

        # Check schemas
        cursor.execute("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name;")
        schemas = [row[0] for row in cursor.fetchall()]
        print(f"   ✅ Vector DB Connected. Schemas: {schemas}")

        # Check for document_chunks in public schema
        cursor.execute("""
            SELECT table_name, table_schema
            FROM information_schema.tables
            WHERE table_name = 'document_chunks'
            ORDER BY table_schema;
        """)
        chunk_tables = cursor.fetchall()
        print(f"   📋 document_chunks tables found: {chunk_tables}")

        if not chunk_tables:
            print(f"   ❌ CRITICAL: No document_chunks table found in vector_db!")
            return False

        # Check table structure for each document_chunks table
        for table_name, schema_name in chunk_tables:
            print(f"\n   🔍 Checking {schema_name}.{table_name} structure:")

            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = '{schema_name}'
                AND table_name = '{table_name}'
                ORDER BY ordinal_position;
            """)
            columns = cursor.fetchall()

            required_columns = ['category_ids', 'tag_ids', 'content_type']
            existing_columns = [col[0] for col in columns]

            print(f"      Columns: {existing_columns}")

            missing_categorization = [col for col in required_columns if col not in existing_columns]
            if missing_categorization:
                print(f"      ❌ Missing categorization columns: {missing_categorization}")
            else:
                print(f"      ✅ All categorization columns present")

            # Check record count
            cursor.execute(f"SELECT COUNT(*) FROM {schema_name}.{table_name};")
            count = cursor.fetchone()[0]
            print(f"      📊 Record count: {count}")

        # Check for pgvector extension
        cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector';")
        vector_ext = cursor.fetchone()
        if vector_ext:
            print(f"   ✅ pgvector extension installed")
        else:
            print(f"   ❌ pgvector extension not found")

        conn.close()

    except Exception as e:
        print(f"   ❌ Vector DB Connection failed: {e}")
        return False

    print("\n3. Checking Application Database Configuration:")

    # Try to import and test the categorized vector store
    try:
        sys.path.append('/Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/onboarding-service')
        from app.core.database import get_vector_db, get_db
        from app.services.categorized_vector_store import CategorizedVectorStore

        print("   ✅ Successfully imported database modules")

        # Test creating categorized vector store
        # Note: This is a basic import test, not a full connection test
        print("   ✅ CategorizedVectorStore class can be imported")

    except Exception as e:
        print(f"   ❌ Application module import failed: {e}")

    print("\n4. Recommendations:")
    print("   If document_chunks table is missing categorization columns:")
    print("   1. Run: docker-build/db-init/03-add-categorization-to-vector-db.sql on production vector_db")
    print("   2. Or manually add columns:")
    print("      ALTER TABLE public.document_chunks ADD COLUMN IF NOT EXISTS category_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;")
    print("      ALTER TABLE public.document_chunks ADD COLUMN IF NOT EXISTS tag_ids VARCHAR(36)[] DEFAULT '{}' NOT NULL;")
    print("      ALTER TABLE public.document_chunks ADD COLUMN IF NOT EXISTS content_type VARCHAR(50);")
    print("      CREATE INDEX IF NOT EXISTS idx_document_chunks_category_ids ON public.document_chunks USING GIN (category_ids);")
    print("      CREATE INDEX IF NOT EXISTS idx_document_chunks_tag_ids ON public.document_chunks USING GIN (tag_ids);")

    return True

if __name__ == "__main__":
    success = test_database_schemas()
    sys.exit(0 if success else 1)