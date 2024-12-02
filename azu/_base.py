from azure.identity import (
    DefaultAzureCredential,
    ManagedIdentityCredential,
    AzureCliCredential,
    ChainedTokenCredential
)
import logging
import os

class AzureResourceCleanup:
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4, disk_hours=4, managed_identity_client_id=None):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.hours = hours
        self.disk_hours = disk_hours
        
        if credentials:
            self.credentials = credentials
        else:
            self.credentials = self._get_credentials(managed_identity_client_id)

    def _get_credentials(self, managed_identity_client_id):
        """Get credentials with fallback mechanisms."""
        try:
            cli_credential = AzureCliCredential()
            cli_credential.get_token("https://management.azure.com/.default")
            return cli_credential
        except Exception:
            try:
                managed_credential = ManagedIdentityCredential(
                    client_id=managed_identity_client_id
                )
                managed_credential.get_token("https://management.azure.com/.default")
                return managed_credential
            except Exception:
                return DefaultAzureCredential()

    def cleanup(self):
        raise NotImplementedError("Cleanup method must be implemented by subclasses")

    def log_deletion(self, resource_type, resource_name):
        logging.info(f"Deleting {resource_type}: {resource_name}")
