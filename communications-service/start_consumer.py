#!/usr/bin/env python3
"""
Script to start RabbitMQ consumer with proper environment loading
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Print loaded config for verification
print(f"Database: {os.environ.get('DATABASE_URL')[:30]}...")
print(f"RabbitMQ User: {os.environ.get('RABBITMQ_USERNAME')}")
print(f"RabbitMQ Exchange: {os.environ.get('RABBITMQ_EXCHANGE')}")

# Import and start consumer
from app.services.rabbitmq_consumer import start_consumer

if __name__ == "__main__":
    start_consumer()