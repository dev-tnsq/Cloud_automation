from azure.mgmt.compute import ComputeManagementClient
from datetime import datetime, timedelta
from ._base import AzureResourceCleanup

class SSHCleanup(AzureResourceCleanup):
    def __init__(self, subscription_id, resource_group=None, credentials=None, hours=4):
        super().__init__(subscription_id, resource_group, credentials, hours)
        self.client = ComputeManagementClient(self.credentials, self.subscription_id)
        self.hours = hours

    def cleanup(self):
        cutoff_time = datetime.utcnow() - timedelta(hours=self.hours)
        
        try:
            if self.resource_group:
                vms = self.client.virtual_machines.list(self.resource_group)
            else:
                vms = self.client.virtual_machines.list_all()

            for vm in vms:
                if vm.os_profile and vm.os_profile.linux_configuration and vm.os_profile.linux_configuration.ssh:
                    if vm.time_created < cutoff_time:
                        self.log_deletion("SSH key", vm.name)
                        vm.os_profile.linux_configuration.ssh.public_keys = []
                        self.client.virtual_machines.begin_create_or_update(vm.resource_group_name, vm.name, vm)
        except Exception as e:
            print(f"Error cleaning up SSH keys: {str(e)}")
