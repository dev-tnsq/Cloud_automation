import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from google.cloud import compute_v1

from alerts.models import Alert, Severity

CPU_METRIC = 'metric.type="compute.googleapis.com/instance/cpu/utilization" AND resource.type="gce_instance"'
# Guest OS metric — requires the Ops Agent (or legacy monitoring agent) on the instance.
DISK_USED_METRIC = 'metric.type="agent.googleapis.com/disk/percent_used" AND resource.type="gce_instance"'


class UtilizationAlert:
    """
    Utilization-based alert checks for GCP resources.

    Checks:
      - cpu_low:             average instance CPU utilization below threshold (over-provisioned / idle VM)
      - disk_space_high:     disk usage above threshold (needs Ops Agent metrics)
      - volume_unallocated:  disk provisioned but not attached to any instance
      - volume_misallocated: volume attached to a stopped (TERMINATED) instance
    """

    def __init__(self, project_id, credentials=None,
                 cpu_threshold=10.0, disk_threshold=90.0, lookback_hours=24):
        self.project_id = project_id
        self.credentials = credentials
        self.cpu_threshold = float(cpu_threshold) / 100.0  # GCP reports utilization as a fraction
        self.disk_threshold = float(disk_threshold)
        self.lookback_hours = int(lookback_hours)

        self._monitoring_client = None
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def check(self) -> List[Alert]:
        self.logger.info(
            f"Starting utilization checks (lookback: {self.lookback_hours}h, "
            f"cpu < {self.cpu_threshold * 100:.1f}%, disk > {self.disk_threshold}%)"
        )

        instances = self._list_instances()  # instance_id -> {name, zone, status}
        by_name = {info["name"]: info for info in instances.values()}
        alerts: List[Alert] = []

        alerts.extend(self._check_cpu(instances))
        alerts.extend(self._check_disk_space(instances))
        alerts.extend(self._check_volumes(instances, by_name))

        self.logger.info(f"Utilization checks finished: {len(alerts)} alert(s) raised")
        return alerts

    # ------------------------------------------------------------------ #
    # Checks
    # ------------------------------------------------------------------ #
    def _check_cpu(self, instances: Dict[str, dict]) -> List[Alert]:
        """Alert when average CPU utilization of an instance is below the threshold."""
        alerts: List[Alert] = []
        series_by_instance = self._group_by_instance(CPU_METRIC)

        for instance_id, points in series_by_instance.items():
            if not points:
                continue
            avg_cpu = sum(points) / len(points)
            if avg_cpu >= self.cpu_threshold:
                continue

            info = instances.get(instance_id, {})
            severity = Severity.CRITICAL if avg_cpu < 0.01 else Severity.WARNING  # < 1% CPU
            pct = avg_cpu * 100
            alerts.append(Alert(
                cloud="gcp",
                check="cpu_low",
                severity=severity,
                resource_type="instance",
                resource_name=info.get("name", instance_id),
                resource_id=f"projects/{self.project_id}/zones/{info.get('zone', '?')}/instances/{info.get('name', instance_id)}",
                message=(
                    f"Instance average CPU is {pct:.2f}% over the last {self.lookback_hours}h "
                    f"(threshold {self.cpu_threshold * 100:.1f}%) — likely over-provisioned or idle, "
                    f"consider right-sizing or stopping it"
                ),
                metric="compute.googleapis.com/instance/cpu/utilization",
                value=round(pct, 2),
                threshold=round(self.cpu_threshold * 100, 2),
                region=info.get("zone"),
                extra={"status": info.get("status")},
            ))

        checked = len(series_by_instance)
        if checked < len(instances):
            self.logger.info(
                f"CPU metrics available for {checked}/{len(instances)} instance(s) "
                f"(stopped instances emit no CPU metrics)"
            )
        return alerts

    def _check_disk_space(self, instances: Dict[str, dict]) -> List[Alert]:
        """
        Alert when disk usage of a filesystem is above the threshold.

        Uses the Ops Agent metric agent.googleapis.com/disk/percent_used;
        instances without the agent are skipped with an info log.
        """
        alerts: List[Alert] = []

        # (instance_id, device) -> list of values
        grouped: Dict[Tuple[str, str], List[float]] = {}
        for ts in self._list_time_series(DISK_USED_METRIC):
            instance_id = ts.resource.labels.get("instance_id", "")
            # If the metric carries a state label, only "used" is meaningful.
            state = ts.metric.labels.get("state")
            if state and state != "used":
                continue
            device = ts.metric.labels.get("device", "?")
            values = [p.value.double_value for p in ts.points if p.value.double_value is not None]
            grouped.setdefault((instance_id, device), []).extend(values)

        if not grouped:
            self.logger.info(
                "No guest disk metrics found — install the Ops Agent on your instances "
                "to enable disk space alerts"
            )
            return alerts

        # One alert per instance, using its worst (most used) filesystem.
        worst: Dict[str, Tuple[float, str]] = {}
        for (instance_id, device), values in grouped.items():
            if not values:
                continue
            avg = sum(values) / len(values)
            if instance_id not in worst or avg > worst[instance_id][0]:
                worst[instance_id] = (avg, device)

        for instance_id, (used_pct, device) in worst.items():
            if used_pct < self.disk_threshold:
                continue

            info = instances.get(instance_id, {})
            severity = Severity.CRITICAL if used_pct >= self.disk_threshold + 5 else Severity.WARNING
            alerts.append(Alert(
                cloud="gcp",
                check="disk_space_high",
                severity=severity,
                resource_type="instance",
                resource_name=info.get("name", instance_id),
                resource_id=f"projects/{self.project_id}/zones/{info.get('zone', '?')}/instances/{info.get('name', instance_id)}",
                message=(
                    f"Disk usage on device '{device}' is {used_pct:.1f}% over the last "
                    f"{self.lookback_hours}h (threshold {self.disk_threshold}%) — "
                    f"risk of running out of space"
                ),
                metric="agent.googleapis.com/disk/percent_used",
                value=round(used_pct, 2),
                threshold=self.disk_threshold,
                region=info.get("zone"),
                extra={"device": device},
            ))

        return alerts

    def _check_volumes(self, instances: Dict[str, dict], by_name: Dict[str, dict]) -> List[Alert]:
        """Alert on volumes/disks that are allocated but not properly in use."""
        alerts: List[Alert] = []

        for zone in self._get_zones():
            try:
                client = compute_v1.DisksClient()
                request = compute_v1.ListDisksRequest(project=self.project_id, zone=zone)
                disks = list(client.list(request=request))
            except Exception as e:
                self.logger.error(f"Error listing disks in zone {zone}: {e}")
                continue

            for disk in disks:
                try:
                    size_gb = getattr(disk, "size_gb", None)

                    if not disk.users:
                        alerts.append(Alert(
                            cloud="gcp",
                            check="volume_unallocated",
                            severity=Severity.WARNING,
                            resource_type="disk",
                            resource_name=disk.name,
                            resource_id=f"projects/{self.project_id}/zones/{zone}/disks/{disk.name}",
                            message=(
                                f"Volume ({size_gb} GB) is provisioned but not attached to any "
                                f"instance — it is not properly allocated and is costing money "
                                f"without being used"
                            ),
                            region=zone,
                            extra={"disk_size_gb": size_gb},
                        ))
                        continue

                    # Volume attached to a stopped instance?
                    attached_instance = disk.users[0].split("/")[-1]
                    info = by_name.get(attached_instance)
                    if info and info.get("status") == "TERMINATED":
                        alerts.append(Alert(
                            cloud="gcp",
                            check="volume_misallocated",
                            severity=Severity.WARNING,
                            resource_type="disk",
                            resource_name=disk.name,
                            resource_id=f"projects/{self.project_id}/zones/{zone}/disks/{disk.name}",
                            message=(
                                f"Volume ({size_gb} GB) is attached to instance "
                                f"'{attached_instance}' which is STOPPED — the volume is "
                                f"allocated but not being used"
                            ),
                            region=zone,
                            extra={
                                "disk_size_gb": size_gb,
                                "attached_instance": attached_instance,
                                "instance_status": info.get("status"),
                            },
                        ))
                except Exception as e:
                    self.logger.error(f"Error checking disk {disk.name} in {zone}: {e}")

        return alerts

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get_monitoring_client(self):
        if self._monitoring_client is None:
            from google.cloud import monitoring_v3
            if self.credentials:
                self._monitoring_client = monitoring_v3.MetricServiceClient(credentials=self.credentials)
            else:
                self._monitoring_client = monitoring_v3.MetricServiceClient()
        return self._monitoring_client

    def _list_time_series(self, metric_filter: str) -> List:
        from google.cloud import monitoring_v3

        now = datetime.now(timezone.utc)
        interval = monitoring_v3.TimeInterval({
            "end_time": {"seconds": int(now.timestamp())},
            "start_time": {"seconds": int((now - timedelta(hours=self.lookback_hours)).timestamp())},
        })
        request = {
            "name": f"projects/{self.project_id}",
            "filter": metric_filter,
            "interval": interval,
            "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        }
        try:
            return list(self._get_monitoring_client().list_time_series(request=request))
        except Exception as e:
            self.logger.error(f"Failed to query Cloud Monitoring ({metric_filter}): {e}")
            return []

    def _group_by_instance(self, metric_filter: str) -> Dict[str, List[float]]:
        """Group time series points by instance_id."""
        grouped: Dict[str, List[float]] = {}
        for ts in self._list_time_series(metric_filter):
            instance_id = ts.resource.labels.get("instance_id", "")
            values = [p.value.double_value for p in ts.points if p.value.double_value is not None]
            if instance_id and values:
                grouped.setdefault(instance_id, []).extend(values)
        return grouped

    def _get_zones(self) -> List[str]:
        client = compute_v1.ZonesClient(credentials=self.credentials) if self.credentials else compute_v1.ZonesClient()
        return [zone.name for zone in client.list(project=self.project_id)]

    def _list_instances(self) -> Dict[str, dict]:
        """Map instance id -> {name, zone, status} across all zones."""
        client = compute_v1.InstancesClient(credentials=self.credentials) if self.credentials else compute_v1.InstancesClient()
        instances: Dict[str, dict] = {}
        for zone in self._get_zones():
            try:
                for instance in client.list(project=self.project_id, zone=zone):
                    instances[str(instance.id)] = {
                        "name": instance.name,
                        "zone": zone,
                        "status": instance.status,
                    }
            except Exception as e:
                self.logger.error(f"Error listing instances in zone {zone}: {e}")
        return instances
