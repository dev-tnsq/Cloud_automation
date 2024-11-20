from .vm import VMCleanup
from .disk import DiskCleanup
from .ip import IPCleanup
from .nic import NICCleanup
from .network import NetworkEndpointGroupCleanup
from .ssh import SSHKeyCleanup
from .auth import get_gcp_credentials
import logging

class GCPCleanupOrchestrator:
    def __init__(self, project_id, service_account_key_path=None, hours=4, disk_hours=4):
        """
        Initialize the GCP cleanup orchestrator.
        
        Args:
            project_id (str): GCP project ID
            service_account_key_path (str, optional): Path to service account key file
            hours (int, optional): Hours threshold for VM, IP, NIC, and NEG cleanup
            disk_hours (int, optional): Hours threshold for Disk cleanup
        """
        self.project_id = project_id
        self.credentials = None
        self.hours = hours
        self.disk_hours = disk_hours
        if service_account_key_path:
            self.credentials = get_gcp_credentials(service_account_key_path)
            if self.credentials:
                logging.info("Credentials obtained successfully.")
            else:
                logging.error("Failed to obtain credentials.")
        logging.info(self.credentials)
    def run_all_cleanups(self, cleanup_types=None):
        """
        Run all specified cleanup operations.
        
        Args:
            cleanup_types (list, optional): List of cleanup types to run.
                                          If None, runs all cleanups.
        """
        logging.debug(f"Running cleanups for types: {cleanup_types}")
        cleanup_map = {
            'vm': lambda: VMCleanup(self.project_id, self.hours),
            'disk': lambda: DiskCleanup(self.project_id, self.disk_hours),
            'ip': lambda: IPCleanup(self.project_id, self.hours),
            'nic': lambda: NICCleanup(self.project_id, self.hours),
            'neg': lambda: NetworkEndpointGroupCleanup(self.project_id, self.hours),
            'ssh': SSHKeyCleanup
        }

        if cleanup_types is None:
            cleanup_types = cleanup_map.keys()

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

