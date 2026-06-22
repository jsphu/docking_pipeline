import os
import logging
import time
import threading
import requests
import smtplib
import subprocess
import re
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)

class Notifier:
    """Handles sending notifications to various services."""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN") or self.config.get("telegram_bot_token")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID") or self.config.get("telegram_chat_id")
        
        self.smtp_server = os.environ.get("SMTP_SERVER") or self.config.get("smtp_server")
        self.smtp_port = int(os.environ.get("SMTP_PORT", 587))
        self.smtp_user = os.environ.get("SMTP_USER") or self.config.get("smtp_user")
        self.smtp_password = os.environ.get("SMTP_PASSWORD") or self.config.get("smtp_password")
        
        # Priority for recipient email: NOTIFY_USER (from .env) -> NOTIFY_EMAIL -> config
        self.notify_email = os.environ.get("NOTIFY_USER") or os.environ.get("NOTIFY_EMAIL") or self.config.get("notify_email")

    def is_configured(self):
        """Returns True if at least one notification service is configured."""
        has_telegram = bool(self.telegram_token and self.telegram_chat_id)
        has_email = bool(self.smtp_server and self.notify_email)
        return has_telegram or has_email

    def notify(self, message):
        """Sends notification to all configured services."""
        logger.info(f"Notification: {message}")
        
        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(message)
            
        if self.notify_email:
            if self.smtp_server:
                self._send_email_smtp(message)
            else:
                self._send_email_sendmail(message)

    def _send_telegram(self, message):
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {"chat_id": self.telegram_chat_id, "text": message}
            requests.post(url, json=data, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    def _send_email_smtp(self, message):
        try:
            msg = MIMEText(message)
            msg['Subject'] = f'MD Progress: {self.complex_id if hasattr(self, "complex_id") else "Simulation"}'
            msg['From'] = self.smtp_user
            msg['To'] = self.notify_email
            
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            logger.debug(f"Email sent to {self.notify_email}")
        except Exception as e:
            logger.error(f"Failed to send SMTP notification: {e}")

    def _send_email_sendmail(self, message):
        """Uses local sendmail binary."""
        try:
            msg = MIMEText(message)
            msg['Subject'] = 'MD Simulation Progress Update'
            msg['From'] = self.smtp_user or 'md-workflow@localhost'
            msg['To'] = self.notify_email
            
            process = subprocess.Popen(["/usr/sbin/sendmail", "-t", "-oi"], stdin=subprocess.PIPE)
            process.communicate(msg.as_bytes())
            if process.returncode != 0:
                logger.error(f"Sendmail failed with code {process.returncode}")
        except Exception as e:
            logger.error(f"Failed to send Sendmail notification: {e}")

class ProgressMonitor(threading.Thread):
    """Monitors GROMACS log file and sends progress notifications."""
    
    def __init__(self, log_path, complex_id, interval_sec, notifier):
        super().__init__()
        self.log_path = log_path
        self.complex_id = complex_id
        self.interval_sec = interval_sec
        self.notifier = notifier
        self.stop_event = threading.Event()
        self.daemon = True

    def stop(self):
        self.stop_event.set()

    def run(self):
        logger.info(f"Starting progress monitor for {self.complex_id} (Interval: {self.interval_sec}s)")
        last_notified_time = -1.0
        
        while not self.stop_event.is_set():
            if os.path.exists(self.log_path):
                try:
                    # Robust way to find the last progress line
                    cmd = f"grep -A 1 \"Step\" {self.log_path} | grep -v \"Step\" | grep -v \"\\--\" | tail -n 1"
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    line = result.stdout.strip()
                    
                    if line:
                        numbers = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
                        if len(numbers) >= 2:
                            sim_time = float(numbers[1])
                            
                            # Only notify if simulation time has actually advanced
                            if sim_time > last_notified_time:
                                time_ns = sim_time / 1000.0
                                message = f"Complex {self.complex_id} passes {time_ns:.3f} ns right now."
                                # Temporarily add complex_id context for email subject
                                self.notifier.complex_id = self.complex_id
                                self.notifier.notify(message)
                                last_notified_time = sim_time
                                
                except Exception as e:
                    logger.debug(f"Monitor error: {e}")
            
            # Wait for the next interval
            self.stop_event.wait(self.interval_sec)
        
        logger.info(f"Progress monitor for {self.complex_id} stopped.")
