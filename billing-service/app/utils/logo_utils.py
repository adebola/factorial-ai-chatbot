"""
Logo utility functions for embedding logos in emails and PDFs.
"""
import base64
import os
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent


def get_logo_base64(logo_filename: str = "chatcraft-logo.png") -> str:
    """
    Read logo file and return base64-encoded string.

    Args:
        logo_filename: Name of the logo file in static/images/

    Returns:
        Base64-encoded string of the logo image
    """
    logo_path = PROJECT_ROOT / "static" / "images" / logo_filename

    if not logo_path.exists():
        return ""

    with open(logo_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def get_logo_data_url(logo_filename: str = "chatcraft-logo.png") -> str:
    """
    Get data URL for embedding logo in HTML/email.

    Args:
        logo_filename: Name of the logo file in static/images/

    Returns:
        Data URL string (data:image/png;base64,...)
    """
    base64_data = get_logo_base64(logo_filename)
    if not base64_data:
        return ""

    return f"data:image/png;base64,{base64_data}"


def get_logo_file_path(logo_filename: str = "chatcraft-logo.png") -> str:
    """
    Get absolute file path to logo (for PDF generation with WeasyPrint).

    Args:
        logo_filename: Name of the logo file in static/images/

    Returns:
        Absolute file path to the logo
    """
    logo_path = PROJECT_ROOT / "static" / "images" / logo_filename
    return str(logo_path.absolute()) if logo_path.exists() else ""
