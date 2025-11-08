#!/usr/bin/env python3
"""
User Registration Script for Live/Production Environment

This script registers a new tenant (organization) and admin user in the
FactorialBot production authorization server.

Usage:
    # Interactive mode
    python register-user-live.py

    # With command-line arguments
    python register-user-live.py \
        --org-name "My Company" \
        --org-domain "mycompany.com" \
        --admin-username "admin" \
        --admin-email "admin@mycompany.com" \
        --admin-first-name "John" \
        --admin-last-name "Doe" \
        --admin-password "SecurePassword123!"

    # With environment variables
    export AUTH_SERVER_URL="https://api.chatcraft.cc"
    export ORG_NAME="My Company"
    export ORG_DOMAIN="mycompany.com"
    export ADMIN_USERNAME="admin"
    export ADMIN_EMAIL="admin@mycompany.com"
    export ADMIN_FIRST_NAME="John"
    export ADMIN_LAST_NAME="Doe"
    export ADMIN_PASSWORD="SecurePassword123!"
    python register-user-live.py --non-interactive
"""

import argparse
import json
import os
import sys
from datetime import datetime
from getpass import getpass
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: 'requests' library not found.")
    print("Install it with: pip install requests")
    sys.exit(1)


# ANSI color codes
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color


def print_colored(message: str, color: str = Colors.NC):
    """Print colored message"""
    print(f"{color}{message}{Colors.NC}")


def print_header(title: str):
    """Print a formatted header"""
    print_colored("=" * 50, Colors.BLUE)
    print_colored(f"  {title}", Colors.BLUE)
    print_colored("=" * 50, Colors.BLUE)
    print()


def read_input(prompt: str, default: Optional[str] = None, env_var: Optional[str] = None) -> str:
    """Read input with optional default from environment"""
    # Check environment variable first
    if env_var and os.environ.get(env_var):
        value = os.environ.get(env_var)
        print_colored(f"Using {env_var} from environment: {value}", Colors.GREEN)
        return value

    # Check if default provided
    if default:
        prompt_with_default = f"{prompt} [{default}]: "
        value = input(prompt_with_default).strip()
        return value if value else default

    # No default, require input
    value = input(f"{prompt}: ").strip()
    while not value:
        print_colored("This field is required!", Colors.RED)
        value = input(f"{prompt}: ").strip()
    return value


def read_password(prompt: str, env_var: Optional[str] = None) -> str:
    """Read password securely"""
    # Check environment variable first
    if env_var and os.environ.get(env_var):
        print_colored(f"Using {env_var} from environment", Colors.GREEN)
        return os.environ.get(env_var)

    # Read password securely
    while True:
        password = getpass(f"{prompt}: ")
        if len(password) >= 8:
            return password
        print_colored("Password must be at least 8 characters long!", Colors.RED)


def validate_email(email: str) -> bool:
    """Basic email validation"""
    return '@' in email and '.' in email.split('@')[1]


def validate_domain(domain: str) -> bool:
    """Basic domain validation"""
    return '.' in domain and len(domain.split('.')) >= 2


