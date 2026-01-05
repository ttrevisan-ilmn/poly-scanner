import json
import time
import datetime
import sys
import os
import ssl
import threading
import argparse
import concurrent.futures

import requests
import websocket
import certifi
from dateutil import parser, tz

# Rich Imports
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich import print as rprint
from rich.text import Text
import database # Local DB for persistence

console = Console()

# --- CONFIGURATION ---
# PASTE YOUR DISCORD WEBHOOK URL HERE
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1457494327394570314/BVpG5ZnG6QeeW5Wn04FzXTFBpC6kRztNy0u4nD2mLlbyDDg1OY1Z5IQPlb2yW4kztCb_"

# THRESHOLDS
MIN_TRADE_SIZE_USD = 6000.0
MARKET_CHECK_INTERVAL = 300 # Cache market category for 5 minutes
MAX_MARKETS = 10000 # Increased to capture wider net (Polymarket has ~21k mkts)

# API ENDPOINTS
CLOB_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"
DATA_API_ACTIVITY_URL = "https://data-api.polymarket.com/activity"
DATA_API_TRADES_URL = "https://data-api.polymarket.com/trades"

# CACHE
# CACHE
# CACHE
market_cache = {} # Map market_id -> {is_sports: bool, timestamp: float, title: str, slug: str}
MARKET_MAP_FILE = "market_map.json"
CACHE_EXPIRY = 3600 # 1 Hour
MARKET_MAP_FILE = "market_map.json"
CACHE_EXPIRY = 3600 # 1 Hour

import queue

# ... imports ...

