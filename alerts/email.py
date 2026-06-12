"""
alerts/email.py
SMTP email alerts.

Functions:
  send_email_band_drop() — fired by Agent 1 on band worsening
  send_lever_email()     — fired by Agent 3 on SLA threshold crossing
"""

import logging
import os
import re
import smtplib
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText

logger = logging.getLogger(__name__)


# ── Agent 1 — Band drop alert ─────────────────────────────────────────────────

def send_email_band_drop(skill_name: str, old_band: str, new_band: str,
                          metric, message: str) -> bool:
    """Send email when a specific skill drops to a worse band."""
    smtp_server = os.getenv("SMTP_SERVER")
    if not smtp_server:
        logger.warning("SMTP_SERVER not set.")
        return False

    band_colors = {
        "SEVERE":   "#7b0000",
        "CRITICAL": "#dc3545",
        "WARNING":  "#f57c00",
        "HEALTHY":  "#28a745"
    }
    hdr_color = band_colors.get(new_band, "#dc3545")

    html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', message)
    html_body = html_body.replace('\n', '<br>')

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#2c3e50;max-width:700px;margin:0 auto;padding:20px;">
        <div style="background:{hdr_color};padding:20px;border-radius:8px;margin-bottom:20px;">
            <h2 style="color:white;margin:0;">
                {skill_name} — {old_band} → {new_band}
            </h2>
        </div>
        <div style="background:#fff;padding:20px;border-radius:8px;border:1px solid #e0e0e0;line-height:1.7;">
            <p>{html_body}</p>
        </div>
        <h3 style="margin-top:20px;">Skill Snapshot</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead><tr style="background:#f0f4f8;">
                <th style="padding:8px;text-align:left;">Metric</th>
                <th style="padding:8px;text-align:center;">Value</th>
            </tr></thead>
            <tbody>
                <tr><td style="padding:7px;">Service Level</td>
                    <td style="padding:7px;text-align:center;font-weight:700;color:{hdr_color};">
                        {metric.service_level:.1f}%</td></tr>
                <tr><td style="padding:7px;">Calls in Queue</td>
                    <td style="padding:7px;text-align:center;">{metric.calls_waiting}</td></tr>
                <tr><td style="padding:7px;">Skill Avail</td>
                    <td style="padding:7px;text-align:center;">{metric.agents_available}</td></tr>
                <tr><td style="padding:7px;">On AUX</td>
                    <td style="padding:7px;text-align:center;color:#6a1b9a;font-weight:700;">
                        {metric.agents_on_aux}</td></tr>
                <tr><td style="padding:7px;">OCW</td>
                    <td style="padding:7px;text-align:center;">{metric.ocw}</td></tr>
                <tr><td style="padding:7px;">Headcount</td>
                    <td style="padding:7px;text-align:center;">{metric.headcount}</td></tr>
            </tbody>
        </table>
        <p style="color:#aaa;font-size:11px;margin-top:20px;">RTA SLA Tracker — Auto-generated alert</p>
    </body></html>"""

    msg            = MIMEMultipart('alternative')
    msg['Subject'] = f"[{new_band}] {skill_name}: {old_band} → {new_band} ({metric.service_level:.1f}%)"
    msg['From']    = os.getenv("SMTP_USERNAME")
    msg['To']      = os.getenv("EMAIL_MANAGERS")
    msg.attach(MIMEText(html, 'html'))

    try:
        server = smtplib.SMTP(smtp_server, int(os.getenv("SMTP_PORT", "587")))
        server.starttls()
        server.login(msg['From'], os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent: {skill_name} {old_band}→{new_band}")
        return True
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False


# ── Agent 3 — Lever report email ──────────────────────────────────────────────

def send_lever_email(subject: str, body: str, skill_name: str,
                     lever_name: str, region: str) -> bool:
    """
    Send Lever report email to managers.
    Called by Agent 3 when SLA crosses 90 / 80 / 70 threshold.
    Fires once per threshold crossing per skill.
    """
    smtp_server    = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port      = int(os.getenv("SMTP_PORT", "587"))
    smtp_user      = os.getenv("SMTP_USERNAME", "")
    smtp_pass      = os.getenv("SMTP_PASSWORD", "")
    recipients_str = os.getenv("EMAIL_MANAGERS", "")

    if not smtp_user or not recipients_str:
        logger.warning("A3 Email: SMTP credentials or recipients not configured.")
        return False

    recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]

    # Lever colour based on severity
    lever_colors = {
        "AMBER": "#FF9900",
        "RED":   "#CC0000",
        "BLACK": "#111111",
    }
    color = lever_colors.get(lever_name.upper(), "#333333")

    # HTML version — styled like the real Lever report
    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#2c3e50;max-width:750px;margin:0 auto;padding:20px;">

      <!-- Header banner -->
      <div style="background:{color};padding:16px 20px;border-radius:8px 8px 0 0;">
        <h2 style="color:white;margin:0;font-size:16px;">
          {region} | {skill_name} | {lever_name} LEVER
        </h2>
      </div>

      <!-- Body -->
      <div style="border:2px solid {color};border-top:none;padding:20px;
                  border-radius:0 0 8px 8px;background:#fff;">
        <pre style="font-family:Arial,sans-serif;font-size:13px;
                    line-height:1.7;white-space:pre-wrap;color:#2c3e50;">
{body}
        </pre>
      </div>

      <!-- Footer -->
      <p style="color:#aaa;font-size:11px;margin-top:16px;text-align:center;">
        RTA Agentic SLA Monitoring System — Auto-generated Lever Report
      </p>

    </body>
    </html>"""

    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = smtp_user
    msg['To']      = ", ".join(recipients)

    msg.attach(MIMEText(body, 'plain'))   # plain text fallback
    msg.attach(MIMEText(html, 'html'))    # HTML version

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipients, msg.as_string())
        server.quit()
        logger.info(
            f"A3 Lever email sent: [{lever_name}] {skill_name} | "
            f"to {recipients}"
        )
        return True
    except Exception as e:
        logger.error(f"A3 Lever email failed: {e}")
        return False