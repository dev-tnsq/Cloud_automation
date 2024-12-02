import logging
from azure.core.exceptions import AzureError
from azure.identity import AzureCliCredential, ManagedIdentityCredential, DefaultAzureCredential
from .disk import DiskCleanup
from .ip import IPCleanup
from .nic import NICCleanup
from .vm import VMCleanup
from .ssh import SSHCleanup
from .auth import get_azure_credentials
from .network import NetworkCleanup
from .network import NetworkSecurityGroupCleanup
from .virtualNetwork import VirtualNetworkCleanup

class AzureCleanupOrchestrator:
    def __init__(self, subscription_id, resource_group=None, managed_identity_client_id=None, hours=4, disk_hours=4):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.hours = hours
        self.disk_hours = disk_hours
        self.managed_identity_client_id = managed_identity_client_id
        
        try:
            self.credentials = AzureCliCredential()
            self.credentials.get_token("https://management.azure.com/.default")
        except Exception:
            try:
                self.credentials = ManagedIdentityCredential(
                    client_id=managed_identity_client_id
                )
                self.credentials.get_token("https://management.azure.com/.default")
            except Exception:
                self.credentials = DefaultAzureCredential()
        
        logging.info("AzureCleanupOrchestrator initialized.")

    def run_all_cleanups(self, cleanup_types=None):
        """
        Run all specified cleanup operations.
        
        Args:
            cleanup_types (list, optional): List of cleanup types to run.
                                            If None, runs all cleanups.
        """
        if cleanup_types is None:
            cleanup_types = ['vm', 'disk', 'ip', 'nic', 'ssh', 'vnet', 'nsg']

        logging.info(f"Starting cleanup for: {', '.join(cleanup_types)}")
        logging.debug(f"Running cleanups for types: {cleanup_types}")
        cleanup_map = {
            'vm': lambda: VMCleanup(self.subscription_id, self.resource_group, self.credentials, self.hours, managed_identity_client_id=self.managed_identity_client_id),
            'disk': lambda: DiskCleanup(self.subscription_id, self.resource_group, self.credentials, self.disk_hours, managed_identity_client_id=self.managed_identity_client_id),
            'ip': lambda: IPCleanup(self.subscription_id, self.resource_group, self.credentials, self.hours, managed_identity_client_id=self.managed_identity_client_id),
            'nic': lambda: NICCleanup(self.subscription_id, self.resource_group, self.credentials, self.hours, managed_identity_client_id=self.managed_identity_client_id),
            'ssh': lambda: SSHCleanup(self.subscription_id, self.resource_group, self.credentials, self.hours, managed_identity_client_id=self.managed_identity_client_id),
            'vnet': lambda: VirtualNetworkCleanup(self.subscription_id, self.resource_group, self.credentials, self.hours, managed_identity_client_id=self.managed_identity_client_id),
            'nsg': lambda: NetworkSecurityGroupCleanup(self.subscription_id, self.resource_group, self.credentials, self.hours, managed_identity_client_id=self.managed_identity_client_id)
        }

        errors = []
        for cleanup_type in cleanup_types:
            if cleanup_type not in cleanup_map:
                logging.warning(f"Unknown cleanup type '{cleanup_type}'")
                continue

            try:
                cleanup_class = cleanup_map[cleanup_type]
                cleanup_instance = cleanup_class()
                logging.debug(f"Starting {cleanup_type} cleanup")
                cleanup_instance.cleanup()
                logging.debug(f"Completed {cleanup_type} cleanup")
            except AzureError as e:
                error_msg = f"Azure error during {cleanup_type} cleanup: {str(e)}"
                errors.append(error_msg)
                logging.error(error_msg)
            except Exception as e:
                error_msg = f"Error during {cleanup_type} cleanup: {str(e)}"
                errors.append(error_msg)
                logging.error(error_msg)

        if errors:
            logging.error("The following errors occurred during cleanup:")
            for error in errors:
                logging.error(f"- {error}")
            return False
        return True
