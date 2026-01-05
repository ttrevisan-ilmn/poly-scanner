# Raspberry Pi Deployment Guide
**Run your Polymarket Whale Tracker 24/7 on DietPI**

---

## Prerequisites
- Raspberry Pi (3B+ or newer recommended) running DietPI
- SSH access to your Pi
- GitHub repository with this code

---

## Step 1: Initial Setup on Raspberry Pi

### 1.1 Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 1.2 Install Python and Dependencies
```bash
sudo apt install python3 python3-pip git -y
```

### 1.3 Clone Repository
```bash
cd ~
git clone https://github.com/ttrevisan-ilmn/poly-scanner.git
cd poly-scanner
```

### 1.4 Install Python Requirements
```bash
pip3 install -r requirements.txt
```

### 1.5 Set Up Discord Webhook (Optional)
```bash
# Edit whale_tracker.py and add your Discord webhook URL
nano whale_tracker.py
# Replace: DISCORD_WEBHOOK_URL = "YOUR_DISCORD..."
```

---

## Step 2: Create Systemd Service for Live Monitor

### 2.1 Create Service File
```bash
sudo nano /etc/systemd/system/whale-tracker.service
```

### 2.2 Add This Configuration
```ini
[Unit]
Description=Polymarket Whale Tracker Live Monitor
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/poly-scanner
ExecStart=/usr/bin/python3 /home/pi/poly-scanner/whale_tracker.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 2.3 Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable whale-tracker.service
sudo systemctl start whale-tracker.service
```

### 2.4 Check Status
```bash
sudo systemctl status whale-tracker.service
```

### 2.5 View Logs
```bash
# Live logs
sudo journalctl -u whale-tracker.service -f

# Last 100 lines
sudo journalctl -u whale-tracker.service -n 100
```

---

## Step 3: Auto-Deploy on Git Push (Option A: GitHub Actions)

### 3.1 Create SSH Key on Pi
```bash
ssh-keygen -t ed25519 -C "whale-tracker-deploy"
cat ~/.ssh/id_ed25519.pub
# Copy this public key
```

### 3.2 Add Deploy Key to GitHub
1. Go to: `https://github.com/ttrevisan-ilmn/poly-scanner/settings/keys`
2. Click "Add deploy key"
3. Paste public key, name it "Raspberry Pi", check "Allow write access"

### 3.3 Create Deployment Script
```bash
nano ~/deploy-whale-tracker.sh
```

Add this:
```bash
#!/bin/bash
cd /home/pi/poly-scanner
git pull origin main
pip3 install -r requirements.txt
sudo systemctl restart whale-tracker.service
echo "Deployed at $(date)" >> /home/pi/deploy.log
```

Make executable:
```bash
chmod +x ~/deploy-whale-tracker.sh
```

### 3.4 Set Up Webhook Listener (Using webhook package)
```bash
pip3 install webhook
```

Create webhook config:
```bash
nano ~/webhook.json
```

Add:
```json
[
  {
    "id": "whale-tracker-deploy",
    "execute-command": "/home/pi/deploy-whale-tracker.sh",
    "command-working-directory": "/home/pi/poly-scanner",
    "response-message": "Deploying whale tracker..."
  }
]
```

Create webhook service:
```bash
sudo nano /etc/systemd/system/webhook.service
```

Add:
```ini
[Unit]
Description=Webhook Listener for Auto-Deploy
After=network.target

[Service]
Type=simple
User=pi
ExecStart=/usr/local/bin/webhook -hooks /home/pi/webhook.json -port 9000 -verbose
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable webhook.service
sudo systemctl start webhook.service
```

### 3.5 Configure GitHub Webhook
1. Go to: `https://github.com/ttrevisan-ilmn/poly-scanner/settings/hooks`
2. Click "Add webhook"
3. Payload URL: `http://YOUR_PI_IP:9000/hooks/whale-tracker-deploy`
4. Content type: `application/json`
5. Select "Just the push event"
6. Click "Add webhook"

---

## Step 3 Alternative: Auto-Deploy with Cron (Simpler)

If you don't want webhooks, use a cron job to poll Git every 5 minutes:

### 3.1 Create Deployment Script (Same as above)
```bash
nano ~/deploy-whale-tracker.sh
```

Add:
```bash
#!/bin/bash
cd /home/pi/poly-scanner
git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ $LOCAL != $REMOTE ]; then
    echo "New changes detected. Deploying..."
    git pull origin main
    pip3 install -r requirements.txt
    sudo systemctl restart whale-tracker.service
    echo "Deployed at $(date)" >> /home/pi/deploy.log
else
    echo "No changes. Skipping deployment." >> /home/pi/deploy.log
fi
```

Make executable:
```bash
chmod +x ~/deploy-whale-tracker.sh
```

### 3.2 Add to Crontab
```bash
crontab -e
```

Add this line (check every 5 minutes):
```
*/5 * * * * /home/pi/deploy-whale-tracker.sh >> /home/pi/deploy-cron.log 2>&1
```

---

## Step 4: Access Web Dashboard Remotely (Optional)

If you want to access the Streamlit app from your local computer:

### Option A: SSH Tunnel
On your local machine:
```bash
ssh -L 8501:localhost:8501 pi@YOUR_PI_IP
```

Then on the Pi, start Streamlit:
```bash
streamlit run app.py
```

Visit on your local machine: `http://localhost:8501`

### Option B: Run Streamlit as Service on Pi
```bash
sudo nano /etc/systemd/system/whale-dashboard.service
```

Add:
```ini
[Unit]
Description=Whale Tracker Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/poly-scanner
ExecStart=/usr/local/bin/streamlit run app.py --server.address 0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable whale-dashboard.service
sudo systemctl start whale-dashboard.service
```

Access at: `http://YOUR_PI_IP:8501`

---

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u whale-tracker.service -n 50

# Test manually
cd ~/poly-scanner
python3 whale_tracker.py
```

### Database permissions
```bash
# Ensure database directory is writable
chmod 755 ~/poly-scanner
```

### Memory issues (common on Pi Zero)
```bash
# Reduce market limit in whale_tracker.py
# Change MAX_MARKETS from 10000 to 1000
```

---

## Maintenance Commands

```bash
# Restart tracker
sudo systemctl restart whale-tracker.service

# Stop tracker
sudo systemctl stop whale-tracker.service

# View live logs
sudo journalctl -u whale-tracker.service -f

# Manual deploy
cd ~/poly-scanner && git pull && sudo systemctl restart whale-tracker.service

# Check disk space (database grows over time)
df -h
```

---

## Recommended: Set Up Log Rotation

Prevent logs from filling disk:
```bash
sudo nano /etc/logrotate.d/whale-tracker
```

Add:
```
/home/pi/poly-scanner/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

---

**Your Pi is now a 24/7 whale tracking machine! 🐳**
