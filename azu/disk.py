import logging
from azure.mgmt.compute import ComputeManagementClient
from datetime import datetime, timedelta, timezone
from ._base import AzureResourceCleanup

class DiskCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, disk_hours=4, managed_identity_client_id=None):
        super().__init__(subscription_id, resource_group, credentials, disk_hours=disk_hours, managed_identity_client_id=managed_identity_client_id)
        self.client = ComputeManagementClient(self.credentials, self.subscription_id)
        self.logger = logging.getLogger(__name__)

    def cleanup(self):
        cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=self.disk_hours)
        self.logger.info(f"Starting Disk cleanup (Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        
        try:
            disks = list(
                self.client.disks.list_by_resource_group(self.resource_group)
                if self.resource_group
                else self.client.disks.list()
            )
            
            total_disks = len(disks)
            unattached_disks = 0
            deleted_disks = 0

            for disk in disks:
                try:
                    if not disk.managed_by:
                        unattached_disks += 1
                        if disk.time_created and disk.time_created.replace(tzinfo=timezone.utc) < cutoff_time:
                            resource_group_name = disk.id.split('/')[4]
                            self.logger.info(f"Deleting Disk: {disk.name} (unattached for {(datetime.utcnow().replace(tzinfo=timezone.utc) - disk.time_created.replace(tzinfo=timezone.utc)).total_seconds() / 3600:.1f} hours)")
                            self.client.disks.begin_delete(resource_group_name, disk.name)
                            deleted_disks += 1
                        else:
                            self.logger.debug(f"Skipping Disk {disk.name}: Not reached cutoff time")
                except Exception as e:
                    self.logger.error(f"Error processing Disk {disk.name}: {str(e)}")

            self.logger.info(f"Disk Cleanup Summary:")
            self.logger.info(f"- Total Disks found: {total_disks}")
            self.logger.info(f"- Unattached Disks: {unattached_disks}")
            self.logger.info(f"- Disks deleted: {deleted_disks}")

        except Exception as e:
            self.logger.error(f"Error during Disk cleanup: {str(e)}")
