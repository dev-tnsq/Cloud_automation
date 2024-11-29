from azure.mgmt.network import NetworkManagementClient
from datetime import datetime, timedelta
from ._base import AzureResourceCleanup

class IPCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4):
        super().__init__(subscription_id, resource_group, credentials, hours)
        self.client = NetworkManagementClient(self.credentials, self.subscription_id)
        self.hours = hours

    def cleanup(self):
        cutoff_time = datetime.utcnow() - timedelta(hours=self.hours)
        
        try:
            if self.resource_group:
                ips = self.client.public_ip_addresses.list(self.resource_group)
            else:
                ips = self.client.public_ip_addresses.list_all()

            for ip in ips:
                if not ip.ip_configuration and ip.time_created < cutoff_time:
                    self.log_deletion("unattached IP address", ip.name)
                    self.client.public_ip_addresses.begin_delete(ip.resource_group_name, ip.name)
        except Exception as e:
            print(f"Error cleaning up IP addresses: {str(e)}")