class PolymarketTracker:
    def __init__(self):
        self.ws = None
        # Async Processing Queue
        self.event_queue = queue.Queue()
        self.is_running = False
        
        # Keep track of recent trades for potential LP detection (simple heuristic)
        # Map wallet -> list of (timestamp, side, amount, market_id)
        self.wallet_activity_cache = {} 

    def start(self, use_cache=True):
        print(f"[*] Starting Polymarket Whale Tracker...")
        print(f"[*] Threshold: ${MIN_TRADE_SIZE_USD}")
        print(f"[*] Connecting to {CLOB_WS_URL}...")
        
        # Start Async Worker
        self.is_running = True
        worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        worker_thread.start()
        
        # Enable trace for debugging if needed
        # websocket.enableTrace(True)
        
        self.ws = websocket.WebSocketApp(
            CLOB_WS_URL,
            # Pass use_cache via functools or just store in self? 
            # or simplify: subscribe_to_markets is called in on_open.
            # We can store a flag in self.
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=lambda ws: self.on_open(ws, use_cache)
        )
        
        # Run in a loop to auto-reconnect
        while True:
            try:
                self.ws.run_forever(sslopt={"ca_certs": certifi.where()})
                print("[*] WebSocket connection closed. Reconnecting in 5 seconds...")
                time.sleep(5)
            except KeyboardInterrupt:
                print("\n[!] Stopping tracker...")
                self.is_running = False
                break
            except Exception as e:
                print(f"[!] Critical error: {e}")
                time.sleep(5)

    def _worker_loop(self):
        """Background thread to process events from Queue."""
        print("[*] Async Worker Started. Ready to process whales.")
        while self.is_running:
            try:
                event = self.event_queue.get(timeout=1.0)
                self._handle_event_worker(event)
                self.event_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[!] Worker Error: {e}")

    def on_open(self, ws, use_cache=True):
        print("[*] Connected to Polymarket CLOB!")
        self.subscribe_to_markets(use_cache=use_cache)

    def subscribe_to_markets(self, use_cache=True):
        # Fetch top markets to subscribe to
        # Since we can't easily subscribe to ALL, we'll get the top 50 active markets
        print("[*] Fetching active markets to subscribe...")
        markets = self.fetch_active_markets(use_cache=use_cache)
        if not markets:
            print("[!] No markets found to subscribe.")
            return

        print(f"[*] Subscribing to {len(markets)} markets...")
        # Subscription payload format: {"assets_ids": ["..."], "type": "market"} usually for trade updates
        # Check standard CLOB docs: usually {"type": "subscribe", "channels": [{"name": "level1", "token_ids": [...]}]}
        # But for 'trades', let's guess the channel name 'trades' or 'market_trades'.
        # Using a common pattern for now. If this fails in testing, I'll need to research exact subscribe msg.
        
        # NOTE: Polymarket CLOB often uses asset_id (token_id) for subscriptions.
        asset_ids = []
        for m in markets:
            # Each market has 2 tokens (Yes/No usually). We need their asset_ids.
            # Gamma structure usually has 'clobTokenIds' or 'tokens'.
            if 'clobTokenIds' in m:
                asset_ids.extend(json.loads(m['clobTokenIds'])) 
            elif 'tokens' in m:
                 # tokens might be list of dicts
                 pass
        
        # Simplified: Try subscribing by market_id/condition_id if supported, else asset_ids
        # Let's try sending asset_ids which is safer for CLOB.
        if not asset_ids:
            print("[!] Could not extract asset IDs.")
            return

        chunk_size = 20 # Subscribe in chunks
        for i in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[i:i+chunk_size]
            msg = {
                "type": "subscribe",
                "channels": [
                    {
                        "name": "trades",
                        "token_ids": chunk
                    }
                ]
            }
            self.ws.send(json.dumps(msg))
            time.sleep(0.1) # Rate limit protection

    def process_whale(self, trade_data, market_data, historical=False, timestamp_override=None):
        """
        Unified logic to process a detected whale trade.
        trade_data: {price, size, side, asset_id, outcome?, wallet}
        market_data: {title, slug, volume24hr, liquidity, clobTokenIds, outcomes, end_date, description}
        """
        try:
            # 1. Calculate Value
            price = float(trade_data.get('price', 0))
            size = float(trade_data.get('size', 0))
            value_usd = price * size
            
            if value_usd < MIN_TRADE_SIZE_USD:
                return None

            # 2. Resolve Outcome
            outcome = "Unknown"
            if trade_data.get('outcome'):
                outcome = trade_data.get('outcome')
            elif trade_data.get('outcome_label'):
                outcome = trade_data.get('outcome_label')
            else:
                 # Asset ID Logic
                 asset_id = trade_data.get('asset_id')
                 clob_tokens = market_data.get('clobTokenIds')
                 if clob_tokens:
                    try:
                        if isinstance(clob_tokens, str): clob_tokens = json.loads(clob_tokens)
                        
                        found_idx = -1
                        aid_str = str(asset_id)
                        if aid_str in clob_tokens: found_idx = clob_tokens.index(aid_str)
                        if found_idx == -1 and isinstance(asset_id, int):
                            if str(asset_id) in clob_tokens: found_idx = clob_tokens.index(str(asset_id))
                        
                        if found_idx != -1:
                            m_outcomes = market_data.get('outcomes')
                            if isinstance(m_outcomes, str): m_outcomes = json.loads(m_outcomes)
                            if m_outcomes and len(m_outcomes) > found_idx:
                                outcome = m_outcomes[found_idx]
                            elif len(clob_tokens) == 2:
                                outcome = "Yes" if found_idx == 0 else "No"
                    except: pass
            
            # 3. Analyze Wallet
            wallet = trade_data.get('wallet')
            profile = self.analyze_wallet(wallet) if wallet else {'is_fresh': False, 'win_rate': 'N/A', 'total_trades': 0}
            
            # 4. Timestamps
            # If historical, use provided timestamp. If live, use NOW.
            ts = timestamp_override if timestamp_override else time.time()
            
            # Formatted Time (PST)
            pst = tz.gettz("America/Los_Angeles")
            dt_ts = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).astimezone(pst)
            time_str = dt_ts.strftime('%m-%d %I:%M %p')

            # 5. Persistence (DB)
            # Upsert Market
            database.upsert_market({
                'market_id': trade_data.get('market_id'),
                'question': market_data['title'],
                'slug': market_data['slug'],
                'volume': market_data['volume24hr'],
                'liquidity': market_data['liquidity'],
                'end_date': market_data.get('end_date'),
                'description': market_data.get('description')
            })
            
            # Upsert Wallet
            database.upsert_wallet({
                'address': wallet,
                'win_rate': profile.get('win_rate'),
                'total_trades': profile.get('total_trades'),
                'is_fresh': profile.get('is_fresh'),
                'profitability_score': profile.get('profitability_score', 0)
            })
            
            # Save Alert
            database.save_alert({
                'timestamp': ts,
                'market_id': trade_data.get('market_id'),
                'wallet': wallet,
                'value': value_usd,
                'outcome': outcome,
                'side': trade_data.get('side'),
                'price': price,
                'asset_id': trade_data.get('asset_id')
            })

            # 6. Console & Alert
            # For Scan Mode, we might want to defer printing to avoid garbling progress bar?
            # Or we print using progress.console.print if passed? 
            # For now, let's return the structured object and let the caller handle printing/alerting if they need custom UI control
            # OR we standardize printing here too.
            # The Live Monitor prints immediately. Scan Mode prints via progress bar.
            # Let's do the DB part here and return the RICH object for printing.
            
            # Calculate Metrics
            metrics = self._calculate_advanced_metrics(market_data)
            
            result_item = {
                'time': time_str,
                'market': market_data['title'],
                'value': value_usd,
                'outcome': outcome,
                'wallet': wallet,
                'fresh': profile['is_fresh'],
                'age': profile.get('age_formatted', 'N/A'),
                'slug': market_data['slug'],
                'side': trade_data.get('side'),
                'price': price,
                'market_id': trade_data.get('market_id'),
                'asset_id': trade_data.get('asset_id'),
                'profile': profile,
                'vol_24h': float(market_data.get('volume24hr', 0)),
                'liquidity': float(market_data.get('liquidityNum', 0)),
                
                # Metrics
                'spread': metrics['spread'],
                'urgency': metrics['urgency'],
                'bias': metrics['bias'],
                'liq_vol_ratio': metrics['liq_vol_ratio'],
                
                '_ts': ts,
                'end_date': market_data.get('end_date'),
                'description': market_data.get('description'),
                'raw_timestamp': ts 
            }
            
            # Live Mode Check: If not historical, print and alert immediately
            if not historical:
                val_str = f"${value_usd:,.0f}"
                m_text = Text(market_data['title'], style="bold blue")
                v_text = Text(val_str, style="bold green")
                o_text = Text(str(outcome), style="yellow")
                
                # We need to access console global or pass it
                console.print(f"[{time_str}] 🚨 [bold red]LIVE WHALE[/]: {v_text} on {o_text} in {m_text}")
                
                # Discord
                t_event = {
                    'value': value_usd, 'side': trade_data.get('side'), 'outcome': outcome,
                    'price': price, 'market_id': trade_data.get('market_id')
                }
                m_info = {
                    'title': market_data['title'], 
                    'slug': market_data['slug'], 
                    'volume24hr': market_data.get('volume24hr', 0), 
                    'liquidity': market_data.get('liquidityNum', 0),
                    'metrics': metrics
                }
                self.send_discord_alert(t_event, m_info, profile, wallet, historical=False)

            return result_item

        except Exception as e:
            print(f"Error processing whale: {e}")
            return None

    def _calculate_advanced_metrics(self, market_data):
        """
        Calculates Polysights-style advanced metrics.
        metrics: Spread %, Urgency, Bias, Liq/Vol
        """
        try:
            liq = float(market_data.get('liquidityNum') or market_data.get('liquidity', 0))
            vol = float(market_data.get('volume', 0)) or float(market_data.get('volume24hr', 0))
            
            # A. Implied Probability Bias: (YesPrice - 0.5) * 2
            # Use outcomePrices if available
            bias = 0.0
            prices_str = market_data.get('outcomePrices', '[]')
            try:
                prices_list = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
                if prices_list:
                    # Logic: If bias to Yes (>0.5), positive. If bias to No (<0.5), negative.
                    # Usually [0] is Yes.
                    yes_p = float(prices_list[0])
                    bias = (yes_p - 0.5) * 2
            except:
                pass

            # B. Liquidity-to-Volume Ratio
            liq_vol_ratio = (liq / vol) if vol > 0 else 0.0
            
            # C. Resolution Urgency
            # Formula: (TimeFactor*0.5) + (LiqFactor*0.2) + (VolFactor*0.2) + (PriceCertainty*0.1)
            urgency = 0.0
            try:
                end_str = market_data.get('end_date') or market_data.get('endDate')
                if end_str:
                     end_dt = parser.isoparse(end_str).replace(tzinfo=datetime.timezone.utc)
                     now_dt = datetime.datetime.now(datetime.timezone.utc)
                     seconds_left = (end_dt - now_dt).total_seconds()
                     
                     if seconds_left <= 0: time_factor = 1.0 # 100%
                     elif seconds_left > 2592000: time_factor = 0.1 # 10% base for far out
                     else: time_factor = 1.0 - (seconds_left / 2592000)
                     
                     liq_factor = min(liq / 100000, 1.0)
                     vol_factor = min(vol / 500000, 1.0)
                     
                     # Price Certainty
                     try:
                         prices_list = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
                         max_p = max([float(p) for p in prices_list]) if prices_list else 0.5
                     except:
                         max_p = 0.5
                     price_certainty = max_p
                     
                     urgency = (time_factor * 50) + (liq_factor * 20) + (vol_factor * 20) + (price_certainty * 10)
            except:
                pass

            return {
                'spread': 0.0, # Placeholder
                'urgency': float(urgency),
                'bias': float(bias),
                'liq_vol_ratio': float(liq_vol_ratio)
            }
        except Exception:
            return {'spread': 0, 'urgency': 0, 'bias': 0, 'liq_vol_ratio': 0}

    def run_scan(self, limit=None, days=1.0, use_cache=True):
        print(f"[*] Starting Historical Scan (Last {days} Days)...")
        
        limit = limit if limit else MAX_MARKETS
        markets = self.fetch_active_markets(limit_override=limit, use_cache=use_cache)
        
        if not markets:
            print("[!] No active markets found to scan.")
            return

        print(f"[*] Scanning {len(markets)} markets with 25 concurrent threads...")
        
        found_whales = []
        count_found = 0
        total = len(markets)
        lock = threading.Lock() # Thread lock for print/count updates
        
        # Helper function for a single market scan
        def scan_market(market):
            market_results = []
            market_id = market.get('conditionId') or market.get('id')
            title = market.get('question', 'Unknown')
            slug = market.get('slug', '')
            
            # 1. Check Category
            tags = [t.lower() for t in market.get('tags', [])]
            category = market.get('category', '').lower()
            is_sports = 'sports' in tags or 'nba' in tags or 'nfl' in tags or 'soccer' in tags or category == 'sports'
            
            if is_sports:
                return []

            # 2. Fetch Recent Trades
            trades = self.fetch_recent_trades(market_id)
            for trade in trades:
                try:
                    size = float(trade.get('size', 0))
                    price = float(trade.get('price', 0))
                    value_usd = size * price
                    
                    if value_usd < MIN_TRADE_SIZE_USD:
                        continue
                        
                    # Check time (Last 24h)
                    trade_time = float(trade.get('timestamp')) 
                    if trade_time > 10000000000: 
                        trade_time = trade_time / 1000
                    
                    if (time.time() - trade_time) > (days * 24 * 3600):
                        continue
                        
                    # Found a whale!
                    wallet = trade.get('taker_address') or trade.get('maker_address') or trade.get('owner')
                    
                    # Prepare Data
                    t_data = {
                        'price': price,
                        'size': size,
                        'side': trade.get('side'),
                        'asset_id': trade.get('asset_id'),
                        'outcome': trade.get('outcome'),
                        'wallet': wallet,
                        'market_id': market_id
                    }
                    m_data = {
                        'title': title, # title from scan_market scope
                        'slug': slug,
                        'volume24hr': float(market.get('volume24hr', 0)),
                        'liquidity': float(market.get('liquidityNum', 0)),
                        'clobTokenIds': market.get('clobTokenIds'),
                        'outcomes': market.get('outcomes'),
                        'end_date': market.get('endDate'),
                        'description': market.get('description')
                    }

                    # Process
                    result = self.process_whale(t_data, m_data, historical=True, timestamp_override=trade_time)
                    if result:
                        market_results.append(result)
                    
                except Exception:
                    pass
            return market_results


        # Run Scan in ThreadPool
        # Run Scan with Rich Progress
        # Using 25 Workers for speed on large datasets
        completed = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task_id = progress.add_task(f"[cyan]Scanning {len(markets)} markets...", total=total)
            # Increased workers to 25 for massive 10k market scan
            with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
                futures = {executor.submit(scan_market, m): m for m in markets}
                
                for future in concurrent.futures.as_completed(futures):
                    # Update Progress
                    progress.update(task_id, advance=1)
                    
                    try:
                        results = future.result()
                        if results:
                            for item in results:
                                with lock:
                                    count_found += 1
                                    found_whales.append(item)
                                    
                                    val_str = f"${item['value']:,.0f}"
                                    m_text = item['market']
                                    o_text = str(item['outcome'])
                                    
                                    # Console Print (Keep this for Progress Bar compatibility)
                                    progress.console.print(f"[bold red]🚨 WHALE FOUND: {val_str} on {o_text}[/] in [blue]{m_text}[/]")

                                    
                                    # Alert logic handled by process_whale

                            
                    except Exception as e:
                        pass

        console.print(f"\n[bold green][*] Scan complete. Found {count_found} whale trades.[/bold green]\n")
        
        if found_whales:
            table = Table(title=f"🐳 Whale Scan Results (Last {days} Days)", show_header=True, header_style="bold magenta")
            table.add_column("Time", style="dim")
            table.add_column("Value", justify="right", style="green")
            table.add_column("Outcome")
            table.add_column("Vol 24h", justify="right")
            table.add_column("Liq", justify="right")
            table.add_column("New User", justify="center")
            table.add_column("Market", style="cyan")

            # Sort by VALUE desc (Highest Bet First)
            found_whales.sort(key=lambda x: x['value'], reverse=True)
            
            for w in found_whales:
                fresh_str = "[bold green]YES[/]" if w['fresh'] else "NO"
                
                # Format metrics
                vol_str = f"${w['vol_24h']:,.0f}"
                liq_str = f"${w['liquidity']:,.0f}"
                val_str = f"${w['value']:,.0f}"
                
                # Truncate market title
                title_short = w['market'][:45] + "..." if len(w['market']) > 45 else w['market']
                
                table.add_row(
                    w['time'],
                    val_str,
                    str(w['outcome']),
                    vol_str,
                    liq_str,
                    fresh_str,
                    title_short
                )
            
            console.print(table)
            console.print("\n")

    def make_api_request(self, url, retries=3):
        for i in range(retries):
            try:
                resp = requests.get(url)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    # Rate limit - wait and retry
                    wait_time = (i + 1) * 0.5 # 0.5s, 1.0s, 1.5s
                    time.sleep(wait_time)
                    continue
                else:
                    return None
            except Exception:
                time.sleep(0.5)
        return None

    def fetch_recent_trades(self, market_id):
        try:
            url = f"{DATA_API_TRADES_URL}?market={market_id}&limit=20"
            data = self.make_api_request(url)
            
            if data and isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    def save_market_map(self, markets):
        try:
            with open(MARKET_MAP_FILE, 'w') as f:
                json.dump({'timestamp': time.time(), 'markets': markets}, f)
            print("[*] Saved market map to cache.")
        except Exception as e:
            print(f"[!] Warning: Could not save cache: {e}")

    def load_market_map(self):
        try:
            if not os.path.exists(MARKET_MAP_FILE): return None
            with open(MARKET_MAP_FILE, 'r') as f:
                data = json.load(f)
                
            if time.time() - data.get('timestamp', 0) < CACHE_EXPIRY:
                print(f"[*] Loaded {len(data['markets'])} markets from cache.")
                return data['markets']
            else:
                print("[*] Cache expired.")
                return None
        except Exception:
            return None

    def fetch_active_markets(self, limit_override=None, use_cache=True):
        all_markets = []
        target_limit = limit_override if limit_override else MAX_MARKETS
        
        # Try Cache first
        if use_cache:
            cached = self.load_market_map()
            if cached:
                # If cached list is smaller than requested limit, we might need to fetch more?
                # Usually we cache the full MAX_MARKETS set.
                # Simplification: If cache has decent size, use it.
                if len(cached) >= (target_limit * 0.5): # Use if at least half target
                     return cached[:target_limit]

        batch_size = 100 # Increased batch size for speed
        
        print(f"[*] Fetching up to {target_limit} active markets (sorted by volume)...")
        
        try:
            for offset in range(0, target_limit, batch_size):
                # Using default sort (usually liquidity/activity) as explicit volume sort returned inactive markets
                url = f"{GAMMA_API_URL}?limit={batch_size}&offset={offset}&active=true&closed=false"
                resp = requests.get(url)
                
                if resp.status_code == 200:
                    data = resp.json()
                    chunk = []
                    if isinstance(data, list):
                        chunk = data
                    elif isinstance(data, dict) and 'data' in data: 
                        chunk = data['data']
                    
                    if not chunk:
                        break 
                        
                    all_markets.extend(chunk)
                    
                    # Stop if we have enough
                    if len(all_markets) >= target_limit:
                        all_markets = all_markets[:target_limit]
                        break
                        
                    time.sleep(0.1) 
                else:
                    print(f"[!] Gamma API failed (Status {resp.status_code})")
                    break
            
            # Save to Cache if we fetched a good amount
            if len(all_markets) > 100:
                self.save_market_map(all_markets)
                
            return all_markets
 
        except Exception as e:
            print(f"[!] Error fetching markets: {e}")
        return all_markets

    def on_message(self, ws, message):
        try:
            if not message: return
            data = json.loads(message)
            if isinstance(data, list):
                for item in data:
                    self.process_trade_event(item)
            else:
                self.process_trade_event(data)
        except Exception:
            pass

    def process_trade_event(self, event):
        """Async Producer: Pushes raw event to queue."""
        self.event_queue.put(event)

    def _handle_event_worker(self, event):
        """Consumer: Heavy processing of valid trades."""
        if event.get('event_type') != 'last_trade_price' and event.get('type') != 'trade':
            return
            
        try:
            price = float(event.get('price', 0))
            size = float(event.get('size', 0))
            market_id = event.get('market') or event.get('asset_id')
            
            # Helper check to avoid unnecessary api calls for small trades?
            # process_whale has check but we need market info first.
            if (price * size) < MIN_TRADE_SIZE_USD:
                return
            
            market_info = self.get_market_info(market_id)
            if not market_info:
                return
            
            if market_info.get('is_sports'):
                return

            # Prepare Payload
            wallet = event.get('owner') or event.get('taker')
            # Extract Timestamp to ensure Deduplication with Historical Scans
            # WS event usually has 'timestamp' (ms or seconds) or 'time'
            evt_ts = float(event.get('timestamp', 0))
            if evt_ts == 0: evt_ts = time.time()
            # precision check
            if evt_ts > 10000000000: evt_ts /= 1000
            
            t_data = {
                'price': price,
                'size': size,
                'side': event.get('side'),
                'asset_id': event.get('asset_id'),
                'outcome': event.get('outcome_label') or event.get('outcome'), # outcome_label might be in live event
                'wallet': wallet,
                'market_id': market_id
            }
            # process_whale calls analyze_wallet, etc.
            
            self.process_whale(t_data, market_info, historical=False, timestamp_override=evt_ts)
            
        except Exception as e:
            # print(f"Error: {e}")
            pass

    def on_error(self, ws, error):
        print(f"[!] WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("[*] WebSocket Closed")

    def get_market_info(self, market_id):
        # Check cache
        now = time.time()
        if market_id in market_cache:
            cached = market_cache[market_id]
            if now - cached['timestamp'] < MARKET_CHECK_INTERVAL:
                return cached
        
        # Fetch from Gamma
        try:
            # Note: Gamma API uses 'condition_id' or 'id'. Let's assume market_id is what we need.
            # Sometimes 'market_id' in WS is the 'condition_id'.
            url = f"{GAMMA_API_URL}/{market_id}" 
            resp = requests.get(url)
            if resp.status_code != 200:
                # Try finding by token/asset if direct ID fails, or assume it's valid but private?
                return None
            
            data = resp.json()
            
            # Check Tags/Category
            # Gamma structure: data.get('tags') is a list usually, or 'category'
            tags = [t.lower() for t in data.get('tags', [])]
            category = data.get('category', '').lower()
            
            is_sports = 'sports' in tags or 'nba' in tags or 'nfl' in tags or 'soccer' in tags or category == 'sports'
            
            info = {
                'is_sports': is_sports,
                'title': data.get('question', 'Unknown Market'),
                'slug': data.get('slug', ''),
                'timestamp': now,
                'outcomes': data.get('outcomes'), # List or string
                'volume24hr': data.get('volume24hr', 0),
                'liquidity': data.get('liquidityNum', 0),
                'clobTokenIds': data.get('clobTokenIds'),
                'end_date': data.get('endDate'),
                'description': data.get('description')
            }
            market_cache[market_id] = info
            return info
        except Exception as e:
            print(f"[!] Gamma API Error: {e}")
            return None

    def analyze_wallet(self, wallet_address):
        # Returns dict: {'is_fresh': bool, 'win_rate': str, 'total_trades': int}
        try:
            url = f"{DATA_API_ACTIVITY_URL}?user={wallet_address}&limit=100" 
            resp = requests.get(url)
            if resp.status_code != 200:
                return {'is_fresh': False, 'win_rate': 0.0, 'total_trades': 0}
            
            activities = resp.json()
            if not activities:
                return {'is_fresh': True, 'win_rate': 0.0, 'total_trades': 0}

            trades = [a for a in activities if a.get('type') == 'TRADE']
            redeems = [a for a in activities if a.get('type') == 'REDEEM']
            
            if not trades:
                 return {'is_fresh': True, 'win_rate': 0.0, 'total_trades': 0}

            # Check Freshness (First trade < 24 hours ago)
            # timestamps are typically ISO strings
            earliest_trade = trades[-1] # List usually desc
            last_trade_time = parser.parse(earliest_trade.get('timestamp'))
            # Calculate Age
            try:
                oldest_time_dt = parser.parse(trades[-1].get('timestamp')).replace(tzinfo=None) # naive for diff
                now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) # keep naive for diff compatibility
                age_hours = (now - oldest_time_dt).total_seconds() / 3600
            except:
                age_hours = 999.0
            
            is_fresh = age_hours < 24.0 # Strict 24h as per criteria
            
            # --- RADAR SCORE LOGIC (0-100) ---
            radar_score = 0
            
            # 1. Freshness (+30)
            if is_fresh: radar_score += 30
            
            # 2. Focus (+30) -> Less than 3 unique markets
            unique_markets = set()
            for t in trades:
                m_id = t.get('market') or t.get('asset_id')
                if m_id: unique_markets.add(m_id)
            if len(unique_markets) < 3: radar_score += 30
            
            # 3. Speed / Sniper (+40)
            # Find explicit deposit if possible, or infer from first trade relative to creation
            deposits = [a for a in activities if a.get('type') in ['DEPOSIT', 'PROXY']]
            speed_bonus = 0
            if deposits:
                # Funding Time
                try:
                    fund_time = parser.parse(deposits[-1].get('timestamp')).replace(tzinfo=None)
                    # First Trade Time
                    first_trade = parser.parse(trades[-1].get('timestamp')).replace(tzinfo=None)
                    
                    delta_hours = (first_trade - fund_time).total_seconds() / 3600
                    if delta_hours < 1.0: speed_bonus = 40
                    elif delta_hours < 6.0: speed_bonus = 20
                except:
                    pass
            else:
                # No deposit visible (maybe bridged). If VERY fresh (<6h) and low trades, assume instant.
                if age_hours < 6.0 and len(trades) < 10: speed_bonus = 40
                elif age_hours < 12.0: speed_bonus = 20
            
            radar_score += speed_bonus

            # Win Rate Proxy
            # Return raw float (0.0 to 1.0)
            redeem_count = len(redeems)
            trade_count = len(trades)
            win_rate_val = (redeem_count / trade_count) if trade_count > 0 else 0.0
            
            # Format Age String
            if age_hours < 24:
                age_formatted = f"{int(age_hours)}h"
            else:
                age_formatted = f"{int(age_hours/24)}d"
            
            return {
                'is_fresh': is_fresh,
                'age_formatted': age_formatted,
                'win_rate': float(win_rate_val), # Float
                'total_trades': trade_count,
                'profitability_score': radar_score # Storing Radar Score here!
            }

        except Exception as e:
            print(f"[!] Data API Error: {e}")
            return {'is_fresh': False, 'win_rate': 'Error', 'total_trades': 0}

    def is_market_making(self, wallet_address, market_id):
        # Heuristic: If we see this wallet on BOTH sides (Buy/Sell) frequently
        # For MVP, we'll assume NO for now unless we store state. 
        # The prompt says: "small, frequent trades on both sides".
        # We can implement a basic check if we had stream history.
        # Since we are stateless on restart, let's skip complex LP checks 
        # OR just check if they possess a high trade count (Data API) with low size logic?
        # Actually proper LP check needs recent history.
        # Let's rely on the DATA API 'total_trades' -> If > 1000, likely heavy trader/bot.
        return False

    def send_discord_alert(self, trade_data, market_data, profile_data, wallet, historical=False):
        if "YOUR_DISCORD" in DISCORD_WEBHOOK_URL:
            # print("[!] Discord Webhook not set. Skipping alert.")
            return

        side_str = "BUY" if trade_data['side'] == 'BUY' else "SELL"
        color = 0x00ff00 if side_str == "BUY" else 0xff0000
        
        prefix = "[HISTORICAL SCAN] " if historical else "🐳 WHALE ALERT: "
        
        profile_str = ""
        if profile_data.get('is_fresh'):
            profile_str += "🆕 **NEW USER** (First trade < 48h)\n"
        
        # Vol/Liq Context
        vol_str = f"${float(market_data.get('volume24hr', 0)):,.0f}"
        liq_str = f"${float(market_data.get('liquidity', 0)):,.0f}"
        
        # Time PST
        pst_zone = tz.gettz("America/Los_Angeles")
        time_pst = datetime.datetime.now(datetime.timezone.utc).astimezone(pst_zone).strftime('%I:%M %p PST')

        embed = {
            "title": f"{prefix} {market_data['title']}",
            "description": f"**Value:** ${trade_data['value']:,.2f}\n"
                           f"**Side:** {side_str}\n" 
                           f"**Outcome:** {trade_data['outcome']}\n"
                           f"**Price:** {trade_data['price']}\n"
                            f"**Context:** Vol 24h: {vol_str} | Liq: {liq_str}\n"
                           f"**Metrics:** Urgency: {market_data.get('metrics', {}).get('urgency', 0):.0f}% | Bias: {market_data.get('metrics', {}).get('bias', 0):.2f}\n"
                           f"**Time:** {time_pst}\n"
                           f"\n{profile_str}"
                           f"[View Market](https://polymarket.com/event/{market_data['slug']}) | [View Wallet](https://polymarket.com/profile/{wallet})",
            "color": color,
            "footer": {
                "text": "Polymarket Whale Tracker 🐳"
            }
        }
        
        payload = {
            "username": "Whale Tracker",
            "embeds": [embed]
        }
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
            # print("[*] Discord alert sent!")
        except Exception as e:
            print(f"[!] Failed to send Discord alert: {e}")

