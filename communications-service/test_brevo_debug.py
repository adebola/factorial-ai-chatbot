"""
Brevo API Key Diagnostic Script
This script helps debug 401 authentication errors
"""
import os
from dotenv import load_dotenv
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

# Load environment variables
load_dotenv()

print("=" * 60)
print("BREVO API KEY DIAGNOSTIC")
print("=" * 60)

# Step 1: Check if API key is loaded
api_key = os.environ.get('BREVO_API_KEY')
print(f"\n1. API Key Status:")
if api_key:
    # Show only first and last 10 characters for security
    masked_key = f"{api_key[:10]}...{api_key[-10:]}"
    print(f"   ✅ API key found: {masked_key}")
    print(f"   📏 Length: {len(api_key)} characters")
    print(f"   🔤 Starts with: {api_key[:10]}")
else:
    print("   ❌ API key NOT found in environment")
    print("   💡 Make sure .env file is in the current directory")
    exit(1)

# Step 2: Check API key format
print(f"\n2. API Key Format Check:")
if api_key.startswith('xkeysib-'):
    print("   ✅ API key has correct prefix 'xkeysib-'")
else:
    print(f"   ⚠️  API key doesn't start with 'xkeysib-' (starts with: {api_key[:10]})")

# Step 3: Configure Brevo client
print(f"\n3. Configuring Brevo Client:")
try:
    configuration = sib_api_v3_sdk.Configuration()

    # Try different configuration methods
    print("   Testing configuration method 1: api_key['api-key']")
    configuration.api_key['api-key'] = api_key

    api_client = sib_api_v3_sdk.ApiClient(configuration)
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(api_client)
    print("   ✅ Brevo client configured successfully")
except Exception as e:
    print(f"   ❌ Failed to configure client: {e}")
    exit(1)

# Step 4: Test API connection with account endpoint
print(f"\n4. Testing API Connection (Account Info):")
try:
    account_api = sib_api_v3_sdk.AccountApi(api_client)
    account_info = account_api.get_account()
    print(f"   ✅ API connection successful!")
    print(f"   📧 Account email: {account_info.email}")
    print(f"   📊 Plan type: {account_info.plan[0].type if account_info.plan else 'N/A'}")
    print(f"   📮 Email credits: {account_info.plan[0].credits if account_info.plan else 'N/A'}")
except ApiException as e:
    print(f"   ❌ API connection failed!")
    print(f"   Status: {e.status}")
    print(f"   Reason: {e.reason}")
    print(f"   Body: {e.body}")
    print("\n   💡 Possible issues:")
    print("      1. API key might be invalid or expired")
    print("      2. API key might not have correct permissions")
    print("      3. Check your Brevo dashboard: https://app.brevo.com/settings/keys/api")
    exit(1)
except Exception as e:
    print(f"   ❌ Unexpected error: {e}")
    exit(1)

# Step 5: Test sending email
print(f"\n5. Testing Email Send:")
test_email = input("\n   Enter your email address to send a test: ").strip()

if not test_email:
    print("   ⚠️  No email provided, skipping send test")
    print("\n✅ Diagnostic complete - API key is valid!")
    exit(0)

from_email = os.environ.get('BREVO_FROM_EMAIL', 'support@chatcraft.cc')
from_name = os.environ.get('BREVO_FROM_NAME', 'ChatCraft')

print(f"   📤 Sending from: {from_name} <{from_email}>")
print(f"   📥 Sending to: {test_email}")

send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
    sender={"name": from_name, "email": from_email},
    to=[{"email": test_email, "name": "Test User"}],
    subject="Brevo Integration Test - SUCCESS!",
    html_content="""
    <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1 style="color: #5D3EC1;">✅ Success!</h1>
            <p>Your Brevo integration is working correctly!</p>
            <p><strong>Email Provider:</strong> Brevo (Sendinblue)</p>
            <p><strong>Service:</strong> ChatCraft Communications</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                This is a test email from your ChatCraft communications service.
            </p>
        </body>
    </html>
    """,
    text_content="SUCCESS! Your Brevo integration is working correctly!"
)

try:
    response = api_instance.send_transac_email(send_smtp_email)
    print(f"   ✅ Email sent successfully!")
    print(f"   📬 Message ID: {response.message_id}")
    print(f"\n   Check your inbox at: {test_email}")
except ApiException as e:
    print(f"   ❌ Failed to send email!")
    print(f"   Status: {e.status}")
    print(f"   Reason: {e.reason}")
    print(f"   Body: {e.body}")

    if e.status == 400:
        print("\n   💡 Common 400 errors:")
        print(f"      - Sender email '{from_email}' not verified in Brevo")
        print(f"      - Invalid recipient email format")
        print(f"      - Check Brevo dashboard: https://app.brevo.com/senders")
    exit(1)
except Exception as e:
    print(f"   ❌ Unexpected error: {e}")
    exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED - Brevo integration is working!")
print("=" * 60)
print("\nNext steps:")
print("1. Restart communications service")
print("2. Test via RabbitMQ: python test_email_sender.py")
print("3. Test billing notifications from billing-service")
