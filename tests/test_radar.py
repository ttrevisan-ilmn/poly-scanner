import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import datetime
from dateutil import tz

# Add parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import whale_tracker

class TestRadarScore(unittest.TestCase):
    def setUp(self):
        self.tracker = whale_tracker.PolymarketTracker()

    @patch('requests.get')
    def test_perfect_sniper_score(self, mock_get):
        """Test a perfect sniper trade (+30 Fresh, +30 Focused, +40 Fast)."""
        now = datetime.datetime.utcnow()
        # Created 1 hour ago
        creation_time = now - datetime.timedelta(hours=1)
        # First trade 10 mins after creation
        trade_time = creation_time + datetime.timedelta(minutes=10)
        
        # Mock Activity Response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            # Recent Trade (Trade Time)
            {'type': 'TRADE', 'timestamp': trade_time.isoformat(), 'market': '0xMarket1'},
            # Funding (Creation Time)
            {'type': 'DEPOSIT', 'timestamp': creation_time.isoformat()}
        ]
        mock_get.return_value = mock_resp
        
        result = self.tracker.analyze_wallet('0xSniper')
        
        # Fresh (<24h age): +30
        # Focused (1 market): +30
        # Fast (10min delta): +40
        # Total: 100
        self.assertEqual(result['profitability_score'], 100)
        self.assertTrue(result['is_fresh'])

    @patch('requests.get')
    def test_slow_fresh_wallet(self, mock_get):
        """Test a fresh wallet that took too long to trade."""
        now = datetime.datetime.utcnow()
        creation_time = now - datetime.timedelta(hours=20)
        # Trade 10 hours after funding (Slow)
        trade_time = creation_time + datetime.timedelta(hours=10)
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {'type': 'TRADE', 'timestamp': trade_time.isoformat(), 'market': '0xMarket1'},
            {'type': 'DEPOSIT', 'timestamp': creation_time.isoformat()}
        ]
        mock_get.return_value = mock_resp
        
        result = self.tracker.analyze_wallet('0xSlow')
        
        # Fresh (<24h): +30
        # Focused (1 mkt): +30
        # Speed (>6h): +0
        # Total: 60
        self.assertEqual(result['profitability_score'], 60)

    @patch('requests.get')
    def test_old_wallet(self, mock_get):
        """Test an old wallet (Age > 24h)."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        creation_time = now - datetime.timedelta(hours=48)
        trade_time = now 
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Must provide OLD activity to prove age
        mock_resp.json.return_value = [
            {'type': 'TRADE', 'timestamp': trade_time.isoformat()},
            {'type': 'TRADE', 'timestamp': creation_time.isoformat()}
        ]
        mock_get.return_value = mock_resp
        
        result = self.tracker.analyze_wallet('0xOld')
        
        # Fresh: 0 (Age 48h)
        # Focused: +30 (1 unique market inferred or None -> None ignored)
        # Need to ensure unique markets logic works with None
        # Logic: m_id = t.get('market')
        # Here mocks have no market. Unique = 0 < 3 -> +30.
        # Speed: Age 48h > 12 -> 0.
        # Total: 30
        self.assertEqual(result['profitability_score'], 30)

if __name__ == '__main__':
    unittest.main()
