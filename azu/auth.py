from azure.identity import ClientSecretCredential, ManagedIdentityCredential

def get_azure_credentials(client_id=None):
    return ManagedIdentityCredential(client_id=client_id)
