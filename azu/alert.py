import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from azure.mgmt.compute import ComputeManagementClient

from alerts.models import Alert, Severity

# Platform metric available on every VM without any agent.
CPU_METRIC = "Percentage CPU"

# Guest OS disk-space metrics (collected by the Azure Monitor Agent / diagnostics).
# Tried in order; the first metric that returns data for a VM is used.
USED_SPACE_METRICS = [
    "% Used Space",
    "Percentage Used Space",
    "Percent Used Space",
    "Used Space Percentage",
]
FREE_SPACE_METRICS = [
    "% Free Space",
    "Percentage Free Space",
    "Free Space Percentage",
    "LogicalDisk(_Total)% Free Space",
]


class UtilizationAlert:
    """
    Utilization-based alert checks for Azure resources.

    Checks:
      - cpu_low:             average VM CPU utilization below threshold (over-provisioned / idle VM)
      - disk_space_high:     disk usage above threshold (needs guest OS metrics via Azure Monitor Agent)
      - volume_unallocated:  disk/volume provisioned but not attached to any VM
      - volume_misallocated: volume attached to a stopped/deallocated VM
    """

    def __init__(self, subscription_id, resource_group=None, credentials=None,
                 cpu_threshold=10.0, disk_threshold=90.0, lookback_hours=24):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.credentials = credentials
        self.cpu_threshold = float(cpu_threshold)
        self.disk_threshold = float(disk_threshold)
        self.lookback_hours = int(lookback_hours)

        self.client = ComputeManagementClient(self.credentials, self.subscription_id)
        self._metrics_client = None
        self._disk_metric_name = None  # first guest disk metric name that worked
        self._vm_status_cache: Dict[str, Optional[str]] = {}
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def check(self) -> List[Alert]:
        start = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)
        end = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        self.logger.info(
            f"Starting utilization checks (lookback: {self.lookback_hours}h, "
            f"cpu < {self.cpu_threshold}%, disk > {self.disk_threshold}%)"
        )

        try:
            vms = list(
                self.client.virtual_machines.list_by_resource_group(self.resource_group)
                if self.resource_group
                else self.client.virtual_machines.list_all()
            )
        except Exception as e:
            self.logger.error(f"Failed to list VMs: {e}")
            return alerts

        self.logger.info(f"Checking {len(vms)} VM(s) for utilization alerts")
        no_guest_metrics: List[str] = []

        for vm in vms:
            try:
                alert = self._check_cpu(vm, start, end)
                if alert:
                    alerts.append(alert)

                if not self._check_disk_space(vm, start, end, alerts):
                    no_guest_metrics.append(vm.name)
            except Exception as e:
                self.logger.error(f"Error checking VM {vm.name}: {e}")

        if no_guest_metrics:
            self.logger.info(
                f"Guest disk metrics unavailable for {len(no_guest_metrics)} VM(s) "
                f"(install the Azure Monitor Agent to enable disk space alerts): "
                f"{', '.join(no_guest_metrics)}"
            )

        try:
            self._check_volumes(alerts)
        except Exception as e:
            self.logger.error(f"Error checking volumes/disks: {e}")

        self.logger.info(f"Utilization checks finished: {len(alerts)} alert(s) raised")
        return alerts

    # ------------------------------------------------------------------ #
    # Checks
    # ------------------------------------------------------------------ #
    def _check_cpu(self, vm, start, end) -> Optional[Alert]:
        """Alert when average CPU utilization is below the threshold."""
        avg_cpu = self._average_metric(vm.id, CPU_METRIC, start, end)
        if avg_cpu is None:
            # No data usually means the VM is stopped/deallocated — skip quietly.
            return None

        if avg_cpu >= self.cpu_threshold:
            return None

        # Near-zero CPU is a stronger signal than merely below threshold.
        severity = Severity.CRITICAL if avg_cpu < 1.0 else Severity.WARNING
        return Alert(
            cloud="azure",
            check="cpu_low",
            severity=severity,
            resource_type="vm",
            resource_name=vm.name,
            resource_id=vm.id,
            message=(
                f"VM average CPU is {avg_cpu:.2f}% over the last {self.lookback_hours}h "
                f"(threshold {self.cpu_threshold}%) — likely over-provisioned or idle, "
                f"consider right-sizing or deallocating"
            ),
            metric=CPU_METRIC,
            value=round(avg_cpu, 2),
            threshold=self.cpu_threshold,
            region=getattr(vm, "location", None),
        )

    def _check_disk_space(self, vm, start, end, alerts: List[Alert]) -> bool:
        """
        Alert when disk usage is above the threshold.

        Returns True if a disk metric was found/evaluated for this VM,
        False when no guest OS disk metric is available.
        """
        used_pct, metric_name = self._disk_used_percent(vm.id, start, end)
        if used_pct is None:
            return False

        if used_pct < self.disk_threshold:
            return True

        severity = Severity.CRITICAL if used_pct >= self.disk_threshold + 5 else Severity.WARNING
        alerts.append(Alert(
            cloud="azure",
            check="disk_space_high",
            severity=severity,
            resource_type="vm",
            resource_name=vm.name,
            resource_id=vm.id,
            message=(
                f"Disk usage is {used_pct:.1f}% over the last {self.lookback_hours}h "
                f"(threshold {self.disk_threshold}%) — risk of running out of space"
            ),
            metric=metric_name,
            value=round(used_pct, 2),
            threshold=self.disk_threshold,
            region=getattr(vm, "location", None),
        ))
        return True

    def _check_volumes(self, alerts: List[Alert]) -> None:
        """Alert on volumes/disks that are allocated but not properly in use."""
        disks = list(
            self.client.disks.list_by_resource_group(self.resource_group)
            if self.resource_group
            else self.client.disks.list()
        )
        self.logger.info(f"Checking {len(disks)} disk/volume(s) for allocation issues")

        for disk in disks:
            try:
                size_gb = getattr(disk, "disk_size_gb", None)
                location = getattr(disk, "location", None)

                if not disk.managed_by:
                    alerts.append(Alert(
                        cloud="azure",
                        check="volume_unallocated",
                        severity=Severity.WARNING,
                        resource_type="disk",
                        resource_name=disk.name,
                        resource_id=disk.id,
                        message=(
                            f"Volume ({size_gb} GB) is provisioned but not attached to any VM — "
                            f"it is not properly allocated and is costing money without being used"
                        ),
                        threshold=None,
                        region=location,
                        extra={"disk_size_gb": size_gb},
                    ))
                    continue

                status = self._vm_power_state(disk.managed_by)
                if status and status.lower() in ("deallocated", "stopped"):
                    vm_name = disk.managed_by.split("/")[-1]
                    alerts.append(Alert(
                        cloud="azure",
                        check="volume_misallocated",
                        severity=Severity.WARNING,
                        resource_type="disk",
                        resource_name=disk.name,
                        resource_id=disk.id,
                        message=(
                            f"Volume ({size_gb} GB) is attached to VM '{vm_name}' which is "
                            f"{status} — the volume is allocated but not being used"
                        ),
                        threshold=None,
                        region=location,
                        extra={"disk_size_gb": size_gb, "attached_vm": vm_name, "vm_state": status},
                    ))
            except Exception as e:
                self.logger.error(f"Error checking disk {disk.name}: {e}")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get_metrics_client(self):
        if self._metrics_client is None:
            from azure.monitor.query import MetricsClient
            self._metrics_client = MetricsClient(self.credentials, self.subscription_id)
        return self._metrics_client

    def _average_metric(self, resource_uri: str, metric_name: str, start, end) -> Optional[float]:
        """Return the average of a metric across all time series, or None if no data."""
        try:
            response = self._get_metrics_client().query_resource(
                resource_uri,
                metric_names=[metric_name],
                timespan=(start, end),
                interval=timedelta(hours=1),
                aggregation="Average",
            )
        except Exception as e:
            self.logger.debug(f"Metric query failed for {metric_name} on {resource_uri}: {e}")
            return None

        values = []
        for metric in getattr(response, "value", []) or []:
            for series in metric.timeseries or []:
                for point in series.data or []:
                    if point.average is not None:
                        values.append(point.average)

        if not values:
            return None
        return sum(values) / len(values)

    def _disk_used_percent(self, vm_id: str, start, end) -> tuple:
        """
        Best-effort disk usage percentage for a VM.

        Returns (used_percent, metric_name) or (None, None) when no guest
        OS disk metric is available (Azure Monitor Agent not installed).
        """
        candidates = []
        if self._disk_metric_name:
            candidates.append(self._disk_metric_name)
        candidates += [m for m in USED_SPACE_METRICS + FREE_SPACE_METRICS if m not in candidates]

        for metric_name in candidates:
            avg = self._average_metric(vm_id, metric_name, start, end)
            if avg is None:
                continue

            is_free_metric = metric_name in FREE_SPACE_METRICS
            used = 100.0 - avg if is_free_metric else avg

            if not self._disk_metric_name:
                self._disk_metric_name = metric_name
                self.logger.info(f"Using guest disk metric '{metric_name}' for disk space alerts")
            return used, metric_name

        return None, None

    def _vm_power_state(self, vm_resource_id: str) -> Optional[str]:
        """Power state of a VM given its resource id (cached)."""
        if vm_resource_id in self._vm_status_cache:
            return self._vm_status_cache[vm_resource_id]

        status = None
        try:
            parts = vm_resource_id.split("/")
            resource_group = parts[4]
            vm_name = parts[-1]
            view = self.client.virtual_machines.instance_view(resource_group, vm_name)
            for s in view.statuses or []:
                if s.code.startswith("PowerState/"):
                    status = s.code.split("/")[-1]
                    break
        except Exception as e:
            self.logger.debug(f"Could not get power state for {vm_resource_id}: {e}")

        self._vm_status_cache[vm_resource_id] = status
        return status
