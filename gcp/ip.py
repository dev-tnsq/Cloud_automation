from google.cloud import compute_v1
from ._base import GCPResourceCleanup

class IPCleanup(GCPResourceCleanup):
    def cleanup(self):
        client = compute_v1.AddressesClient()
        for region in self._get_regions():
            addresses = client.list(project=self.project_id, region=region)
            for address in addresses:
                if not address.users:
                    print(f"Deleting unattached IP address: {address.name}")
                    client.delete(project=self.project_id, region=region, address=address.name)
    
    def _get_regions(self):
        client = compute_v1.RegionsClient()
        regions = client.list(project=self.project_id)
        return [region.name for region in regions]
