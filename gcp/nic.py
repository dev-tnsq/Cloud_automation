from google.cloud import compute_v1
from ._base import GCPResourceCleanup

class NICCleanup(GCPResourceCleanup):
    def cleanup(self):
        client = compute_v1.NetworkInterfacesClient()
        instances_client = compute_v1.InstancesClient()
        
        for zone in self._get_zones():
            instances = instances_client.list(project=self.project_id, zone=zone)
            for instance in instances:
                for nic in instance.network_interfaces:
                    if not nic.network:
                        print(f"Deleting unattached NIC: {nic.name}")
                        client.delete(project=self.project_id, zone=zone, instance=instance.name, network_interface=nic.name)
    
    def _get_zones(self):
        client = compute_v1.ZonesClient()
        zones = client.list(project=self.project_id)
        return [zone.name for zone in zones]
