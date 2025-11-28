import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

# Set your API key
os.environ['BREVO_API_KEY'] = 'YOUR_API_KEY_HERE'

# Configure Brevo
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = os.environ.get('BREVO_API_KEY')

# Create API instance
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
    sib_api_v3_sdk.ApiClient(configuration)
)

# Send test email
send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
    sender={"name": "ChatCraft", "email": "support@chatcraft.cc"},
    to=[{"email": "adeomoboya@gmail.com", "name": "Test User"}],
    subject="Brevo Migration Test",
    html_content="<html><body><h1>Success!</h1><p>Brevo is working correctly.</p></body></html>"
)

try:
    response = api_instance.send_transac_email(send_smtp_email)
    print(f"✅ Email sent successfully!")
    print(f"Message ID: {response.message_id}")
except ApiException as e:
    print(f"❌ Failed to send email: {e}")