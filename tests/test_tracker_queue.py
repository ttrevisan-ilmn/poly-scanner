import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import queue

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import whale_tracker
import database

class TestTrackerAsync(unittest.TestCase):
    def setUp(self):
        """Setup Tracker with mocked dependencies."""
        self.tracker = whale_tracker.PolymarketTracker()
        # Mock the queue to verify interactions
        self.tracker.event_queue = MagicMock()

    @patch('whale_tracker.PolymarketTracker.process_whale')
    def test_handle_event_worker_calls_process_whale(self, mock_process_whale):
        """Verify worker logic processes valid events."""
        # Valid Event
        event = {
            'event_type': 'last_trade_price',
            'price': '0.5',
            'size': '20000',
            'market': '0x123',
            'side': 'BUY',
            'timestamp': '1700000000000'
        }
        
        # Mock get_market_info to return something valid
        self.tracker.get_market_info = MagicMock(return_value={'title': 'Test Market', 'is_sports': False})
        
        # Call the worker handler directly (bypassing queue get)
        self.tracker._handle_event_worker(event)
        
        # Verify process_whale was called
        mock_process_whale.assert_called_once()
        
    def test_producer_puts_to_queue(self):
        """Verify the listener logic is non-blocking (puts to queue)."""
        # Restore the real queue (or a fresh mock)
        self.tracker.event_queue = MagicMock()
        
        event = {'type': 'trade'}
        self.tracker.process_trade_event(event)
        
        # Verify put called
        self.tracker.event_queue.put.assert_called_with(event)

    @patch('database.save_alert')
    def test_process_whale_saves_to_db(self, mock_save_alert):
        """Verify process_whale calls database.save_alert."""
        trade_data = {'price': 0.5, 'size': 20000, 'market_id': '0x123', 'wallet': '0xWallet'}
        market_data = {'title': 'Test', 'slug': 'test', 'volume24hr': 0, 'liquidity': 0}
        
        # Call process_whale (Testing the logic inside it)
        # Note: whale_tracker.MIN_TRADE_SIZE_USD default might be 6000. 10000 is safe.
        self.tracker.process_whale(trade_data, market_data)
        
        # Verify DB call
        mock_save_alert.assert_called_once()

if __name__ == '__main__':
    unittest.main()
