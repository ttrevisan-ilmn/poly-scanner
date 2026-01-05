# Polymarket Whale Tracker 🐳

A powerful real-time and historical scanner for finding large "Whale" trades on [Polymarket](https://polymarket.com).

## Features
- **Live Monitor**: Watch trades in real-time across top 10,000 markets.
- **Historical Scanner**: Scan past 24h (or up to 7 days) for missed whale activity.
- **Whale Profiling**: Detects "New Users" (Fresh Wallets) vs experienced traders.
- **Rich Context**: Shows Volume, Liquidity, and specific Outcome (Yes/No/Trump/Harris etc).
- **Discord Alerts**: Sends beautiful, formatted alerts to your Discord channel.
- **Smart Filtering**: Ignores Sports markets (optional) and likely Market Makers.

## Installation

1. Clone the repo.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Requires: `requests`, `websocket-client`, `rich`, `python-dateutil`, `certifi`)*

3. Set your Discord Webhook URL in `whale_tracker.py` (Line ~30).

## Usage

### 1. Web Dashboard (Recommended)
Launch the interactive dashboard with Live Monitor, Historical Scanner, and Smart Money Radar.
```bash
python3 -m streamlit run app.py
```

### 2. Live Monitor (CLI)
By default, this monitors for trades **> $6,000 USD** in real-time.
```bash
python3 whale_tracker.py
```

### 2. Historical Scan
Scan the last 24 hours of trading data.
```bash
python3 whale_tracker.py --scan
```

### 3. Custom Examples

**Scan last 7 days for massive bets > $20,000:**
```bash
python3 whale_tracker.py --scan --days 7 --threshold 20000
```

**Monitor Live but with lower threshold ($1,000):**
```bash
python3 whale_tracker.py --threshold 1000
```

**Scan only the top 500 markets (faster):**
```bash
python3 whale_tracker.py --scan --limit 500
```

## Command Reference

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--scan` | Run in historical mode logic | Live Mode |
| `--threshold` | Minimum $ value to alert | 6000 |
| `--days` | Days to look back (Scan only) | 1 |
| `--limit` | Max active markets to fetch | 10000 |

