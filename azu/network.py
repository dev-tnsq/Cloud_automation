import logging
from azure.mgmt.network import NetworkManagementClient
from datetime import datetime, timedelta, timezone
from ._base import AzureResourceCleanup

class NetworkCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4, managed_identity_client_id=None):
        super().__init__(subscription_id, resource_group, credentials, hours, managed_identity_client_id=managed_identity_client_id)
        self.client = NetworkManagementClient(self.credentials, self.subscription_id)
        self.logger = logging.getLogger(__name__)

    def cleanup(self):
        cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=self.hours)
        self.logger.info(f"Starting Network cleanup (Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        
        try:
            networks = list(
                self.client.virtual_networks.list(self.resource_group)
                if self.resource_group
                else self.client.virtual_networks.list_all()
            )
            
            total_networks = len(networks)
            deleted_networks = 0

            for network in networks:
                try:
                    creation_time = datetime.fromisoformat(network.tags['createdTime']) if 'createdTime' in network.tags else datetime.min.replace(tzinfo=timezone.utc)
                    if creation_time < cutoff_time:
                        resource_group_name = network.id.split('/')[4]
                        self.logger.info(f"Deleting Network: {network.name} (created {(datetime.utcnow().replace(tzinfo=timezone.utc) - creation_time).total_seconds() / 3600:.1f} hours ago)")
                        self.client.virtual_networks.begin_delete(resource_group_name, network.name)
                        deleted_networks += 1
                    else:
                        self.logger.debug(f"Skipping Network {network.name}: Not reached cutoff time")
                except Exception as e:
                    self.logger.error(f"Error processing Network {network.name}: {str(e)}")

            self.logger.info(f"Network Cleanup Summary:")
            self.logger.info(f"- Total Networks found: {total_networks}")
            self.logger.info(f"- Networks deleted: {deleted_networks}")

        except Exception as e:
            self.logger.error(f"Error during Network cleanup: {str(e)}")

class NetworkSecurityGroupCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4, managed_identity_client_id=None):
        super().__init__(subscription_id, resource_group, credentials, hours, managed_identity_client_id=managed_identity_client_id)
        self.client = NetworkManagementClient(self.credentials, self.subscription_id)
        self.logger = logging.getLogger(__name__)

    def cleanup(self):
        cutoff_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=self.hours)
        self.logger.info(f"Starting Network Security Group cleanup (Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        
        try:
            nsgs = list(
                self.client.network_security_groups.list(self.resource_group)
                if self.resource_group
                else self.client.network_security_groups.list_all()
            )
            
            total_nsgs = len(nsgs)
            deleted_nsgs = 0

            for nsg in nsgs:
                try:
                    creation_time = datetime.fromisoformat(nsg.tags['createdTime']) if nsg.tags and 'createdTime' in nsg.tags else datetime.min.replace(tzinfo=timezone.utc)
                    if creation_time < cutoff_time:
                        resource_group_name = nsg.id.split('/')[4]
                        self.logger.info(f"Deleting Network Security Group: {nsg.name} (created {(datetime.utcnow().replace(tzinfo=timezone.utc) - creation_time).total_seconds() / 3600:.1f} hours ago)")
                        self.client.network_security_groups.begin_delete(resource_group_name, nsg.name)
                        deleted_nsgs += 1
                    else:
                        self.logger.debug(f"Skipping Network Security Group {nsg.name}: Not reached cutoff time")
                except Exception as e:
                    self.logger.error(f"Error processing Network Security Group {nsg.name}: {str(e)}")

            self.logger.info(f"Network Security Group Cleanup Summary:")
            self.logger.info(f"- Total Network Security Groups found: {total_nsgs}")
            self.logger.info(f"- Network Security Groups deleted: {deleted_nsgs}")

        except Exception as e:
            self.logger.error(f"Error during Network Security Group cleanup: {str(e)}")
