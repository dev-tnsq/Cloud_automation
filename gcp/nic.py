from google.cloud import compute_v1
from datetime import datetime, timedelta
import pytz
from ._base import GCPResourceCleanup
import logging

class NICCleanup(GCPResourceCleanup):
    def __init__(self, project_id, hours):
        super().__init__(project_id)
        self.hours = hours

    def _get_zones(self):
        client = compute_v1.ZonesClient()
        zones = client.list(project=self.project_id)
        return [zone.name for zone in zones]

    def cleanup(self):
        client = compute_v1.InstancesClient()
        threshold_time = datetime.now(pytz.UTC) - timedelta(hours=self.hours)
        
        for zone in self._get_zones():
            try:
                instances = client.list(project=self.project_id, zone=zone)
                for instance in instances:
                    if instance.network_interfaces:
                        for nic in instance.network_interfaces:
                            logging.info(f"Found NIC: {nic.name} in zone {zone}")
                            if not nic.network:  # If NIC is not attached to any network
                                creation_time = datetime.fromisoformat(instance.creation_timestamp.replace('Z', '+00:00'))
                                if creation_time < threshold_time:
                                    logging.info(f"Deleting unattached NIC: {nic.name}")
                                    operation = client.delete_access_config(
                                        project=self.project_id,
                                        zone=zone,
                                        instance=instance.name,
                                        network_interface=nic.name,
                                        access_config='external-nat'
                                    )
                                else:
                                    logging.info(f"NIC {nic.name} was recently created, keeping it")
            except Exception as e:
                logging.error(f"Error processing NICs in zone {zone}: {e}")
