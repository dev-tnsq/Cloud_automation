from google.cloud import compute_v1
from ._base import GCPResourceCleanup
from .utils import is_resource_old_enough

class NetworkEndpointGroupCleanup(GCPResourceCleanup):
    def cleanup(self):
        client = compute_v1.NetworkEndpointGroupsClient()
        
        for zone in self._get_zones():
            negs = client.list(project=self.project_id, zone=zone)
            for neg in negs:
                if not neg.size and is_resource_old_enough(neg.creation_timestamp):
                    print(f"Deleting unused network endpoint group: {neg.name}")
                    client.delete(project=self.project_id, zone=zone, network_endpoint_group=neg.name)
    
    def _get_zones(self):
        client = compute_v1.ZonesClient()
        zones = client.list(project=self.project_id)
        return [zone.name for zone in zones]
