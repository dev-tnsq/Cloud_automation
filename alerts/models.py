from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Alert:
    """A single utilization alert raised for a cloud resource."""
    cloud: str                      # azure / gcp
    check: str                      # cpu_low / disk_high / volume_unallocated / volume_misallocated
    severity: Severity
    resource_type: str              # vm / disk / volume / instance
    resource_name: str
    resource_id: str
    message: str
    metric: Optional[str] = None    # e.g. Percentage CPU
    value: Optional[float] = None   # observed value
    threshold: Optional[float] = None
    region: Optional[str] = None    # location / zone
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data

    def __str__(self) -> str:
        metric_part = ""
        if self.metric is not None and self.value is not None and self.threshold is not None:
            metric_part = f" [{self.metric}: {self.value:.2f} vs threshold {self.threshold:.2f}]"
        return (
            f"[{self.severity.value}] {self.cloud}/{self.resource_type} "
            f"'{self.resource_name}' ({self.check}){metric_part} - {self.message}"
        )
