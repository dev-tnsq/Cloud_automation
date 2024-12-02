import logging
from azure.mgmt.compute import ComputeManagementClient
from datetime import datetime, timedelta, timezone
from ._base import AzureResourceCleanup

class SSHCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4, managed_identity_client_id=None):
        super().__init__(subscription_id, resource_group, credentials, hours, managed_identity_client_id=managed_identity_client_id)
        self.client = ComputeManagementClient(self.credentials, self.subscription_id)
        self.logger = logging.getLogger(__name__)

    def cleanup(self):
        cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=self.hours)
        self.logger.info(f"Starting SSH cleanup (Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        
        try:
            ssh_keys = list(
                self.client.ssh_public_keys.list_by_resource_group(self.resource_group)
                if self.resource_group
                else self.client.ssh_public_keys.list_by_subscription()
            )
            
            total_keys = len(ssh_keys)
            deleted_keys = 0

            for key in ssh_keys:
                try:
                    creation_time = datetime.fromisoformat(key.tags['createdTime']) if 'createdTime' in key.tags else datetime.min.replace(tzinfo=timezone.utc)
                    if creation_time < cutoff_time:
                        resource_group_name = key.id.split('/')[4]
                        self.logger.info(f"Deleting SSH Key: {key.name} (created {(datetime.utcnow().replace(tzinfo=timezone.utc) - creation_time).total_seconds() / 3600:.1f} hours ago)")
                        self.client.ssh_public_keys.delete(resource_group_name, key.name)
                        deleted_keys += 1
                    else:
                        self.logger.debug(f"Skipping SSH Key {key.name}: Not reached cutoff time")
                except Exception as e:
                    self.logger.error(f"Error processing SSH Key {key.name}: {str(e)}")

            self.logger.info(f"SSH Cleanup Summary:")
            self.logger.info(f"- Total SSH Keys found: {total_keys}")
            self.logger.info(f"- SSH Keys deleted: {deleted_keys}")

        except Exception as e:
            self.logger.error(f"Error during SSH cleanup: {str(e)}")
