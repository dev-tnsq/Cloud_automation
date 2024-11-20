from google.cloud import compute_v1
from ._base import GCPResourceCleanup
from datetime import datetime, timedelta
import pytz
import logging

class NetworkEndpointGroupCleanup(GCPResourceCleanup):
    def __init__(self, project_id, hours):
        super().__init__(project_id)
        self.hours = hours

    def cleanup(self):
        client = compute_v1.NetworkEndpointGroupsClient()
        threshold_time = datetime.now(pytz.UTC) - timedelta(hours=self.hours)
        
        for zone in self._get_zones():
            negs = client.list(project=self.project_id, zone=zone)
            for neg in negs:
                logging.info(f"Found network endpoint group: {neg.name} in zone {zone}")
                if not neg.size:
                    creation_time = datetime.fromisoformat(neg.creation_timestamp.replace('Z', '+00:00'))
                    if creation_time < threshold_time:
                        print(f"Deleting unused network endpoint group: {neg.name}")
                        client.delete(project=self.project_id, zone=zone, network_endpoint_group=neg.name)
                    else:
                        logging.info(f"Network endpoint group {neg.name} was recently created, keeping it")

    def _get_zones(self):
        client = compute_v1.ZonesClient()
        zones = client.list(project=self.project_id)
        return [zone.name for zone in zones]
