from azure.mgmt.compute import ComputeManagementClient
from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.mgmt.compute.models import VirtualMachine
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from ._base import AzureResourceCleanup
import logging

class VMCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id: str, resource_group: Optional[str] = None, credentials=None, hours: int = 720, managed_identity_client_id=None):
        super().__init__(subscription_id, resource_group, credentials, hours, managed_identity_client_id=managed_identity_client_id)
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
        self.logger.info(f"Starting VM cleanup (Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
        
        try:
            vms: List[VirtualMachine] = list(
                self.client.virtual_machines.list(self.resource_group)
                if self.resource_group
                else self.client.virtual_machines.list_all()
            )
            
            total_vms = len(vms)
            eligible_vms = 0
            deleted_vms = 0

            for vm in vms:
                try:
                    status = self.get_vm_status(vm.id.split('/')[4], vm.name)
                    
                    if status and status.lower() in ['deallocated', 'stopped']:
                        eligible_vms += 1
                        if hasattr(vm, 'time_created') and vm.time_created and vm.time_created < cutoff_time:
                            self.logger.info(f"Deleting VM: {vm.name} ({status}, idle for {(datetime.now(timezone.utc) - vm.time_created).total_seconds() / 3600:.1f} hours)")
                            self.client.virtual_machines.begin_delete(
                                vm.id.split('/')[4],
                                vm.name
                            )
                            deleted_vms += 1
                        else:
                            self.logger.debug(f"Skipping VM {vm.name}: Not reached cutoff time")

                except Exception as e:
                    self.logger.error(f"Error processing VM {vm.name}: {str(e)}")

            self.logger.info(f"VM Cleanup Summary:")
            self.logger.info(f"- Total VMs found: {total_vms}")
            self.logger.info(f"- Eligible for cleanup (stopped/deallocated): {eligible_vms}")
            self.logger.info(f"- VMs deleted: {deleted_vms}")

        except Exception as e:
            self.logger.error(f"Error during VM cleanup: {str(e)}")


