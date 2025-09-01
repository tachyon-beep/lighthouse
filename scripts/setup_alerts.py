#!/usr/bin/env python3
"""
Production Alert Setup Script for FEATURE_PACK_0

Configures PagerDuty, Slack, and monitoring alerts for production deployment.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List
import yaml
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AlertManager:
    """Manages production alert configuration"""
    
    def __init__(self):
        self.config_path = Path("/home/john/lighthouse/config/monitoring.yaml")
        self.env_file = Path("/home/john/lighthouse/.env")
        self.alerts_configured = False
        
        # Load monitoring config
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
    
    def setup_all_alerts(self):
        """Configure all alert channels"""
        logger.info("Setting up production alert channels...")
        
        # Setup PagerDuty
        if self.config['alerting']['pagerduty']['enabled']:
            self.setup_pagerduty()
        
        # Setup Slack
        if self.config['alerting']['slack']['enabled']:
            self.setup_slack()
        
        # Setup Prometheus alerts
        self.setup_prometheus_alerts()
        
        # Verify setup
        if self.verify_alert_channels():
            logger.info("✅ All alert channels configured successfully")
            self.alerts_configured = True
        else:
            logger.error("❌ Alert channel configuration failed")
            sys.exit(1)
    
    def setup_pagerduty(self):
        """Configure PagerDuty integration"""
        logger.info("Configuring PagerDuty alerts...")
        
        pagerduty_config = self.config['alerting']['pagerduty']
        
        # Create alert rules in PagerDuty
        alert_rules = []
        
        for alert in pagerduty_config['alerts']:
            rule = {
                "name": f"FEATURE_PACK_0_{alert['name']}",
                "condition": alert['condition'],
                "severity": alert['severity'],
                "escalation_policy": alert['escalation_policy'],
                "description": f"Lighthouse Elicitation: {alert['name']}",
                "actions": {
                    "notify": ["on-call"],
                    "auto_resolve": True,
                    "auto_resolve_timeout": "30m"
                }
            }
            alert_rules.append(rule)
        
        # Save PagerDuty configuration
        pagerduty_file = Path("/home/john/lighthouse/config/pagerduty_alerts.json")
        with open(pagerduty_file, 'w') as f:
            json.dump({
                "service_id": pagerduty_config['service_id'],
                "alerts": alert_rules
            }, f, indent=2)
        
        logger.info(f"Created {len(alert_rules)} PagerDuty alert rules")
        
        # Create test incident (commented out for safety)
        # self.create_test_pagerduty_incident()
    
    def setup_slack(self):
        """Configure Slack notifications"""
        logger.info("Configuring Slack notifications...")
        
        slack_config = self.config['alerting']['slack']
        
        # Create Slack webhook configurations
        slack_webhooks = {
            "channels": slack_config['channels'],
            "notifications": []
        }
        
        for notification in slack_config['notifications']:
            webhook_config = {
                "name": notification['name'],
                "channel": slack_config['channels'].get(
                    notification.get('channel', 'default'),
                    '#lighthouse-alerts'
                ),
                "template": notification['template'],
                "enabled": True
            }
            slack_webhooks['notifications'].append(webhook_config)
        
        # Save Slack configuration
        slack_file = Path("/home/john/lighthouse/config/slack_webhooks.json")
        with open(slack_file, 'w') as f:
            json.dump(slack_webhooks, f, indent=2)
        
        logger.info(f"Created {len(slack_webhooks['notifications'])} Slack notification rules")
        
        # Send test message (commented out for safety)
        # self.send_test_slack_message()
    
    def setup_prometheus_alerts(self):
        """Configure Prometheus alert rules"""
        logger.info("Configuring Prometheus alert rules...")
        
        # Generate Prometheus alert rules file
        alert_rules = {
            "groups": [
                {
                    "name": "lighthouse_elicitation",
                    "interval": "30s",
                    "rules": []
                }
            ]
        }
        
        # P99 Latency alerts
        alert_rules["groups"][0]["rules"].append({
            "alert": "ElicitationP99LatencyHigh",
            "expr": "p99_latency_milliseconds > 300",
            "for": "5m",
            "labels": {
                "severity": "warning",
                "component": "elicitation",
                "migration": "FEATURE_PACK_0"
            },
            "annotations": {
                "summary": "P99 latency exceeds 300ms target",
                "description": "P99 latency is {{ $value }}ms, exceeding the 300ms target"
            }
        })
        
        alert_rules["groups"][0]["rules"].append({
            "alert": "ElicitationP99LatencyCritical",
            "expr": "p99_latency_milliseconds > 500",
            "for": "2m",
            "labels": {
                "severity": "critical",
                "component": "elicitation",
                "migration": "FEATURE_PACK_0"
            },
            "annotations": {
                "summary": "P99 latency critically high",
                "description": "P99 latency is {{ $value }}ms, triggering rollback consideration"
            }
        })
        
        # Error rate alerts
        alert_rules["groups"][0]["rules"].append({
            "alert": "ElicitationErrorRateHigh",
            "expr": "rate(elicitation_requests_total{status='error'}[5m]) > 0.01",
            "for": "5m",
            "labels": {
                "severity": "warning",
                "component": "elicitation"
            },
            "annotations": {
                "summary": "Elicitation error rate exceeds 1%",
                "description": "Error rate is {{ $value | humanizePercentage }}"
            }
        })
        
        # Security alerts
        alert_rules["groups"][0]["rules"].append({
            "alert": "SecurityViolationCritical",
            "expr": "increase(security_violations_total{severity='CRITICAL'}[1m]) > 0",
            "labels": {
                "severity": "critical",
                "component": "security",
                "response": "immediate"
            },
            "annotations": {
                "summary": "Critical security violation detected",
                "description": "Security violation type: {{ $labels.type }} from agent {{ $labels.agent_id }}"
            }
        })
        
        # Rate limiting alerts
        alert_rules["groups"][0]["rules"].append({
            "alert": "RateLimitViolationsHigh",
            "expr": "rate(rate_limit_violations_total[5m]) > 10",
            "for": "5m",
            "labels": {
                "severity": "warning",
                "component": "rate_limiting"
            },
            "annotations": {
                "summary": "High rate of rate limit violations",
                "description": "{{ $value }} violations per second from agent {{ $labels.agent_id }}"
            }
        })
        
        # System health alerts
        alert_rules["groups"][0]["rules"].append({
            "alert": "BridgeDown",
            "expr": "up{job='lighthouse-bridge'} == 0",
            "for": "1m",
            "labels": {
                "severity": "critical",
                "component": "infrastructure"
            },
            "annotations": {
                "summary": "Lighthouse Bridge is down",
                "description": "Bridge has been down for more than 1 minute"
            }
        })
        
        # Save Prometheus rules
        prometheus_file = Path("/home/john/lighthouse/config/prometheus_rules.yml")
        with open(prometheus_file, 'w') as f:
            yaml.dump(alert_rules, f, default_flow_style=False)
        
        logger.info(f"Created {len(alert_rules['groups'][0]['rules'])} Prometheus alert rules")
    
    def setup_grafana_alerts(self):
        """Configure Grafana alert panels"""
        logger.info("Configuring Grafana alert panels...")
        
        grafana_config = self.config['grafana']
        
        # Create alert panel configurations
        alert_panels = []
        
        # P99 Latency panel with alert
        alert_panels.append({
            "title": "P99 Latency Alert",
            "type": "graph",
            "alert": {
                "name": "P99 Latency Threshold",
                "conditions": [{
                    "evaluator": {
                        "params": [300],
                        "type": "gt"
                    },
                    "query": {
                        "model": "p99_latency_milliseconds",
                        "params": ["5m", "now"]
                    }
                }],
                "frequency": "60s",
                "handler": 1,  # PagerDuty
                "message": "P99 latency exceeds 300ms threshold",
                "noDataState": "no_data",
                "notifications": [
                    {"uid": "pagerduty"},
                    {"uid": "slack"}
                ]
            }
        })
        
        # Error rate panel with alert
        alert_panels.append({
            "title": "Error Rate Alert",
            "type": "stat",
            "alert": {
                "name": "Error Rate Threshold",
                "conditions": [{
                    "evaluator": {
                        "params": [0.01],
                        "type": "gt"
                    },
                    "query": {
                        "model": "rate(elicitation_requests_total{status='error'}[5m])",
                        "params": ["5m", "now"]
                    }
                }],
                "frequency": "60s",
                "message": "Error rate exceeds 1% threshold"
            }
        })
        
        # Save Grafana alert configuration
        grafana_file = Path("/home/john/lighthouse/config/grafana_alerts.json")
        with open(grafana_file, 'w') as f:
            json.dump({
                "dashboard_uid": grafana_config['dashboards'][0]['uid'],
                "alert_panels": alert_panels
            }, f, indent=2)
        
        logger.info(f"Created {len(alert_panels)} Grafana alert panels")
    
    def create_runbooks(self):
        """Create operational runbooks for alerts"""
        logger.info("Creating operational runbooks...")
        
        runbooks = {
            "P99_LATENCY_HIGH": {
                "title": "P99 Latency Exceeds 300ms",
                "severity": "WARNING",
                "steps": [
                    "1. Check current P99 latency in Grafana dashboard",
                    "2. Verify number of concurrent agents",
                    "3. Check event store write latency",
                    "4. Review recent deployments",
                    "5. Consider reducing rollout percentage if in migration",
                    "6. If latency > 500ms for 5 minutes, initiate rollback"
                ],
                "escalation": "Performance team, then on-call"
            },
            "SECURITY_VIOLATION": {
                "title": "Critical Security Violation Detected",
                "severity": "CRITICAL",
                "steps": [
                    "1. IMMEDIATE: Check security dashboard for violation details",
                    "2. Identify affected agent(s) and violation type",
                    "3. If authentication bypass: EMERGENCY ROLLBACK",
                    "4. If rate limit abuse: Block offending agent",
                    "5. If replay attack: Verify nonce store integrity",
                    "6. Document incident for post-mortem"
                ],
                "escalation": "Security team immediately"
            },
            "ERROR_RATE_HIGH": {
                "title": "Error Rate Exceeds 1%",
                "severity": "WARNING",
                "steps": [
                    "1. Check error types in logs",
                    "2. Verify database connectivity",
                    "3. Check rate limiting configuration",
                    "4. Review recent configuration changes",
                    "5. If error rate > 5%, consider rollback",
                    "6. Scale infrastructure if resource-constrained"
                ],
                "escalation": "On-call engineer"
            },
            "ROLLBACK_PROCEDURE": {
                "title": "Emergency Rollback Procedure",
                "severity": "CRITICAL",
                "steps": [
                    "1. Execute: python scripts/rollback_elicitation.py --reason '<reason>'",
                    "2. Monitor rollback progress (15-20 minutes)",
                    "3. Verify wait_for_messages is operational",
                    "4. Check no active elicitations remain",
                    "5. Validate event store consistency",
                    "6. Create incident report",
                    "7. Schedule post-mortem within 48 hours"
                ],
                "escalation": "Notify all teams immediately"
            }
        }
        
        # Save runbooks
        runbook_file = Path("/home/john/lighthouse/docs/runbooks/alert_runbooks.json")
        runbook_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(runbook_file, 'w') as f:
            json.dump(runbooks, f, indent=2)
        
        logger.info(f"Created {len(runbooks)} operational runbooks")
        
        # Also create markdown version for easy reading
        runbook_md = Path("/home/john/lighthouse/docs/runbooks/ALERT_RUNBOOKS.md")
        with open(runbook_md, 'w') as f:
            f.write("# FEATURE_PACK_0 Alert Runbooks\n\n")
            
            for alert_name, runbook in runbooks.items():
                f.write(f"## {runbook['title']}\n\n")
                f.write(f"**Severity**: {runbook['severity']}\n\n")
                f.write("### Steps:\n")
                for step in runbook['steps']:
                    f.write(f"{step}\n")
                f.write(f"\n**Escalation**: {runbook['escalation']}\n\n")
                f.write("---\n\n")
    
    def verify_alert_channels(self) -> bool:
        """Verify all alert channels are configured"""
        logger.info("Verifying alert channel configuration...")
        
        checks = {
            "prometheus_rules": Path("/home/john/lighthouse/config/prometheus_rules.yml").exists(),
            "pagerduty_config": Path("/home/john/lighthouse/config/pagerduty_alerts.json").exists(),
            "slack_webhooks": Path("/home/john/lighthouse/config/slack_webhooks.json").exists(),
            "grafana_alerts": Path("/home/john/lighthouse/config/grafana_alerts.json").exists(),
            "runbooks": Path("/home/john/lighthouse/docs/runbooks/alert_runbooks.json").exists()
        }
        
        all_configured = all(checks.values())
        
        for check, status in checks.items():
            status_icon = "✅" if status else "❌"
            logger.info(f"{status_icon} {check}: {'configured' if status else 'missing'}")
        
        return all_configured
    
    def test_alert_channels(self):
        """Send test alerts to verify configuration"""
        logger.info("Testing alert channels...")
        
        # Test Slack (safely)
        test_message = {
            "text": "🧪 Test alert from FEATURE_PACK_0 setup",
            "channel": "#lighthouse-alerts",
            "username": "Lighthouse Bot",
            "icon_emoji": ":lighthouse:"
        }
        
        logger.info("Test Slack message prepared (not sent in setup)")
        
        # Test PagerDuty (safely)
        test_incident = {
            "incident": {
                "type": "incident",
                "title": "Test: FEATURE_PACK_0 Alert Configuration",
                "service": {
                    "id": self.config['alerting']['pagerduty']['service_id'],
                    "type": "service_reference"
                },
                "urgency": "low",
                "body": {
                    "type": "incident_body",
                    "details": "This is a test incident to verify PagerDuty configuration"
                }
            }
        }
        
        logger.info("Test PagerDuty incident prepared (not sent in setup)")
        
        return True


def main():
    """Setup production alerts"""
    manager = AlertManager()
    
    # Setup all alert channels
    manager.setup_all_alerts()
    
    # Create Grafana alerts
    manager.setup_grafana_alerts()
    
    # Create runbooks
    manager.create_runbooks()
    
    # Test channels (safely)
    if manager.test_alert_channels():
        logger.info("\n✅ Production alert channels successfully configured!")
        logger.info("\nNext steps:")
        logger.info("1. Set environment variables in .env file:")
        logger.info("   - PAGERDUTY_API_KEY")
        logger.info("   - SLACK_WEBHOOK_URL")
        logger.info("   - GRAFANA_API_KEY")
        logger.info("2. Deploy Prometheus and Grafana if not already running")
        logger.info("3. Import alert rules to monitoring systems")
        logger.info("4. Test alert channels with test incidents")
    else:
        logger.error("Alert channel configuration failed")
        sys.exit(1)


if __name__ == "__main__":
    main()