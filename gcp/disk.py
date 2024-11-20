from google.cloud import compute_v1
from datetime import datetime, timedelta
import pytz
from ._base import GCPResourceCleanup
import logging

class DiskCleanup(GCPResourceCleanup):
    def __init__(self, project_id, hours):
        super().__init__(project_id)
        self.hours = hours

    def _get_zones(self):
        client = compute_v1.ZonesClient()
        zones = client.list(project=self.project_id)
        return [zone.name for zone in zones]

    def _get_last_detach_time(self, disk):
        """Get the last time the disk was detached from an instance."""
        if hasattr(disk, 'lastDetachTimestamp'):
            return disk.lastDetachTimestamp
        if hasattr(disk, 'lastAttachTimestamp'):
            # If disk has never been detached but has been attached before
            return None
        # If disk has never been attached, use creation time
        return disk.creation_timestamp

    def _parse_timestamp(self, timestamp_str):
        """Convert GCP timestamp to timezone-aware datetime object."""
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

    def cleanup(self):
        client = compute_v1.DisksClient()
        threshold_time = datetime.now(pytz.UTC) - timedelta(hours=self.hours)
        logging.info(f"Cleaning project: {self.project_id}")
        
        # List disks in each zone
        for zone in self._get_zones():
            
            try:
                request = compute_v1.ListDisksRequest(
                    project=self.project_id,
                    zone=zone
                )
                disks = client.list(request=request)
                
                for disk in disks:
                    logging.info(f"Found disk: {disk.name} in zone {zone}")
                    
                    if disk.users:
                        logging.info(f"Disk {disk.name} is currently attached, skipping")
                        continue
                        
                    last_detach_time = self._get_last_detach_time(disk)
                    if not last_detach_time:
                        logging.info(f"Disk {disk.name} has no detach history, skipping")
                        continue

                    detach_time = self._parse_timestamp(last_detach_time)
                    logging.info(f"Disk {disk.name} was last detached at: {detach_time}")
                    if detach_time < threshold_time:
                        logging.info(f"Deleting unattached disk: {disk.name} in zone: {zone}")
                        logging.info(f"Last detached: {last_detach_time}")
                        try:
                            operation = client.delete(
                                project=self.project_id,
                                zone=zone,
                                disk=disk.name
                            )
                            logging.info(f"Delete operation started: {operation.name}")
                        except Exception as e:
                            logging.error(f"Failed to delete disk {disk.name} in zone {zone}: {e}")
                    else:
                        logging.info(f"Disk {disk.name} was recently detached, keeping it")
            except Exception as e:
                logging.error(f"Error listing disks in zone {zone}: {e}")
