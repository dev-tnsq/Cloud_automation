import os
from dotenv import load_dotenv
import logging
import argparse

try:
    from azu.main import run_cleanup as azure_cleanup
    from gcp.main import GCPCleanupOrchestrator
except ImportError as e:
    logging.error(f"Failed to import cleanup modules: {e}")
    raise

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,  # Change this line to set the logging level to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def run_azure_cleanup():
    subscription_id = os.getenv('AZURE_SUBSCRIPTION_ID')
    resource_group = os.getenv('AZURE_RESOURCE_GROUP')
    
    if not subscription_id:
        raise ValueError("AZURE_SUBSCRIPTION_ID environment variable is required")
    
    logger.info("Starting Azure cleanup...")
    azure_cleanup(subscription_id, resource_group)
    logger.info("Azure cleanup completed")

def run_gcp_cleanup(cleanup_types, hours, disk_hours):
    project_id = os.getenv('GCP_PROJECT_ID')
    service_account_key_path = os.getenv('GCP_SERVICE_ACCOUNT_KEY_PATH')
    
    if not project_id:
        raise ValueError("GCP_PROJECT_ID environment variable is required")
    
    logger.info("Starting GCP cleanup...")
    orchestrator = GCPCleanupOrchestrator(
        project_id=project_id,
        service_account_key_path=service_account_key_path,
        hours=hours,
        disk_hours=disk_hours
    )
    
    success = orchestrator.run_all_cleanups(cleanup_types=cleanup_types)
    
    if success:
        logger.info("GCP cleanup completed successfully")
    else:
        logger.warning("GCP cleanup completed with some errors")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Cloud cleanup script")
    parser.add_argument('--cloud-providers', type=str, help="Comma-separated list of cloud providers (e.g., azure,gcp)")
    parser.add_argument('--cleanup-types', type=str, help="Comma-separated list of cleanup types (e.g., vm,disk)")
    parser.add_argument('--hours', type=int, default=4, help="Hours threshold for VM, IP, NIC, NEG cleanup")
    parser.add_argument('--disk-hours', type=int, default=4, help="Hours threshold for Disk cleanup")
    return parser.parse_args()

def main():
    # Load environment variables
    load_dotenv()
    
    args = parse_arguments()
    cloud_providers = args.cloud_providers.split(',') if args.cloud_providers else None
    cleanup_types = args.cleanup_types.split(',') if args.cleanup_types else None
    hours = args.hours
    disk_hours = args.disk_hours
    
    logger.info("Starting the cleanup script...")
    logger.info(f"Cloud providers: {cloud_providers}, Cleanup types: {cleanup_types}, Hours: {hours}, Disk hours: {disk_hours}")
    
    try:
        if cloud_providers is None or 'azure' in cloud_providers:
            logger.debug("Running Azure cleanup")
            run_azure_cleanup()
            
        if cloud_providers is None or 'gcp' in cloud_providers:
            logger.debug("Running GCP cleanup")
            run_gcp_cleanup(cleanup_types, hours, disk_hours)
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise

if __name__ == "__main__":
    main()