def save_credentials(org_name: str, org_domain: str, admin_username: str,
                     admin_email: str, admin_first_name: str, admin_last_name: str,
                     login_url: str) -> str:
    """Save registration credentials to file"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"registration-{org_domain}-{timestamp}.txt"

    with open(filename, 'w') as f:
        f.write(f"FactorialBot Registration - {datetime.now()}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Organization: {org_name}\n")
        f.write(f"Domain: {org_domain}\n\n")
        f.write("Admin Account:\n")
        f.write(f"  Username: {admin_username}\n")
        f.write(f"  Email: {admin_email}\n")
        f.write(f"  First Name: {admin_first_name}\n")
        f.write(f"  Last Name: {admin_last_name}\n\n")
        f.write(f"Login URL: {login_url}\n\n")
        f.write(f"IMPORTANT: Check email at {admin_email} for verification link\n")

    return filename


def register_user(base_url: str, org_name: str,
                  admin_username: str, admin_email: str,
                  admin_first_name: str, admin_last_name: str,
                  admin_password: str) -> bool:
    """Register user via API"""

    register_endpoint = f"{base_url}/register"

    # Prepare payload
    payload = {
        "name": org_name,
        "adminUsername": admin_username,
        "adminEmail": admin_email,
        "adminFirstName": admin_first_name,
        "adminLastName": admin_last_name,
        "adminPassword": admin_password
    }

    print_colored("\nSending registration request...", Colors.BLUE)
    print_colored(f"Endpoint: {register_endpoint}", Colors.CYAN)

    try:
        response = requests.post(
            register_endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        print_colored(f"\nResponse Status: {response.status_code}", Colors.BLUE)

        if response.status_code in [200, 201, 302]:
            print_header("✓ Registration Successful!")
            print_colored(f"\nOrganization '{org_name}' has been registered successfully!", Colors.GREEN)
            print()
            print_colored(f"📧 A verification email has been sent to: {admin_email}", Colors.YELLOW)
            print_colored("   Please check your inbox and click the verification link to activate your account.",
                          Colors.YELLOW)
            print()
            print_colored("Next Steps:", Colors.BLUE)
            print("1. Check email inbox for verification link")
            print("2. Click verification link to activate account")
            print(f"3. Login at: {base_url}/login")
            print()
            print_colored("Login Credentials:", Colors.BLUE)
            print_colored(f"  Username: {admin_username}", Colors.GREEN)
            print_colored(f"  Email: {admin_email}", Colors.GREEN)
            print_colored(f"  Password: <as provided>", Colors.GREEN)
            print()

            # Save credentials
            creds_file = save_credentials(
                org_name, org_name, admin_username, admin_email,
                admin_first_name, admin_last_name, f"{base_url}/login"
            )
            print_colored(f"✓ Credentials saved to: {creds_file}", Colors.GREEN)
            print_colored("⚠️  Keep this file secure and delete after verification!", Colors.YELLOW)

            return True

        else:
            print_header("❌ Registration Failed")
            print_colored(f"HTTP Status: {response.status_code}", Colors.RED)
            print()

            # Try to parse error response
            try:
                error_data = response.json()
                print_colored("Error Response:", Colors.YELLOW)
                print(json.dumps(error_data, indent=2))
            except:
                print_colored("Response:", Colors.YELLOW)
                print(response.text)

            # Parse common errors
            response_text = response.text.lower()
            if "name.taken" in response_text or "name already exists" in response_text:
                print_colored(f"\n❌ Error: Organization name '{org_name}' is already taken", Colors.RED)
            elif "username.taken" in response_text or "username already" in response_text:
                print_colored(f"\n❌ Error: Username '{admin_username}' is already taken", Colors.RED)
            elif "email.taken" in response_text or "email already" in response_text:
                print_colored(f"\n❌ Error: Email '{admin_email}' is already registered", Colors.RED)

            return False

    except requests.exceptions.Timeout:
        print_colored("\n❌ Error: Request timed out. Please check your internet connection.", Colors.RED)
        return False
    except requests.exceptions.ConnectionError:
        print_colored(f"\n❌ Error: Could not connect to {register_endpoint}", Colors.RED)
        print_colored("   Please verify the URL is correct and the server is running.", Colors.YELLOW)
        return False
    except Exception as e:
        print_colored(f"\n❌ Error: {str(e)}", Colors.RED)
        return False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Register a new user in FactorialBot production environment"
    )
    parser.add_argument("--org-name", help="Organization name")
    parser.add_argument("--admin-username", help="Admin username")
    parser.add_argument("--admin-email", help="Admin email")
    parser.add_argument("--admin-first-name", help="Admin first name")
    parser.add_argument("--admin-last-name", help="Admin last name")
    parser.add_argument("--admin-password", help="Admin password (min 8 characters)")
    parser.add_argument("--auth-server-url", default=os.environ.get("AUTH_SERVER_URL", "https://api.chatcraft.cc"),
                        help="Authorization server URL (default: https://api.chatcraft.cc)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Non-interactive mode (use environment variables)")

    args = parser.parse_args()

    print_header("FactorialBot User Registration (LIVE)")
    print_colored("⚠️  WARNING: This will register a user in the PRODUCTION environment!", Colors.YELLOW)
    print_colored(f"   URL: {args.auth_server_url}", Colors.YELLOW)
    print()

    # Non-interactive mode
    if args.non_interactive:
        org_name = args.org_name or os.environ.get("ORG_NAME")
        admin_username = args.admin_username or os.environ.get("ADMIN_USERNAME")
        admin_email = args.admin_email or os.environ.get("ADMIN_EMAIL")
        admin_first_name = args.admin_first_name or os.environ.get("ADMIN_FIRST_NAME", "")
        admin_last_name = args.admin_last_name or os.environ.get("ADMIN_LAST_NAME", "")
        admin_password = args.admin_password or os.environ.get("ADMIN_PASSWORD")

        if not all([org_name, admin_username, admin_email, admin_password]):
            print_colored("❌ Error: Missing required fields in non-interactive mode", Colors.RED)
            print_colored("   Required: ORG_NAME, ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD",
                          Colors.YELLOW)
            sys.exit(1)

    else:
        # Interactive mode
        print_colored("Organization Information:", Colors.BLUE)
        org_name = args.org_name or read_input(
            "Organization Name (e.g., 'Acme Corporation')",
            env_var="ORG_NAME"
        )

        print()
        print_colored("Administrator Account:", Colors.BLUE)
        admin_username = args.admin_username or read_input(
            "Admin Username (letters, numbers, _, -)",
            env_var="ADMIN_USERNAME"
        )
        admin_email = args.admin_email or read_input(
            "Admin Email",
            env_var="ADMIN_EMAIL"
        )

        # Validate email
        while not validate_email(admin_email):
            print_colored("Invalid email format!", Colors.RED)
            admin_email = read_input("Admin Email")

        admin_first_name = args.admin_first_name or read_input(
            "Admin First Name",
            default="",
            env_var="ADMIN_FIRST_NAME"
        )
        admin_last_name = args.admin_last_name or read_input(
            "Admin Last Name",
            default="",
            env_var="ADMIN_LAST_NAME"
        )
        admin_password = args.admin_password or read_password(
            "Admin Password (min 8 characters)",
            env_var="ADMIN_PASSWORD"
        )

    # Show summary
    print()
    print_header("Registration Summary")
    print(f"Organization Name: {Colors.GREEN}{org_name}{Colors.NC}")
    print(f"Admin Username: {Colors.GREEN}{admin_username}{Colors.NC}")
    print(f"Admin Email: {Colors.GREEN}{admin_email}{Colors.NC}")
    print(f"Admin First Name: {Colors.GREEN}{admin_first_name}{Colors.NC}")
    print(f"Admin Last Name: {Colors.GREEN}{admin_last_name}{Colors.NC}")
    print(f"Password: {Colors.GREEN}***********{Colors.NC}")
    print()
    print_colored(f"⚠️  Target: {args.auth_server_url}/register", Colors.YELLOW)
    print()

    # Confirm
    if not args.non_interactive:
        confirm = input("Proceed with registration? (yes/no): ").strip().lower()
        if confirm != "yes":
            print_colored("Registration cancelled.", Colors.YELLOW)
            sys.exit(0)

    # Register
    success = register_user(
        args.auth_server_url,
        org_name,
        admin_username,
        admin_email,
        admin_first_name,
        admin_last_name,
        admin_password
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
