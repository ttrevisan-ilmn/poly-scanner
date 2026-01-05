import sqlite3
import time
import datetime
import json
import os

# Ensure DB is created in the same directory as this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "whale_alerts.db")

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    # Enable WAL mode for concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    """Initialize the database schema with normalized tables."""
    conn = get_connection()
    c = conn.cursor()
    
    # Validating Schema (No Drop)

    # DROP TABLES removed to prevent data loss on restart
    
    # 1. Markets Table (Metadata)
    c.execute('''
        CREATE TABLE IF NOT EXISTS markets (
            market_id TEXT PRIMARY KEY,
            question TEXT,
            slug TEXT,
            volume REAL,
            liquidity REAL,
            end_date TEXT,
            description TEXT,
            last_updated REAL
        )
    ''')

    # 2. Wallets Table (Smart Money Stats)
    c.execute('''
        CREATE TABLE IF NOT EXISTS wallets (
            address TEXT PRIMARY KEY,
            win_rate REAL, 
            total_trades INTEGER,
            is_fresh INTEGER,
            profitability_score REAL,
            last_seen REAL
        )
    ''')

    # 3. Alerts Table (The Trade Events)
    # Linked to markets and wallets
    # Unique constraint on (market_id, timestamp, value, wallet) to prevent dupes
    # Timestamp is now INTEGER (milliseconds) for precision
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,
            market_id TEXT,
            wallet_address TEXT,
            value REAL,
            outcome TEXT,
            side TEXT,
            price REAL,
            asset_id TEXT,
            FOREIGN KEY(market_id) REFERENCES markets(market_id),
            FOREIGN KEY(wallet_address) REFERENCES wallets(address),
            UNIQUE(market_id, timestamp, value, wallet_address)
        )
    ''')
    
    # INDICES for Performance
    c.execute('CREATE INDEX IF NOT EXISTS idx_alerts_ts ON trade_alerts(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_alerts_val ON trade_alerts(value)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_wallets_score ON wallets(profitability_score)')

    conn.commit()
    conn.close()

def upsert_market(data):
    """
    Insert or Update market metadata.
    data: {market_id, question, slug, volume, liquidity, end_date, description}
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO markets (market_id, question, slug, volume, liquidity, end_date, description, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id) DO UPDATE SET
                volume=excluded.volume,
                liquidity=excluded.liquidity,
                last_updated=excluded.last_updated,
                end_date=excluded.end_date,
                description=excluded.description
        ''', (
            data['market_id'],
            data.get('question'),
            data.get('slug'),
            float(data.get('volume', 0)),
            float(data.get('liquidity', 0)),
            data.get('end_date'),
            data.get('description'),
            time.time()
        ))
        conn.commit()
    except Exception as e:
        print(f"[!] Market Upsert Error: {e}")
    finally:
        conn.close()

def upsert_wallet(data):
    """
    Insert or Update wallet stats.
    data: {address, win_rate, total_trades, is_fresh, profitability_score}
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO wallets (address, win_rate, total_trades, is_fresh, profitability_score, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                win_rate=excluded.win_rate,
                total_trades=excluded.total_trades,
                is_fresh=excluded.is_fresh,
                last_seen=excluded.last_seen
        ''', (
            data['address'],
            float(data.get('win_rate', 0)), # Expecting 0.55 now
            int(data.get('total_trades', 0)),
            1 if data.get('is_fresh') else 0,
            float(data.get('profitability_score', 0)),
            time.time()
        ))
        conn.commit()
    except Exception as e:
        print(f"[!] Wallet Upsert Error: {e}")
    finally:
        conn.close()

def save_alert(data):
    """
    Save trade alert event.
    data: {timestamp, market_id, wallet, value, outcome, side, price, asset_id}
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        # Timestamp: Convert to int (milliseconds) if float
        ts = data.get('timestamp', time.time())
        ts_ms = int(ts * 1000) if ts < 100000000000 else int(ts) # Heuristic for seconds vs ms
        
        with open("db_debug_app.log", "a") as f: 
            f.write(f"Saving: {ts_ms} | Mkt: {data.get('market_id')} | Val: {data.get('value')}\n")
        
        c.execute('''
            INSERT INTO trade_alerts 
            (timestamp, market_id, wallet_address, value, outcome, side, price, asset_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ts_ms,
            data.get('market_id'),
            data.get('wallet'),
            float(data.get('value', 0)),
            str(data.get('outcome')),
            data.get('side'),
            float(data.get('price', 0)),
            data.get('asset_id')
        ))
        conn.commit()
    except sqlite3.IntegrityError as e:
         pass # Ignore duplicates silently now that debug is done
    except Exception as e:
        print(f"[!] Database Error: {e}")
    finally:
        conn.close()

def upsert_market(data):
    """
    Insert or Update market metadata.
    data: {market_id, question, slug, volume, liquidity, end_date, description}
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO markets (market_id, question, slug, volume, liquidity, end_date, description, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market_id) DO UPDATE SET
                volume=excluded.volume,
                liquidity=excluded.liquidity,
                last_updated=excluded.last_updated,
                end_date=excluded.end_date,
                description=excluded.description
        ''', (
            data['market_id'],
            data.get('question'),
            data.get('slug'),
            float(data.get('volume', 0)),
            float(data.get('liquidity', 0)),
            data.get('end_date'),
            data.get('description'),
            time.time()
        ))
        conn.commit()
    except Exception as e:
        with open("db_debug.log", "a") as f: f.write(f"MARKET ERROR: {e}\n")
        print(f"[!] Market Upsert Error: {e}")
    finally:
        conn.close()

