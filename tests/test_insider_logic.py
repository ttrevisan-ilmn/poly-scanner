"""
Test script for Insider Finder filtering logic.
Verifies that the pandas filtering correctly identifies insider candidates.
"""

import pandas as pd

# Create dummy scan results resembling real data
dummy_results = [
    # Perfect Insider: WC/TX 2%, Conc 80%, Radar 95
    {"Time": "Jan 05, 01:00 PM", "Market": "https://polymarket.com/event/test1", "Value": 10000, 
     "Wallet": "0xABCD1234", "WC/TX%": 2, "Trade Conc.": 80, "Radar Score": 95, "Urgency": 90, "Age": "3h"},
    
    # Good Insider: WC/TX 4%, Conc 60%, Radar 85
    {"Time": "Jan 05, 02:00 PM", "Market": "https://polymarket.com/event/test2", "Value": 8000,
     "Wallet": "0xDEF5678", "WC/TX%": 4, "Trade Conc.": 60, "Radar Score": 85, "Urgency": 75, "Age": "5h"},
    
    # Not Insider: WC/TX 50%, Conc 20%, Radar 30 (Regular trader)
    {"Time": "Jan 05, 03:00 PM", "Market": "https://polymarket.com/event/test3", "Value": 7000,
     "Wallet": "0x1111222", "WC/TX%": 50, "Trade Conc.": 20, "Radar Score": 30, "Urgency": 45, "Age": "2d"},
    
    # Edge Case: High Radar but high WC/TX (old wallet)
    {"Time": "Jan 05, 04:00 PM", "Market": "https://polymarket.com/event/test4", "Value": 9000,
     "Wallet": "0x3333444", "WC/TX%": 80, "Trade Conc.": 70, "Radar Score": 85, "Urgency": 60, "Age": "10d"},
    
    # Edge Case: Low WC/TX but low Radar (bot maybe)
    {"Time": "Jan 05, 05:00 PM", "Market": "https://polymarket.com/event/test5", "Value": 6000,
     "Wallet": "0x5555666", "WC/TX%": 3, "Trade Conc.": 55, "Radar Score": 40, "Urgency": 50, "Age": "1h"},
]

# Convert to DataFrame
df_scan = pd.DataFrame(dummy_results)

print("=" * 80)
print("INSIDER FINDER FILTER TEST")
print("=" * 80)
print(f"\nTotal dummy records: {len(df_scan)}")
print("\n--- Dummy Data Overview ---")
print(df_scan[['Wallet', 'WC/TX%', 'Trade Conc.', 'Radar Score']])

# Apply Insider Finder filters (defaults: WC/TX ≤ 5, Conc ≥ 50, Radar ≥ 80)
max_wc_tx = 5
min_conc = 50
min_radar = 80

filtered = df_scan[
    (df_scan['WC/TX%'] <= max_wc_tx) &
    (df_scan['Trade Conc.'] >= min_conc) &
    (df_scan['Radar Score'] >= min_radar)
].copy()

print("\n" + "=" * 80)
print(f"FILTER CRITERIA: WC/TX% ≤ {max_wc_tx}, Conc ≥ {min_conc}, Radar ≥ {min_radar}")
print("=" * 80)
print(f"\nFiltered Results: {len(filtered)} matches\n")

if len(filtered) > 0:
    print("--- Insider Candidates ---")
    print(filtered[['Wallet', 'Value', 'WC/TX%', 'Trade Conc.', 'Radar Score', 'Age']])
    
    # Verify expected results
    expected_wallets = ["0xABCD1234", "0xDEF5678"]  # Only the first two should pass
    actual_wallets = filtered['Wallet'].tolist()
    
    print("\n" + "=" * 80)
    print("VALIDATION")
    print("=" * 80)
    print(f"Expected wallets: {expected_wallets}")
    print(f"Actual wallets:   {actual_wallets}")
    
    if set(actual_wallets) == set(expected_wallets):
        print("\n✅ PASS: Filter logic is working correctly!")
    else:
        print("\n❌ FAIL: Filter logic produced unexpected results!")
        exit(1)
else:
    print("❌ FAIL: No results found (expected 2 matches)")
    exit(1)

print("\n" + "=" * 80)
print("All tests passed! 🎯")
print("=" * 80)
