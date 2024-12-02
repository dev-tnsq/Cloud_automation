from azure.mgmt.network import NetworkManagementClient
from datetime import datetime, timedelta, timezone
import logging
from ._base import AzureResourceCleanup

class NICCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4, managed_identity_client_id=None):
        super().__init__(subscription_id, resource_group, credentials, hours, managed_identity_client_id=managed_identity_client_id)
        self.client = NetworkManagementClient(self.credentials, self.subscription_id)
        self.logger = logging.getLogger(__name__)

    def _get_resource_age(self, nic):
        """Determine resource age using available properties."""
        try:
            if hasattr(nic, 'tags') and nic.tags and 'createdTime' in nic.tags:
                return datetime.fromisoformat(nic.tags['createdTime'])
            else:
                self.logger.warning(f"No creation time found for NIC {nic.name}, assuming it's eligible for cleanup")
                return datetime.min.replace(tzinfo=timezone.utc)
        except Exception as e:
            self.logger.warning(f"Error determining age for NIC {nic.name}: {e}")
            return datetime.min.replace(tzinfo=timezone.utc)

    def cleanup(self):
        cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=self.hours)
        self.logger.info(f"Starting NIC cleanup (Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        
        try:
            nics = list(
                self.client.network_interfaces.list(self.resource_group)
                if self.resource_group
                else self.client.network_interfaces.list_all()
            )
            
            total_nics = len(nics)
            unattached_nics = 0
            deleted_nics = 0

            for nic in nics:
                try:
                    if not nic.virtual_machine:
                        unattached_nics += 1
                        creation_time = self._get_resource_age(nic)
                        if creation_time < cutoff_time:
                            resource_group_name = nic.id.split('/')[4]
                            self.logger.info(f"Deleting NIC: {nic.name} (unattached for {(datetime.utcnow().replace(tzinfo=timezone.utc) - creation_time).total_seconds() / 3600:.1f} hours)")
                            self.client.network_interfaces.begin_delete(resource_group_name, nic.name)
                            deleted_nics += 1
                        else:
                            self.logger.debug(f"Skipping NIC {nic.name}: Not reached cutoff time")
                except Exception as e:
                    self.logger.error(f"Error processing NIC {nic.name}: {str(e)}")

            self.logger.info(f"NIC Cleanup Summary:")
            self.logger.info(f"- Total NICs found: {total_nics}")
            self.logger.info(f"- Unattached NICs: {unattached_nics}")
            self.logger.info(f"- NICs deleted: {deleted_nics}")

        except Exception as e:
            self.logger.error(f"Error during NIC cleanup: {str(e)}")
