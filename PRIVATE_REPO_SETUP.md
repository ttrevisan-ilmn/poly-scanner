# Private Repository Setup for Raspberry Pi

If your repository is **private**, you need to authenticate the Pi with GitHub using SSH keys.

---

## One-Time Setup (On Your Raspberry Pi)

### Step 1: Generate SSH Key on Pi
```bash
ssh pi@YOUR_PI_IP

# Generate SSH key (press Enter for all prompts)
ssh-keygen -t ed25519 -C "raspberry-pi-whale-tracker"

# Display the public key
cat ~/.ssh/id_ed25519.pub
```

**Copy the entire output** (starts with `ssh-ed25519 ...`)

---

### Step 2: Add SSH Key to GitHub

1. Go to: **https://github.com/settings/keys**
2. Click **"New SSH key"**
3. Title: `Raspberry Pi Whale Tracker`
4. Key: Paste the key from Step 1
5. Click **"Add SSH key"**

---

### Step 3: Test Connection
```bash
ssh -T git@github.com
# Should see: "Hi USERNAME! You've successfully authenticated..."
```

---

### Step 4: Clone Repo Using SSH (Not HTTPS)

**Update the setup script** or clone manually:

```bash
# Manual clone with SSH
git clone git@github.com:ttrevisan-ilmn/poly-scanner.git ~/poly-scanner
cd ~/poly-scanner
```

**OR** download and modify the setup script:

```bash
# Download setup script
wget https://raw.githubusercontent.com/ttrevisan-ilmn/poly-scanner/main/setup-pi.sh

# Edit the REPO_URL line
nano setup-pi.sh
# Change: REPO_URL="https://github.com/..."
# To:     REPO_URL="git@github.com:ttrevisan-ilmn/poly-scanner.git"

# Run it
chmod +x setup-pi.sh
./setup-pi.sh
```

---

## Alternative: Make Repo Public (Simpler)

If you don't mind the code being public:

1. Go to: **https://github.com/ttrevisan-ilmn/poly-scanner/settings**
2. Scroll to **"Danger Zone"**
3. Click **"Change visibility"** → **"Make public"**
4. Use the original setup script (no SSH needed)

---

## Why SSH Keys?

- ✅ Secure (no passwords in scripts)
- ✅ Works with private repos
- ✅ Auto-deploy works seamlessly
- ✅ One-time setup

The Pi can now `git pull` automatically every day without prompting for credentials!
