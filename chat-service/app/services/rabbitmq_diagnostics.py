"""
RabbitMQ Connection Diagnostics

Helper functions to diagnose RabbitMQ connection issues
"""

import socket
import os
from typing import Dict, Any
from ..core.logging_config import get_logger

logger = get_logger(__name__)


def check_rabbitmq_connectivity() -> Dict[str, Any]:
    """
    Check RabbitMQ connectivity and return diagnostic information.

    Returns:
        Dictionary with diagnostic results
    """
    rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
    rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
    rabbitmq_user = os.environ.get("RABBITMQ_USER", "guest")
    rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

    diagnostics = {
        "host": rabbitmq_host,
        "port": rabbitmq_port,
        "user": rabbitmq_user,
        "vhost": rabbitmq_vhost,
        "dns_resolution": None,
        "tcp_connection": None,
        "environment_vars": {}
    }

    # Check DNS resolution
    try:
        ip_address = socket.gethostbyname(rabbitmq_host)
        diagnostics["dns_resolution"] = {
            "success": True,
            "ip_address": ip_address
        }
        logger.info(f"DNS resolution successful: {rabbitmq_host} -> {ip_address}")
    except socket.gaierror as e:
        diagnostics["dns_resolution"] = {
            "success": False,
            "error": str(e)
        }
        logger.error(f"DNS resolution failed for {rabbitmq_host}: {e}")

    # Check TCP connectivity
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((rabbitmq_host, rabbitmq_port))
        sock.close()

        if result == 0:
            diagnostics["tcp_connection"] = {
                "success": True,
                "message": f"Port {rabbitmq_port} is open"
            }
            logger.info(f"TCP connection successful: {rabbitmq_host}:{rabbitmq_port}")
        else:
            diagnostics["tcp_connection"] = {
                "success": False,
                "error": f"Port {rabbitmq_port} is closed or unreachable (error code: {result})"
            }
            logger.error(f"TCP connection failed: {rabbitmq_host}:{rabbitmq_port} (error code: {result})")
    except Exception as e:
        diagnostics["tcp_connection"] = {
            "success": False,
            "error": str(e)
        }
        logger.exception(f"TCP connection check failed: {e}")

    # Check environment variables
    env_vars = [
        "RABBITMQ_HOST",
        "RABBITMQ_PORT",
        "RABBITMQ_USER",
        "RABBITMQ_PASSWORD",
        "RABBITMQ_VHOST",
        "RABBITMQ_URL",
        "RABBITMQ_CHAT_EXCHANGE",
        "RABBITMQ_USAGE_EXCHANGE"
    ]

    for var in env_vars:
        value = os.environ.get(var)
        if value:
            # Mask password
            if "PASSWORD" in var.upper():
                diagnostics["environment_vars"][var] = "***REDACTED***"
            else:
                diagnostics["environment_vars"][var] = value
        else:
            diagnostics["environment_vars"][var] = None

    return diagnostics


def log_diagnostics():
    """Run diagnostics and log results"""
    logger.info("=" * 60)
    logger.info("RabbitMQ Connection Diagnostics")
    logger.info("=" * 60)

    diagnostics = check_rabbitmq_connectivity()

    logger.info(f"Host: {diagnostics['host']}")
    logger.info(f"Port: {diagnostics['port']}")
    logger.info(f"User: {diagnostics['user']}")
    logger.info(f"VHost: {diagnostics['vhost']}")

    if diagnostics['dns_resolution']:
        if diagnostics['dns_resolution']['success']:
            logger.info(f"✓ DNS Resolution: {diagnostics['dns_resolution']['ip_address']}")
        else:
            logger.error(f"✗ DNS Resolution Failed: {diagnostics['dns_resolution']['error']}")

    if diagnostics['tcp_connection']:
        if diagnostics['tcp_connection']['success']:
            logger.info(f"✓ TCP Connection: {diagnostics['tcp_connection']['message']}")
        else:
            logger.error(f"✗ TCP Connection Failed: {diagnostics['tcp_connection']['error']}")

    logger.info("Environment Variables:")
    for var, value in diagnostics['environment_vars'].items():
        if value:
            logger.info(f"  {var}: {value}")
        else:
            logger.warning(f"  {var}: NOT SET")

    logger.info("=" * 60)

    return diagnostics
