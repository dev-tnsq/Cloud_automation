import logging
from azure.mgmt.network import NetworkManagementClient
from datetime import datetime, timedelta, timezone
from ._base import AzureResourceCleanup

class IPCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4, managed_identity_client_id=None):
        super().__init__(subscription_id, resource_group, credentials, hours, managed_identity_client_id=managed_identity_client_id)
        self.client = NetworkManagementClient(self.credentials, self.subscription_id)
        self.logger = logging.getLogger(__name__)

    def _get_resource_age(self, ip):
        """Determine resource age using available properties."""
        try:
            # Try different ways to get the creation time
            if hasattr(ip, 'time_created'):
                return ip.time_created
            elif hasattr(ip, 'tags') and ip.tags and 'createdTime' in ip.tags:
                return datetime.fromisoformat(ip.tags['createdTime'])
            else:
                # If no creation time found, assume it's old enough
                self.logger.warning(f"No creation time found for IP {ip.name}, assuming it's eligible for cleanup")
                return datetime.min.replace(tzinfo=timezone.utc)
        except Exception as e:
            self.logger.warning(f"Error determining age for IP {ip.name}: {e}")
            return datetime.min.replace(tzinfo=timezone.utc)

    def cleanup(self):
        cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=self.hours)
        self.logger.info(f"Starting IP cleanup (Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        
        try:
            ips = list(
                self.client.public_ip_addresses.list(self.resource_group)
                if self.resource_group
                else self.client.public_ip_addresses.list_all()
            )
            
            total_ips = len(ips)
            unattached_ips = 0
            deleted_ips = 0

            for ip in ips:
                try:
                    self.logger.debug(f"Processing IP {ip.name}")
                    if not ip.ip_configuration:
                        unattached_ips += 1
                        creation_time = self._get_resource_age(ip)
                        
                        if creation_time < cutoff_time:
                            resource_group_name = ip.id.split('/')[4]
                            self.logger.info(f"Deleting IP: {ip.name} (unattached, in resource group: {resource_group_name})")
                            self.client.public_ip_addresses.begin_delete(resource_group_name, ip.name)
                            deleted_ips += 1
                        else:
                            self.logger.debug(f"Skipping IP {ip.name}: Not reached cutoff time")
                except Exception as e:
                    self.logger.error(f"Error processing IP {ip.name}: {str(e)}")

            self.logger.info(f"IP Cleanup Summary:")
            self.logger.info(f"- Total IPs found: {total_ips}")
            self.logger.info(f"- Unattached IPs: {unattached_ips}")
            self.logger.info(f"- IPs deleted: {deleted_ips}")

        except Exception as e:
            self.logger.error(f"Error during IP cleanup: {str(e)}")
