"""
Working Brevo Email Test Script
Run this to send a test email and verify the integration
"""
import os
import sys
from dotenv import load_dotenv
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

# Load environment variables from .env file
load_dotenv()

def send_test_email(to_email: str):
    """Send a test email via Brevo"""

    # Get configuration from environment
    api_key = os.environ.get('BREVO_API_KEY')
    from_email = os.environ.get('BREVO_FROM_EMAIL', 'support@chatcraft.cc')
    from_name = os.environ.get('BREVO_FROM_NAME', 'ChatCraft')

    if not api_key:
        print("❌ ERROR: BREVO_API_KEY not found in environment")
        print("Make sure .env file exists and contains BREVO_API_KEY")
        return False

    print(f"📧 Sending test email...")
    print(f"   From: {from_name} <{from_email}>")
    print(f"   To: {to_email}")

    # Configure Brevo
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = api_key

    # Create API instance
    api_client = sib_api_v3_sdk.ApiClient(configuration)
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(api_client)

    # Create email
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        sender={"name": from_name, "email": from_email},
        to=[{"email": to_email, "name": "Test User"}],
        subject="✅ Brevo Integration Test - ChatCraft",
        html_content="""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 20px auto; padding: 20px; background-color: #f5f5f5;">
                <div style="background: linear-gradient(135deg, #5D3EC1 0%, #3E5DC1 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                    <h1 style="color: white; margin: 0;">✅ SUCCESS!</h1>
                </div>
                <div style="background-color: white; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #333;">Your Brevo Integration is Working!</h2>
                    <p style="color: #666; line-height: 1.6;">
                        This test email confirms that your ChatCraft communications service
                        is successfully connected to Brevo (formerly Sendinblue) and can send emails.
                    </p>
                    <div style="background-color: #f0f0f0; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 5px 0;"><strong>✓</strong> Brevo API authenticated</p>
                        <p style="margin: 5px 0;"><strong>✓</strong> Email service initialized</p>
                        <p style="margin: 5px 0;"><strong>✓</strong> Sender verified</p>
                        <p style="margin: 5px 0;"><strong>✓</strong> Email delivered</p>
                    </div>
                    <h3 style="color: #333;">What's Next?</h3>
                    <ul style="color: #666; line-height: 1.8;">
                        <li>Test via RabbitMQ: <code>python test_email_sender.py</code></li>
                        <li>Start communications service and test API endpoint</li>
                        <li>Test billing notifications from billing-service</li>
                        <li>Monitor emails in Brevo dashboard</li>
                    </ul>
                    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
                    <p style="color: #999; font-size: 12px; text-align: center;">
                        Sent from ChatCraft Communications Service via Brevo
                    </p>
                </div>
            </body>
        </html>
        """,
        text_content="""
        SUCCESS! Your Brevo Integration is Working!

        This test email confirms that your ChatCraft communications service
        is successfully connected to Brevo and can send emails.

        ✓ Brevo API authenticated
        ✓ Email service initialized
        ✓ Sender verified
        ✓ Email delivered

        What's Next?
        - Test via RabbitMQ: python test_email_sender.py
        - Start communications service and test API endpoint
        - Test billing notifications from billing-service
        - Monitor emails in Brevo dashboard

        Sent from ChatCraft Communications Service via Brevo
        """
    )

    # Send email
    try:
        response = api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Email sent successfully!")
        print(f"   Message ID: {response.message_id}")
        print(f"\n📬 Check your inbox at: {to_email}")
        print(f"📊 View in Brevo dashboard: https://app.brevo.com/email/transactional")
        return True

    except ApiException as e:
        print(f"❌ Failed to send email!")
        print(f"   Status: {e.status}")
        print(f"   Reason: {e.reason}")

        if e.status == 401:
            print("\n💡 401 Unauthorized - API Key Issue:")
            print("   - Check that BREVO_API_KEY in .env is correct")
            print("   - Verify API key at: https://app.brevo.com/settings/keys/api")
            print("   - Make sure API key has 'Send transactional emails' permission")

        elif e.status == 400:
            print("\n💡 400 Bad Request - Sender or Content Issue:")
            print(f"   - Verify sender email '{from_email}' at: https://app.brevo.com/senders")
            print("   - Make sure sender email is authorized in your Brevo account")
            print("   - Check that recipient email format is valid")

        elif e.status == 403:
            print("\n💡 403 Forbidden - Permission Issue:")
            print("   - Your account may not have permission to send emails")
            print("   - Check your Brevo plan limits and permissions")

        print(f"\n📄 Full response: {e.body}")
        return False

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("BREVO EMAIL TEST")
    print("=" * 60)
    print()

    # Get recipient email
    if len(sys.argv) > 1:
        recipient = sys.argv[1]
    else:
        recipient = input("Enter recipient email address: ").strip()

    if not recipient:
        print("❌ No recipient email provided")
        print("\nUsage: python test_brevo_working.py your-email@example.com")
        sys.exit(1)

    # Send test email
    success = send_test_email(recipient)

    if success:
        print("\n" + "=" * 60)
        print("✅ TEST PASSED - Brevo integration is fully functional!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED - See errors above")
        print("=" * 60)
        sys.exit(1)
