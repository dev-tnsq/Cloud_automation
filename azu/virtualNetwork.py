from ._base import AzureResourceCleanup
from azure.mgmt.network import NetworkManagementClient
import logging

class VirtualNetworkCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4, managed_identity_client_id=None):
        super().__init__(subscription_id, resource_group, credentials, hours, managed_identity_client_id)
        self.network_client = NetworkManagementClient(self.credentials, self.subscription_id)
        self.logger = logging.getLogger(__name__)

    def get_resource_group_from_id(self, resource_id):
        """Extract resource group name from Azure resource ID."""
        parts = resource_id.split('/')
        try:
            return parts[parts.index('resourceGroups') + 1]
        except (ValueError, IndexError):
            self.logger.error(f"Could not extract resource group from ID: {resource_id}")
            return None

    def cleanup(self):
        """Clean up unused virtual networks."""
        self.logger.info("Starting Virtual Network cleanup")
        
        try:
            vnets = list(
                self.network_client.virtual_networks.list(self.resource_group)
                if self.resource_group
                else self.network_client.virtual_networks.list_all()
            )
            
            total_vnets = len(vnets)
            unused_vnets = 0
            deleted_vnets = 0

            for vnet in vnets:
                try:
                    has_resources = False
                    subnets = self.network_client.subnets.list(
                        self.get_resource_group_from_id(vnet.id),
                        vnet.name
                    )
                    
                    for subnet in subnets:
                        if subnet.ip_configurations or subnet.network_security_group:
                            has_resources = True
                            break
                    
                    if not has_resources:
                        unused_vnets += 1
                        self.logger.info(f"Deleting unused virtual network: {vnet.name}")
                        self.network_client.virtual_networks.begin_delete(
                            self.get_resource_group_from_id(vnet.id),
                            vnet.name
                        ).wait()
                        deleted_vnets += 1
                    else:
                        self.logger.debug(f"Skipping Virtual Network {vnet.name}: Has active resources")
                except Exception as e:
                    self.logger.error(f"Error processing Virtual Network {vnet.name}: {str(e)}")

            self.logger.info(f"Virtual Network Cleanup Summary:")
            self.logger.info(f"- Total Virtual Networks found: {total_vnets}")
            self.logger.info(f"- Unused Virtual Networks: {unused_vnets}")
            self.logger.info(f"- Virtual Networks deleted: {deleted_vnets}")

        except Exception as e:
            self.logger.error(f"Error during Virtual Network cleanup: {str(e)}")