def upsert_wallet(data):
    """
    Insert or Update wallet stats.
    data: {address, win_rate, total_trades, is_fresh, profitability_score}
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO wallets (address, win_rate, total_trades, is_fresh, profitability_score, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                win_rate=excluded.win_rate,
                total_trades=excluded.total_trades,
                is_fresh=excluded.is_fresh,
                last_seen=excluded.last_seen
        ''', (
            data['address'],
            float(data.get('win_rate')) if isinstance(data.get('win_rate'), (int, float)) and data.get('win_rate') != 'N/A' else 0.0,
            int(data.get('total_trades', 0)),
            1 if data.get('is_fresh') else 0,
            float(data.get('profitability_score', 0)) if isinstance(data.get('profitability_score'), (int, float)) else 0.0,
            time.time()
        ))
        conn.commit()
    except Exception as e:
        print(f"[!] Wallet Upsert Error: {e}")
    finally:
        conn.close()

def save_alert(data):
    """
    Save a whale alert (Trade Event) to the database.
    Ignores duplicates based on (market_id, timestamp, value, wallet).
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        # Timestamp: Convert to int (milliseconds) if float
        ts = data.get('timestamp', time.time())
        ts_ms = int(ts * 1000) if ts < 100000000000 else int(ts) # Heuristic for seconds vs ms
        
        with open("db_debug.log", "a") as f: f.write(f"Saving Alert: {ts_ms}, {data.get('market_id')}\n")
        print(f"[DEBUG] Saving Alert: {ts_ms}, {data.get('market_id')}, {data.get('value')}")
        c.execute('''
            INSERT INTO trade_alerts 
            (timestamp, market_id, wallet_address, value, outcome, side, price, asset_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ts_ms,
            data.get('market_id'),
            data.get('wallet'),
            float(data.get('value', 0)),
            str(data.get('outcome')),
            data.get('side'),
            float(data.get('price', 0)),
            data.get('asset_id')
        ))
        conn.commit()
    except sqlite3.IntegrityError as e:
         with open("db_debug.log", "a") as f: f.write(f"ALERT INTEGRITY ERROR: {e}\n")
         print(f"[!] DB Integrity Error (Constraint Failed): {e}")
    except Exception as e:
        with open("db_debug.log", "a") as f: f.write(f"ALERT ERROR: {e}\n")
        print(f"[!] Database Error: {e}")
    finally:
        conn.close()

def get_recent_alerts(limit=100, days=None):
    """Fetch joined alerts with market and wallet info."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    query = '''
        SELECT 
            t.timestamp, t.value, t.side, t.outcome, t.price,
            m.question as market_name, m.slug, m.end_date,
            w.address as wallet, w.is_fresh, w.win_rate
        FROM trade_alerts t
        JOIN markets m ON t.market_id = m.market_id
        LEFT JOIN wallets w ON t.wallet_address = w.address
    '''
    params = []
    
    if days:
        cutoff = (time.time() - (days * 86400)) * 1000 # Convert to MS
        query += " WHERE t.timestamp > ?"
        params.append(cutoff)
        
    query += " ORDER BY t.timestamp DESC LIMIT ?"
    params.append(limit)
    
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_top_markets(days=7, limit=10):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    cutoff = (time.time() - (days * 86400)) * 1000 # Convert to MS
    query = '''
        SELECT m.question as market_name, SUM(t.value) as total_volume, COUNT(*) as alert_count, m.slug
        FROM trade_alerts t
        JOIN markets m ON t.market_id = m.market_id
        WHERE t.timestamp > ?
        GROUP BY m.question
        ORDER BY total_volume DESC
        LIMIT ?
    '''
    c.execute(query, (cutoff, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_smart_whales(min_trades=3):
    """Return wallets with high win rate or high volume."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Simple query for now, can be complex later
    query = '''
        SELECT * FROM wallets 
        WHERE total_trades >= ? 
        ORDER BY last_seen DESC 
        LIMIT 50
    '''
    c.execute(query, (min_trades,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Auto-init removed to prevent side-effects. Call explicitely.
