class GCPResourceCleanup:
    def __init__(self, project_id, zone=None):
        self.project_id = project_id
        self.zone = zone

    def cleanup(self):
        raise NotImplementedError("Cleanup method must be implemented by subclasses")

    def log_deletion(self, resource_type, resource_name):
        print(f"Deleting {resource_type}: {resource_name}")
