#!/usr/bin/env python3
"""
Startup script for RabbitMQ user event consumer.

This script should be run as a separate process from the main FastAPI application.
It listens for user creation events and automatically creates subscriptions.

Usage:
    python3 start_consumer.py

Or with environment variables:
    DATABASE_URL=postgresql://... RABBITMQ_URL=amqp://... python3 start_consumer.py
"""
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import and run consumer
from app.messaging.user_consumer import main

if __name__ == "__main__":
    print("=" * 80)
    print("BILLING SERVICE - RabbitMQ User Event Consumer")
    print("=" * 80)
    print()
    print("This consumer listens for user creation events and automatically")
    print("creates Basic plan subscriptions with 14-day trials.")
    print()
    print("Press CTRL+C to stop the consumer.")
    print("=" * 80)
    print()

    main()
