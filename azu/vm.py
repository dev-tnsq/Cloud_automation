from azure.mgmt.compute import ComputeManagementClient
from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.mgmt.compute.models import VirtualMachine
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from ._base import AzureResourceCleanup
import logging

class VMCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id: str, resource_group: Optional[str] = None, credentials=None, hours: int = 720):
        super().__init__(subscription_id, resource_group, credentials, hours)
        self.client = ComputeManagementClient(self.credentials, self.subscription_id)
        self.logger = logging.getLogger(__name__)
        self.hours = hours

    def get_vm_status(self, resource_group: str, vm_name: str) -> Optional[str]:
        try:
            view = self.client.virtual_machines.instance_view(resource_group, vm_name)
            for status in view.statuses or []:
                if status.code.startswith('PowerState/'):
                    return status.code.split('/')[-1]
            return None
        except ResourceNotFoundError:
            self.logger.warning(f"VM {vm_name} not found")
            return None
        except Exception as e:
            self.logger.error(f"Error getting VM status: {str(e)}")
            return None

    def cleanup(self) -> None:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.hours)
        
        try:
            vms: List[VirtualMachine] = list(
                self.client.virtual_machines.list(self.resource_group)
                if self.resource_group
                else self.client.virtual_machines.list_all()
            )

            for vm in vms:
                try:
                    status = self.get_vm_status(vm.id.split('/')[4], vm.name)
                    
                    if status and status.lower() in ['deallocated', 'stopped']:
                        if vm.time_created and vm.time_created < cutoff_time:
                            self.log_deletion("unused VM", vm.name)
                            self.client.virtual_machines.begin_delete(
                                vm.id.split('/')[4],  # resource group name
                                vm.name
                            )
                except AzureError as e:
                    self.logger.error(f"Azure error processing VM {vm.name}: {str(e)}")
                except Exception as e:
                    self.logger.error(f"Error processing VM {vm.name}: {str(e)}")

        except Exception as e:
            self.logger.error(f"Error cleaning up VMs: {str(e)}")

if __name__ == "__main__":
    # Example usage
    subscription_id = "your-subscription-id"
    resource_group = "your-resource-group"
    vm_cleanup = VMCleanup(subscription_id, resource_group)
    
    # Cleanup unused VMs
    vm_cleanup.cleanup()
