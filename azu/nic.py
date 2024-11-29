from azure.mgmt.network import NetworkManagementClient
from datetime import datetime, timedelta
from ._base import AzureResourceCleanup

class NICCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4):
        super().__init__(subscription_id, resource_group, credentials, hours)
        self.client = NetworkManagementClient(self.credentials, self.subscription_id)
        self.hours = hours

    def cleanup(self):
        cutoff_time = datetime.utcnow() - timedelta(hours=self.hours)
        
        if self.resource_group:
            nics = self.client.network_interfaces.list(self.resource_group)
        else:
            nics = self.client.network_interfaces.list_all()

        for nic in nics:
            if not nic.virtual_machine and nic.time_created < cutoff_time:
                print(f"Deleting unattached NIC: {nic.name}")
                self.client.network_interfaces.begin_delete(
                    nic.resource_group_name, nic.name)
