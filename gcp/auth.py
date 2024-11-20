from google.oauth2 import service_account

def get_gcp_credentials(service_account_key_path):
    """Create credentials from service account key file."""
    credentials = service_account.Credentials.from_service_account_file(
        service_account_key_path,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    return credentials
