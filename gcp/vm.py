from google.cloud import compute_v1
from ._base import GCPResourceCleanup
from datetime import datetime, timedelta
import pytz
import logging

class VMCleanup(GCPResourceCleanup):
    def __init__(self, project_id, hours):
        super().__init__(project_id)
        self.hours = hours

    def cleanup(self):
        client = compute_v1.InstancesClient()
        threshold_time = datetime.now(pytz.UTC) - timedelta(hours=self.hours)
        
        for zone in self._get_zones():
            instances = client.list(project=self.project_id, zone=zone)
            
            for instance in instances:
                logging.info(f"Found instance: {instance.name} in zone {zone}")
                if instance.status == 'TERMINATED':
                    creation_time = datetime.fromisoformat(instance.last_terminated_timestamp.replace('Z', '+00:00'))
                    if creation_time < threshold_time:
                        logging.info(f"Deleting unattached instance: {instance.name}")
                        client.delete(project=self.project_id, zone=zone, instance=instance.name)
                    else:
                        logging.info(f"Instance {instance.name} was recently terminated, keeping it")
    
    def _get_zones(self):
        client = compute_v1.ZonesClient()
        zones = client.list(project=self.project_id)
        return [zone.name for zone in zones]
