import unittest
import sys
import os
import sqlite3
import time

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database

class TestDatabasePersistence(unittest.TestCase):
    def setUp(self):
        """Setup test database (separate file)."""
        self.test_db = "test_whale_alerts.db"
        
        # Override database.DB_NAME directly
        # Note: database.DB_NAME is a string in the module. 
        # But get_connection reads it.
        self.original_db_name = database.DB_NAME
        database.DB_NAME = os.path.join(os.path.dirname(self.original_db_name), self.test_db)
        
        # Clean start
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)
            
        # Initialize Schema
        database.init_db()

    def tearDown(self):
        """Clean up test database."""
        if os.path.exists(database.DB_NAME):
            os.remove(database.DB_NAME)
        database.DB_NAME = self.original_db_name

    def test_upsert_market(self):
        """Test market metadata insertion and update."""
        data = {
            'market_id': '0x123',
            'question': 'Will Bitcoin hit 100k?',
            'slug': 'btc-100k',
            'volume': 1000.0,
            'liquidity': 500.0,
        }
        database.upsert_market(data)
        
        # Verify
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM markets WHERE market_id='0x123'")
        row = c.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 'Will Bitcoin hit 100k?') # question
        
    def test_save_alert_and_deduplication(self):
        """Test alert persistence and unique constraint."""
        ts = time.time()
        alert = {
            'market_id': '0x123',
            'wallet': '0xWalletABC',
            'value': 5000.0,
            'outcome': 'Yes',
            'side': 'BUY',
            'price': 0.5,
            'asset_id': '123456',
            'timestamp': ts
        }
        
        # 1. First Save
        database.save_alert(alert)
        
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT count(*) FROM trade_alerts")
        count1 = c.fetchone()[0]
        conn.close()
        self.assertEqual(count1, 1, "Should have 1 alert")
        
        # 2. Duplicate Save (Same data)
        database.save_alert(alert)
        
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT count(*) FROM trade_alerts")
        count2 = c.fetchone()[0]
        conn.close()
        self.assertEqual(count2, 1, "Should NOT duplicate identical alert")

    def test_persistence_check(self):
        """Verify data persists across connections."""
        database.upsert_wallet({'address': '0xTest', 'win_rate': 0.6})
        
        # Simulate app restart (new connection)
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT win_rate FROM wallets WHERE address='0xTest'")
        row = c.fetchone()
        conn.close()
        
        self.assertEqual(row[0], 0.6)

    def test_upsert_wallet_resilience(self):
        """Regression Test: Verify upsert handles 'N/A' strings safely."""
        # Cause of "could not convert string to float" error
        bad_data = {
            'address': '0xBadData',
            'win_rate': 'N/A', # This should become 0.0
            'total_trades': 5,
            'is_fresh': True,
            'profitability_score': 'N/A' # Should become 0.0
        }
        
        # Should NOT raise ValueError
        try:
            database.upsert_wallet(bad_data)
        except ValueError:
            self.fail("upsert_wallet raised ValueError on 'N/A' input")
            
        # Verify it saved as 0.0
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT win_rate, profitability_score FROM wallets WHERE address='0xBadData'")
        row = c.fetchone()
        conn.close()
        
        self.assertEqual(row[0], 0.0)
        self.assertEqual(row[1], 0.0)

if __name__ == '__main__':
    unittest.main()
