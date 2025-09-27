"""
Module to disable SSL verification globally for development.
Import this module before any other imports that use requests/urllib3.
"""
import os
import ssl
import warnings
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# Set environment variables
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''

# Monkey patch SSL
ssl._create_default_https_context = ssl._create_unverified_context

# Monkey patch requests if it's imported
try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    # Create a session with verify=False as default
    old_request = requests.request

    def no_ssl_request(method, url, **kwargs):
        kwargs['verify'] = False
        return old_request(method, url, **kwargs)

    requests.request = no_ssl_request

    # Also patch Session
    old_session_request = requests.Session.request

    def no_ssl_session_request(self, method, url, **kwargs):
        kwargs['verify'] = False
        return old_session_request(self, method, url, **kwargs)

    requests.Session.request = no_ssl_session_request

except ImportError:
    pass

print("SSL verification has been disabled for development")