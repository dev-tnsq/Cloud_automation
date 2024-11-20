from google.cloud import compute_v1
from ._base import GCPResourceCleanup
class SSHKeyCleanup(GCPResourceCleanup):
    def cleanup(self):
        client = compute_v1.ProjectsClient()
        
        project = client.get(project=self.project_id)
        metadata = project.common_instance_metadata
        
        if not metadata.items:
            return
            
        ssh_keys = [item for item in metadata.items if item.key == 'ssh-keys']
        if not ssh_keys:
            return
            
        # Remove expired or invalid SSH keys
        new_keys = []
        for key in ssh_keys[0].value.split('\n'):
            if key and not self._is_key_expired(key):
                new_keys.append(key)
                
        if len(new_keys) != len(ssh_keys[0].value.split('\n')):
            metadata.items = [item for item in metadata.items if item.key != 'ssh-keys']
            if new_keys:
                metadata.items.append({'key': 'ssh-keys', 'value': '\n'.join(new_keys)})
            client.set_common_instance_metadata(project=self.project_id, metadata=metadata)
    
    def _is_key_expired(self, key):
        # Implement your SSH key expiration logic here
        # This is a placeholder - you might want to check key age, validity, etc.
        return False
