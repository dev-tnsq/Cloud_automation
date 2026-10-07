import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import requests

from .models import Alert, Severity

SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.WARNING: 1,
    Severity.INFO: 2,
}


class AlertReporter:
    """
    Reports utilization alerts: logs them, writes a JSON report under reports/
    and optionally posts them to a webhook (e.g. Slack incoming webhook).
    """

    def __init__(self, output_dir: str = "reports", webhook_url: Optional[str] = None):
        self.output_dir = output_dir
        self.webhook_url = webhook_url if webhook_url is not None else os.getenv("ALERT_WEBHOOK_URL")
        self.logger = logging.getLogger(__name__)

    def report(self, alerts: List[Alert], write_file: bool = True) -> dict:
        """
        Report a list of alerts. Returns a summary dict:
        {"total": n, "critical": n, "warning": n, "info": n, "report_file": path|None}
        """
        alerts = sorted(alerts, key=lambda a: SEVERITY_ORDER.get(a.severity, 99))
        summary = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "total": len(alerts),
            "critical": sum(1 for a in alerts if a.severity == Severity.CRITICAL),
            "warning": sum(1 for a in alerts if a.severity == Severity.WARNING),
            "info": sum(1 for a in alerts if a.severity == Severity.INFO),
            "alerts": [a.to_dict() for a in alerts],
            "report_file": None,
        }

        if not alerts:
            self.logger.info("Utilization checks passed: no alerts raised")
            return summary

        # Log everything
        for alert in alerts:
            if alert.severity == Severity.CRITICAL:
                self.logger.error(str(alert))
            elif alert.severity == Severity.WARNING:
                self.logger.warning(str(alert))
            else:
                self.logger.info(str(alert))

        self.logger.info(
            "Utilization alert summary: %s total "
            "(%s critical, %s warning, %s info)",
            summary["total"], summary["critical"], summary["warning"], summary["info"]
        )

        if write_file:
            summary["report_file"] = self._write_report(summary)

        if self.webhook_url:
            self._post_webhook(summary)

        return summary

    def _write_report(self, summary: dict) -> Optional[str]:
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            path = os.path.join(self.output_dir, "utilization_alerts.json")
            with open(path, "w") as fh:
                json.dump(summary, fh, indent=2, default=str)
            self.logger.info(f"Utilization alert report written to {path}")
            return path
        except Exception as e:
            self.logger.error(f"Failed to write alert report: {e}")
            return None

    def _post_webhook(self, summary: dict) -> None:
        try:
            payload = {
                # Generic payload
                "title": "Cloud utilization alerts",
                "summary": {
                    "total": summary["total"],
                    "critical": summary["critical"],
                    "warning": summary["warning"],
                    "info": summary["info"],
                },
                "alerts": summary["alerts"],
                # Slack-compatible payload
                "text": (
                    f":rotating_light: {summary['total']} utilization alert(s): "
                    f"{summary['critical']} critical, {summary['warning']} warning, "
                    f"{summary['info']} info"
                ),
            }
            resp = requests.post(self.webhook_url, json=payload, timeout=15)
            resp.raise_for_status()
            self.logger.info("Alerts posted to webhook")
        except Exception as e:
            self.logger.error(f"Failed to post alerts to webhook: {e}")
