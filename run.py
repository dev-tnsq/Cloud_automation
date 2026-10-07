import os
from dotenv import load_dotenv
import logging
import argparse
import json

try:
    from azu.main import AzureCleanupOrchestrator
    from gcp.main import GCPCleanupOrchestrator
    from alerts.report import AlertReporter
except ImportError as e:
    logging.error(f"Failed to import cleanup modules: {e}")
    raise

# Setup logging
logging.basicConfig(
    level=logging.INFO,  # Change this line to set the logging level to INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def load_azure_credentials(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
        # Parse all required information from the JSON file
        subscription_id = data['id'].split('/')[2]
        resource_group = data['id'].split('/')[4]
        return {
            'subscription_id': subscription_id,
            'resource_group': resource_group,
            'managed_identity_client_id': data['properties']['clientId'],
            'tenant_id': data['properties']['tenantId'],
            'principal_id': data['properties']['principalId'],
            'location': data['location']
        }

def load_gcp_credentials(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def run_azure_cleanup(cleanup_types, hours, disk_hours, azure_credentials):
    subscription_id = azure_credentials['subscription_id']
    resource_group = azure_credentials['resource_group']
    managed_identity_client_id = azure_credentials['managed_identity_client_id']

    if not subscription_id:
        raise ValueError("AZURE_SUBSCRIPTION_ID is required in the credentials file")
    
    logger.info("Starting Azure cleanup...")
    orchestrator = AzureCleanupOrchestrator(
        subscription_id=subscription_id,
        resource_group=resource_group,
        managed_identity_client_id=managed_identity_client_id,
        hours=hours,
        disk_hours=disk_hours
    )
    
    success = orchestrator.run_all_cleanups(cleanup_types=cleanup_types)
    
    if success:
        logger.info("Azure cleanup completed successfully")
    else:
        logger.warning("Azure cleanup completed with some errors")

def run_gcp_cleanup(cleanup_types, hours, disk_hours):
    gcp_credentials = load_gcp_credentials(os.getenv('GCP_CREDENTIALS_FILE_PATH'))
    project_id = gcp_credentials['project_id']
    service_account_key_path = gcp_credentials['service_account_key_path']
    
    if not project_id:
        raise ValueError("GCP_PROJECT_ID is required in the credentials file")
    
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

def run_azure_alerts(cpu_threshold, disk_threshold, lookback_hours, azure_credentials):
    subscription_id = azure_credentials['subscription_id']
    resource_group = azure_credentials['resource_group']
    managed_identity_client_id = azure_credentials['managed_identity_client_id']

    if not subscription_id:
        raise ValueError("AZURE_SUBSCRIPTION_ID is required in the credentials file")

    logger.info("Starting Azure utilization checks...")
    orchestrator = AzureCleanupOrchestrator(
        subscription_id=subscription_id,
        resource_group=resource_group,
        managed_identity_client_id=managed_identity_client_id,
    )
    return orchestrator.run_utilization_checks(
        cpu_threshold=cpu_threshold,
        disk_threshold=disk_threshold,
        lookback_hours=lookback_hours
    )

def run_gcp_alerts(cpu_threshold, disk_threshold, lookback_hours):
    gcp_credentials = load_gcp_credentials(os.getenv('GCP_CREDENTIALS_FILE_PATH'))
    project_id = gcp_credentials['project_id']
    service_account_key_path = gcp_credentials['service_account_key_path']

    if not project_id:
        raise ValueError("GCP_PROJECT_ID is required in the credentials file")

    logger.info("Starting GCP utilization checks...")
    orchestrator = GCPCleanupOrchestrator(
        project_id=project_id,
        service_account_key_path=service_account_key_path,
    )
    return orchestrator.run_utilization_checks(
        cpu_threshold=cpu_threshold,
        disk_threshold=disk_threshold,
        lookback_hours=lookback_hours
    )

def parse_arguments():
    parser = argparse.ArgumentParser(description="Cloud cleanup script")
    parser.add_argument('--cloud-providers', type=str, help="Comma-separated list of cloud providers (e.g., azure,gcp)")
    parser.add_argument('--cleanup-types', type=str, help="Comma-separated list of cleanup types (e.g., vm,disk)")
    parser.add_argument('--mode', type=str, default='cleanup', choices=['cleanup', 'alerts', 'all'],
                        help="cleanup: resource cleanup only; alerts: utilization checks only; all: both")
    parser.add_argument('--hours', type=int, default=4, help="Hours threshold for VM, IP, NIC, NEG cleanup")
    parser.add_argument('--disk-hours', type=int, default=4, help="Hours threshold for Disk cleanup")
    parser.add_argument('--cpu-threshold', type=float,
                        default=float(os.getenv('CPU_THRESHOLD', '10')),
                        help="Alert when average CPU utilization is below this %% (default: 10)")
    parser.add_argument('--disk-threshold', type=float,
                        default=float(os.getenv('DISK_THRESHOLD', '90')),
                        help="Alert when disk usage is above this %% (default: 90)")
    parser.add_argument('--lookback-hours', type=int,
                        default=int(os.getenv('ALERT_LOOKBACK_HOURS', '24')),
                        help="Metric lookback window in hours for utilization alerts (default: 24)")
    return parser.parse_args()

def main():
    # Load environment variables
    load_dotenv()
    
    args = parse_arguments()
    cloud_providers = args.cloud_providers.split(',') if args.cloud_providers else None
    cleanup_types = args.cleanup_types.split(',') if args.cleanup_types else None
    hours = args.hours
    disk_hours = args.disk_hours
    run_cleanup = args.mode in ('cleanup', 'all')
    run_alerts = args.mode in ('alerts', 'all')
    
    logger.info("Starting the cleanup script...")
    logger.info(
        f"Cloud providers: {cloud_providers}, Mode: {args.mode}, "
        f"Cleanup types: {cleanup_types}, Hours: {hours}, Disk hours: {disk_hours}"
    )
    if run_alerts:
        logger.info(
            f"Utilization thresholds: CPU < {args.cpu_threshold}%, "
            f"Disk > {args.disk_threshold}%, Lookback: {args.lookback_hours}h"
        )

    alerts = []
    try:
        if cloud_providers is None or 'azure' in cloud_providers:
            azure_credentials = load_azure_credentials('./test.json')
            if run_cleanup:
                logger.info("Running Azure cleanup")
                run_azure_cleanup(cleanup_types, hours, disk_hours, azure_credentials)
            if run_alerts:
                logger.info("Running Azure utilization checks")
                alerts.extend(run_azure_alerts(
                    args.cpu_threshold, args.disk_threshold, args.lookback_hours, azure_credentials
                ))

        if cloud_providers is None or 'gcp' in cloud_providers:
            if run_cleanup:
                logger.info("Running GCP cleanup")
                run_gcp_cleanup(cleanup_types, hours, disk_hours)
            if run_alerts:
                logger.info("Running GCP utilization checks")
                alerts.extend(run_gcp_alerts(
                    args.cpu_threshold, args.disk_threshold, args.lookback_hours
                ))

        if run_alerts:
            reporter = AlertReporter()
            reporter.report(alerts)
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise

if __name__ == "__main__":
    main()