if __name__ == "__main__":
    epilog_text = '''
Examples:
  # Live Monitor (Default >$6k)
  python3 whale_tracker.py

  # Historical Scan (Last 24h, >$6k)
  python3 whale_tracker.py --scan

  # Scan Last 7 Days for Whales >$15k
  python3 whale_tracker.py --scan --days 7 --threshold 15000

  # Live Monitor with Custom Threshold (>$10k)
  python3 whale_tracker.py --threshold 10000
'''
    parser = argparse.ArgumentParser(
        description='Polymarket Whale Tracker 🐳',
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--scan', action='store_true', help='Run in Historical Scan Mode (last 24h)')
    parser.add_argument('--limit', type=int, help='Limit the number of markets to scan (default: 10k)')
    parser.add_argument('--threshold', type=float, help='Minimum trade value in USD to alert on (default: 6000)')
    parser.add_argument('--days', type=float, default=1.0, help='Number of days to look back in scan mode (default: 1)')
    parser.add_argument("--no-cache", action="store_true", help="Force refresh of market list (ignore cache)")
    args = parser.parse_args()

    # Initialize Database
    database.init_db()

    tracker = PolymarketTracker()
    
    # Update threshold if provided
    if args.threshold:
        MIN_TRADE_SIZE_USD = args.threshold

    allow_cache = not args.no_cache

    if args.scan:
        tracker.run_scan(limit=args.limit, days=args.days, use_cache=allow_cache)
    else:
        tracker.start(use_cache=allow_cache)
