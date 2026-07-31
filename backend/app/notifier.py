import requests
import json
from datetime import datetime

def send_discord_alert(webhook_url: str, title: str, description: str, fields: list = None, color: int = 15548997):
    """
    Sends a rich embed notification to a Discord Webhook channel.
    color: 15548997 is red (#ED4245), 5763719 is green (#57F287)
    """
    if not webhook_url:
        print("[!] No Discord Webhook URL provided. Skipping alert.")
        return False
        
    payload = {
        "username": "DevOps AI Agent",
        "embeds": [
            {
                "title": title,
                "description": description[:2000],  # Discord limit: 2048 chars for description
                "color": color,
                "fields": fields or [],
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "footer": {
                    "text": "AI Log Analyzer System"
                }
            }
        ]
    }
    
    try:
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code in [200, 204]:
            print("[*] Successfully sent alert to Discord.")
            return True
        else:
            print(f"[!] Discord API returned status: {response.status_code}, response: {response.text}")
            return False
    except Exception as e:
        print(f"[!] Failed to send Discord alert: {str(e)}")
        return False
