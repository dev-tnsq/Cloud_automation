from azure.mgmt.compute import ComputeManagementClient
from datetime import datetime, timedelta
from ._base import AzureResourceCleanup

class DiskCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, disk_hours=4):
        super().__init__(subscription_id, resource_group, credentials, disk_hours=disk_hours)
        self.client = ComputeManagementClient(self.credentials, self.subscription_id)

    def cleanup(self):
        cutoff_time = datetime.utcnow() - timedelta(hours=self.disk_hours)
        
        try:
            if self.resource_group:
                disks = self.client.disks.list_by_resource_group(self.resource_group)
            else:
                disks = self.client.disks.list()

            for disk in disks:
                if not disk.managed_by and disk.time_created < cutoff_time:
                    self.log_deletion("unattached disk", disk.name)
                    self.client.disks.begin_delete(disk.resource_group_name, disk.name)
        except Exception as e:
            print(f"Error cleaning up disks: {str(e)}")
