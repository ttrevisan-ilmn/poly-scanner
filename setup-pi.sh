#!/bin/bash
################################################################################
# Polymarket Whale Tracker - Raspberry Pi One-Click Setup
# Run this script on your Raspberry Pi to install and configure everything
################################################################################

set -e  # Exit on any error

echo "======================================================================"
echo "  Polymarket Whale Tracker - Raspberry Pi Setup"
echo "======================================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="$HOME/poly-scanner"
REPO_URL="https://github.com/ttrevisan-ilmn/poly-scanner.git"
SERVICE_USER=$(whoami)

echo -e "${YELLOW}This script will:${NC}"
echo "  1. Install Python dependencies"
echo "  2. Clone/update the repository"
echo "  3. Install Python packages"
echo "  4. Create systemd service for 24/7 monitoring"
echo "  5. Set up auto-deployment (git pull every 5 min)"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

################################################################################
# Step 1: Update system and install dependencies
################################################################################
echo -e "\n${GREEN}[1/6] Updating system packages...${NC}"
sudo apt update
sudo apt install -y python3 python3-pip git

################################################################################
# Step 2: Clone or update repository
################################################################################
echo -e "\n${GREEN}[2/6] Setting up repository...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo "Repository already exists. Pulling latest changes..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

################################################################################
# Step 3: Install Python dependencies
################################################################################
echo -e "\n${GREEN}[3/6] Installing Python packages...${NC}"
pip3 install -r requirements.txt
echo "Python packages installed successfully."

################################################################################
# Step 4: Create systemd service for live monitor
################################################################################
echo -e "\n${GREEN}[4/6] Creating systemd service...${NC}"

sudo tee /etc/systemd/system/whale-tracker.service > /dev/null <<EOF
[Unit]
Description=Polymarket Whale Tracker Live Monitor
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/whale_tracker.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable whale-tracker.service
echo "Systemd service created and enabled."

################################################################################
# Step 5: Create auto-deployment script
################################################################################
echo -e "\n${GREEN}[5/6] Setting up auto-deployment...${NC}"

cat > "$HOME/deploy-whale-tracker.sh" <<'EOF'
#!/bin/bash
# Auto-deploy script - checks for new commits and deploys

cd $HOME/poly-scanner
git fetch origin main > /dev/null 2>&1

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] New changes detected. Deploying..." >> $HOME/deploy.log
    git pull origin main >> $HOME/deploy.log 2>&1
    pip3 install -q -r requirements.txt >> $HOME/deploy.log 2>&1
    sudo systemctl restart whale-tracker.service
    echo "[$(date)] Deployment complete!" >> $HOME/deploy.log
fi
EOF

chmod +x "$HOME/deploy-whale-tracker.sh"

# Add to crontab if not already present
(crontab -l 2>/dev/null | grep -q "deploy-whale-tracker.sh") || \
(crontab -l 2>/dev/null; echo "*/5 * * * * $HOME/deploy-whale-tracker.sh") | crontab -

echo "Auto-deployment configured (checks every 5 minutes)."

################################################################################
# Step 6: Start the service
################################################################################
echo -e "\n${GREEN}[6/6] Starting whale tracker service...${NC}"
sudo systemctl start whale-tracker.service
sleep 2

# Check status
if sudo systemctl is-active --quiet whale-tracker.service; then
    echo -e "${GREEN}✓ Service started successfully!${NC}"
else
    echo -e "${RED}✗ Service failed to start. Checking logs...${NC}"
    sudo journalctl -u whale-tracker.service -n 20
    exit 1
fi

################################################################################
# Setup Complete
################################################################################
echo ""
echo "======================================================================"
echo -e "${GREEN}  Setup Complete! 🐳${NC}"
echo "======================================================================"
echo ""
echo "Your Raspberry Pi is now tracking whales 24/7!"
echo ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo "  View live logs:    sudo journalctl -u whale-tracker.service -f"
echo "  Restart service:   sudo systemctl restart whale-tracker.service"
echo "  Stop service:      sudo systemctl stop whale-tracker.service"
echo "  Check status:      sudo systemctl status whale-tracker.service"
echo "  View deploy log:   tail -f ~/deploy.log"
echo ""
echo -e "${YELLOW}Optional: Run Streamlit Dashboard${NC}"
echo "  ssh -L 8501:localhost:8501 pi@$(hostname -I | awk '{print $1}')"
echo "  Then: cd ~/poly-scanner && streamlit run app.py"
echo "  Visit: http://localhost:8501"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. (Optional) Edit whale_tracker.py to add Discord webhook"
echo "  2. Just 'git push' from your Mac - Pi auto-updates every 5 min!"
echo ""
echo "======================================================================"
