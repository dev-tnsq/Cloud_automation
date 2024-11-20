from google.cloud import compute_v1
from datetime import datetime, timedelta
import pytz
from ._base import GCPResourceCleanup
import logging

class IPCleanup(GCPResourceCleanup):
    def __init__(self, project_id, hours):
        super().__init__(project_id)
        self.hours = hours

    def _get_regions(self):
        client = compute_v1.RegionsClient()
        regions = client.list(project=self.project_id)
        return [region.name for region in regions]

    def cleanup(self):
        client = compute_v1.AddressesClient()
        threshold_time = datetime.now(pytz.UTC) - timedelta(hours=self.hours)
        
        for region in self._get_regions():
            addresses = client.list(project=self.project_id, region=region)
            for address in addresses:
                logging.info(f"Found IP address: {address.name} in region {region}")
                if not address.users:
                    creation_time = datetime.fromisoformat(address.creation_timestamp.replace('Z', '+00:00'))
                    if creation_time < threshold_time:
                        logging.info(f"Deleting unattached IP address: {address.name}")
                        client.delete(project=self.project_id, region=region, address=address.name)
                    else:
                        logging.info(f"IP address {address.name} was recently created, keeping it")
