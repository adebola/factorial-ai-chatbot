#!/usr/bin/env python3
"""
Quick Production Vector DB Check
Run this to verify the exact state of your production vector database
"""

import os
import psycopg2
from datetime import datetime

def main():
    print("=== Production Vector DB Quick Check ===")
    print(f"Time: {datetime.now()}")
    print()

    # Get vector database URL
    vector_db_url = os.environ.get("VECTOR_DATABASE_URL")
    if not vector_db_url:
        print("❌ VECTOR_DATABASE_URL not set")
        return

    print(f"Connecting to: {vector_db_url.split('@')[1] if '@' in vector_db_url else 'unknown'}")

    try:
        conn = psycopg2.connect(vector_db_url)
        cursor = conn.cursor()

        print("\n1. Checking if public.document_chunks exists:")
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'document_chunks'
            );
        """)
        table_exists = cursor.fetchone()[0]
        print(f"   public.document_chunks exists: {table_exists}")

        if not table_exists:
            print("\n❌ PROBLEM FOUND: public.document_chunks table does not exist!")

            # Check if it exists in vectors schema
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'vectors' AND table_name = 'document_chunks'
                );
            """)
            vectors_exists = cursor.fetchone()[0]
            print(f"   vectors.document_chunks exists: {vectors_exists}")

            # List all schemas
            cursor.execute("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name;")
            schemas = [row[0] for row in cursor.fetchall()]
            print(f"   Available schemas: {schemas}")

            # List all tables with 'chunk' in name
            cursor.execute("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_name LIKE '%chunk%'
                ORDER BY table_schema, table_name;
            """)
            chunk_tables = cursor.fetchall()
            print(f"   Tables with 'chunk' in name: {chunk_tables}")

        else:
            print("\n✅ public.document_chunks exists!")

            print("\n2. Checking table structure:")
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'document_chunks'
                ORDER BY ordinal_position;
            """)
            columns = cursor.fetchall()
            column_names = [col[0] for col in columns]
            print(f"   Columns: {column_names}")

            # Check for categorization columns
            required_cols = ['category_ids', 'tag_ids', 'content_type']
            missing_cols = [col for col in required_cols if col not in column_names]

            if missing_cols:
                print(f"   ❌ Missing categorization columns: {missing_cols}")
                print("   💡 Solution: Run fix_production_vector_db.sql")
            else:
                print("   ✅ All categorization columns present")

            print("\n3. Record count:")
            cursor.execute("SELECT COUNT(*) FROM public.document_chunks;")
            count = cursor.fetchone()[0]
            print(f"   Total chunks: {count}")

        conn.close()

        if not table_exists:
            print("\n🔧 NEXT STEPS:")
            print("1. Your production vector_db is missing the document_chunks table")
            print("2. Run the vector database initialization scripts:")
            print("   - docker-build/db-init/02-init-pgvector-schemas.sql")
            print("   - docker-build/db-init/03-add-categorization-to-vector-db.sql")
            print("3. Or contact your database admin to ensure vector_db is properly set up")

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nPossible issues:")
        print("- Vector database is not running")
        print("- Wrong connection URL")
        print("- Network connectivity issues")
        print("- Database credentials incorrect")

if __name__ == "__main__":
    main()