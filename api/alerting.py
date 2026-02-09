"""
Alerting System
Sends alerts when anomalies are detected
"""

import requests
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertManager:
    """Manages alerts for detected anomalies"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.slack_webhook = self.config.get('slack_webhook_url', '')
        self.smtp_server = self.config.get('smtp_server', 'smtp.gmail.com')
        self.smtp_port = self.config.get('smtp_port', 587)
        self.smtp_user = self.config.get('smtp_user', '')
        self.smtp_password = self.config.get('smtp_password', '')
        self.alert_email = self.config.get('alert_email', '')
    
    def format_anomaly_message(self, anomaly: Dict) -> str:
        """Format anomaly data into readable message"""
        job_name = anomaly.get('data', {}).get('job_name') or anomaly.get('data', {}).get('workflow_name', 'Unknown')
        
        message = f"🚨 *Anomaly Detected in CI/CD Pipeline*\n\n"
        message += f"*Job/Workflow:* {job_name}\n"
        message += f"*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        message += f"*Severity:* {'HIGH' if anomaly.get('max_z_score', 0) > 4 else 'MEDIUM'}\n\n"
        
        if 'anomaly_features' in anomaly:
            message += "*Anomalous Metrics:*\n"
            for feature in anomaly['anomaly_features'][:3]:  # Top 3
                message += f"  • {feature['feature']}: {feature['value']:.2f} "
                message += f"(expected: {feature['expected']:.2f}, "
                message += f"z-score: {feature['z_score']:.2f})\n"
        
        # Add build details
        data = anomaly.get('data', {})
        if 'duration' in data:
            message += f"\n*Build Duration:* {data['duration']:.1f}s\n"
        if 'result' in data:
            message += f"*Result:* {data['result']}\n"
        if 'failure_count' in data:
            message += f"*Failures:* {data['failure_count']}\n"
        
        return message
    
    def send_slack_alert(self, anomaly: Dict) -> bool:
        """Send alert to Slack"""
        if not self.slack_webhook:
            logger.warning("Slack webhook URL not configured")
            return False
        
        try:
            message = self.format_anomaly_message(anomaly)
            
            payload = {
                'text': message,
                'username': 'CI/CD Anomaly Detector',
                'icon_emoji': ':robot_face:'
            }
            
            response = requests.post(
                self.slack_webhook,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Slack alert sent successfully")
                return True
            else:
                logger.error(f"Slack alert failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack alert: {e}")
            return False
    
    def send_email_alert(self, anomaly: Dict) -> bool:
        """Send alert via email"""
        if not all([self.smtp_user, self.smtp_password, self.alert_email]):
            logger.warning("Email configuration incomplete")
            return False
        
        try:
            job_name = anomaly.get('data', {}).get('job_name') or anomaly.get('data', {}).get('workflow_name', 'Unknown')
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"CI/CD Anomaly Alert - {job_name}"
            msg['From'] = self.smtp_user
            msg['To'] = self.alert_email
            
            # Plain text version
            text = self.format_anomaly_message(anomaly)
            
            # HTML version
            html = f"""
            <html>
              <body>
                <h2 style="color: #e74c3c;">🚨 Anomaly Detected in CI/CD Pipeline</h2>
                <p><strong>Job/Workflow:</strong> {job_name}</p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <h3>Anomalous Metrics:</h3>
                <ul>
            """
            
            if 'anomaly_features' in anomaly:
                for feature in anomaly['anomaly_features'][:5]:
                    html += f"""
                    <li>
                        <strong>{feature['feature']}:</strong> {feature['value']:.2f}
                        (expected: {feature['expected']:.2f}, z-score: {feature['z_score']:.2f})
                    </li>
                    """
            
            html += """
                </ul>
                <p style="color: #7f8c8d; font-size: 12px;">
                    This is an automated alert from the CI/CD Anomaly Detection System
                </p>
              </body>
            </html>
            """
            
            part1 = MIMEText(text, 'plain')
            part2 = MIMEText(html, 'html')
            
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email alert sent to {self.alert_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
            return False
    
    def send_webhook_alert(self, anomaly: Dict, webhook_url: str) -> bool:
        """Send alert to custom webhook"""
        if not webhook_url:
            return False
        
        try:
            payload = {
                'type': 'anomaly_detected',
                'timestamp': datetime.now().isoformat(),
                'anomaly': anomaly
            }
            
            response = requests.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Webhook alert sent to {webhook_url}")
                return True
            else:
                logger.error(f"Webhook alert failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")
            return False
    
    def send_alert(self, anomaly: Dict, channels: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Send alert through multiple channels
        
        Args:
            anomaly: Anomaly data
            channels: List of channels to use ['slack', 'email', 'webhook']
        
        Returns:
            Dictionary of channel: success status
        """
        if channels is None:
            channels = ['slack', 'email']
        
        results = {}
        
        if 'slack' in channels:
            results['slack'] = self.send_slack_alert(anomaly)
        
        if 'email' in channels:
            results['email'] = self.send_email_alert(anomaly)
        
        if 'webhook' in channels and self.config.get('webhook_url'):
            results['webhook'] = self.send_webhook_alert(
                anomaly,
                self.config['webhook_url']
            )
        
        return results
    
    def send_batch_alert(self, anomalies: List[Dict], max_items: int = 10) -> bool:
        """Send summary alert for multiple anomalies"""
        if not anomalies:
            return False
        
        count = len(anomalies)
        message = f"🚨 *{count} Anomalies Detected in CI/CD Pipelines*\n\n"
        
        for i, anomaly in enumerate(anomalies[:max_items], 1):
            job_name = anomaly.get('data', {}).get('job_name') or anomaly.get('data', {}).get('workflow_name', 'Unknown')
            message += f"{i}. *{job_name}* - "
            
            if 'max_z_score' in anomaly:
                message += f"z-score: {anomaly['max_z_score']:.2f}\n"
            else:
                message += "Detected by ML model\n"
        
        if count > max_items:
            message += f"\n... and {count - max_items} more\n"
        
        # Send via Slack
        if self.slack_webhook:
            try:
                payload = {
                    'text': message,
                    'username': 'CI/CD Anomaly Detector',
                    'icon_emoji': ':robot_face:'
                }
                
                response = requests.post(self.slack_webhook, json=payload, timeout=10)
                return response.status_code == 200
            except Exception as e:
                logger.error(f"Error sending batch alert: {e}")
                return False
        
        return False


def main():
    """Example usage"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    config = {
        'slack_webhook_url': os.getenv('SLACK_WEBHOOK_URL', ''),
        'smtp_user': os.getenv('SMTP_USER', ''),
        'smtp_password': os.getenv('SMTP_PASSWORD', ''),
        'alert_email': os.getenv('ALERT_EMAIL', ''),
    }
    
    alert_manager = AlertManager(config)
    
    # Mock anomaly
    anomaly = {
        'max_z_score': 4.5,
        'anomaly_features': [
            {
                'feature': 'duration',
                'value': 800.0,
                'expected': 300.0,
                'z_score': 4.5
            },
            {
                'feature': 'failure_count',
                'value': 15.0,
                'expected': 2.0,
                'z_score': 3.8
            }
        ],
        'data': {
            'job_name': 'production-deploy',
            'duration': 800.0,
            'result': 'FAILURE',
            'failure_count': 15
        }
    }
    
    print("Sending test alert...")
    results = alert_manager.send_alert(anomaly, channels=['slack'])
    print(f"Alert results: {results}")


if __name__ == "__main__":
    main()
