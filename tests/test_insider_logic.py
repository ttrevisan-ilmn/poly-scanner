import pandas as pd
import unittest

# Simulation of st.session_state.scan_results
mock_scan_results = [
    {
        "Wallet": "0x123",
        "Market": "Will BTC hit 100k?",
        "Value": 10000,
        "WC/TX%": 4.5,         # Insider (<5)
        "Trade Conc.": 80.0,   # High Focus (>50)
        "Radar Score": 90,     # Perfect Score (>80)
        "Link": "http://..."
    },
    {
        "Wallet": "0x456",
        "Market": "Will ETH hit 10k?",
        "Value": 5000,
        "WC/TX%": 20.0,        # Normal user
        "Trade Conc.": 10.0,   # Low Focus
        "Radar Score": 40,     # Low Score
        "Link": "http://..."
    },
    {
        "Wallet": "0x789",
        "Market": "Election Winner",
        "Value": 50000,
        "WC/TX%": 2.0,         # Insider
        "Trade Conc.": 40.0,   # But low concentration (<50)
        "Radar Score": 85,     # Good score
        "Link": "http://..."
    }
]

class TestInsiderLogic(unittest.TestCase):
    def test_insider_filtering(self):
        df_insider = pd.DataFrame(mock_scan_results)

        # Filter settings (Defaults)
        wc_tx_filter = 5
        conc_filter = 50
        score_filter = 80

        # Apply Logic from app.py
        filtered_df = df_insider[
            (df_insider["WC/TX%"] <= wc_tx_filter) &
            (df_insider["Trade Conc."] >= conc_filter) &
            (df_insider["Radar Score"] >= score_filter)
        ]

        # We expect only the first wallet (0x123) to pass
        self.assertEqual(len(filtered_df), 1)
        self.assertEqual(filtered_df.iloc[0]["Wallet"], "0x123")

        print("✅ Filter Logic Test Passed!")
        print(filtered_df[["Wallet", "WC/TX%", "Trade Conc.", "Radar Score"]])

if __name__ == "__main__":
    unittest.main()
