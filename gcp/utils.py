from datetime import datetime

def is_resource_old_enough(creation_timestamp, hours=4):
    """Check if resource is older than specified hours."""
    creation_time = datetime.fromisoformat(creation_timestamp.replace('Z', '+00:00'))
    age = datetime.now(creation_time.tzinfo) - creation_time
    return age.total_seconds() > hours * 3600
