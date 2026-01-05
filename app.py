import streamlit as st
import pandas as pd
import plotly.express as px
import threading
import time
import datetime
import whale_tracker
import database
from dateutil import tz
import concurrent.futures

# --- Configuration & State ---
st.set_page_config(
    page_title="Polymarket Whale Tracker",
    page_icon="🐳",
    layout="wide"
)

# Ensure Database Exists
database.init_db()

# Initialize Session State
if 'live_whales' not in st.session_state:
    st.session_state.live_whales = []
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = []

# --- Custom Tracker Class ---
class StreamlitTracker(whale_tracker.PolymarketTracker):
    """
    Subclass to override valid methods for Streamlit integration.
    """
    def send_discord_alert(self, trade_data, market_data, profile_data, wallet, historical=False):
        # Override to capture data for Streamlit AND send Discord alert
        
        # 1. Capture for UI
        # Format: Jan 05, 06:58 PM
        timestamp = datetime.datetime.now().strftime('%b %d, %I:%M %p')
        item = {
            "Time": timestamp,
            "Market": market_data['title'],
            "Value": trade_data['value'],
            "Side": trade_data['side'],
            "Outcome": trade_data['outcome'],
            "Price": trade_data['price'],
            "Link": f"https://polymarket.com/event/{market_data['slug']}",
            "New User": "Yes" if profile_data.get('is_fresh') else "No",
            "Age": profile_data.get('age_formatted', 'N/A'),
            "Urgency": market_data.get('metrics', {}).get('urgency', 0),
            "Bias": market_data.get('metrics', {}).get('bias', 0),
            "Liq/Vol": market_data.get('metrics', {}).get('liq_vol_ratio', 0),
            "WC/TX%": trade_data.get('wc_tx_pct', 100),
            "Trade Conc.": trade_data.get('trade_concentration', 0)
        }
        
        # Append to session state (thread-safeish in Streamlit context usually requires care, 
        # but appending to list is atomic enough for display)
        # Note: In Streamlit, modifying logic from a thread doesn't auto-rerun. We use a poller.
        st.session_state.live_whales.insert(0, item)
        # Keep list manageable
        if len(st.session_state.live_whales) > 50:
            st.session_state.live_whales.pop()

        # 2. Call Original for Discord
        super().send_discord_alert(trade_data, market_data, profile_data, wallet, historical)

# --- Singleton Runner ---
# We need a singleton-like instance for the live runner to persist across reruns if started
if 'tracker_instance' not in st.session_state:
    st.session_state.tracker_instance = StreamlitTracker()
    st.session_state.tracker_thread = None

# --- UI Layout ---

# --- UI Layout ---

# Sidebar
with st.sidebar:
    st.title("🐳 Config")
    
    st.subheader("Filters")
    # 1. Threshold
    threshold = st.slider(
        "Min Trade Size ($)",
        min_value=1000,
        max_value=100000,
        value=int(whale_tracker.MIN_TRADE_SIZE_USD),
        step=1000,
        help="Only show trades larger than this value."
    )
    # 2. Max Markets
    limit_markets = st.number_input(
        "Max Markets to Scan", 
        value=2000, 
        step=500,
        help="How many top active markets to check."
    )
    # 3. Days Back
    days_back = st.number_input(
        "Lookback (Days)", 
        value=1, 
        min_value=1, 
        max_value=30,
        help="How far back to check for the Historical Scan."
    )
    # 4. Sports Filter
    exclude_sports = st.checkbox(
        "Exclude Sports", 
        value=True,
        help="Ignore sports markets (NBA, NFL, etc)."
    )
    
    st.divider()
    
    # Discord Webhook
    webhook_url = st.text_input(
        "Discord Webhook URL", 
        value=whale_tracker.DISCORD_WEBHOOK_URL,
        type="password"
    )
    
    # Update Globals
    whale_tracker.MIN_TRADE_SIZE_USD = float(threshold)
    whale_tracker.DISCORD_WEBHOOK_URL = webhook_url
    
    st.caption("v1.1.0 Beta")

st.title("Polymarket Whale Tracker 🐳")

tab_live, tab_scan, tab_db, tab_smart, tab_insider = st.tabs(["📡 Live Monitor", "📜 Historical Scan", "💾 Database", "🧠 Smart Money", "🕵️ Insider Finder"])

# --- TAB 1: LIVE MONITOR ---
with tab_live:
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Start Monitor" if not st.session_state.is_running else "Running...", disabled=st.session_state.is_running):
            if not st.session_state.is_running:
                st.session_state.is_running = True
                
                def run_live():
                    try:
                        st.session_state.tracker_instance.start()
                    except Exception as e:
                        print(f"Thread Error: {e}")
                        
                t = threading.Thread(target=run_live, daemon=True)
                t.start()
                st.session_state.tracker_thread = t
                st.rerun()

    with col2:
        if st.session_state.is_running:
            st.success(f"Listening for Whales > ${threshold:,.0f}...")
        else:
            st.info("Monitor is stopped. Click Start to connect.")

    st.subheader("Live Feed")
    
    if st.session_state.is_running:
        if st.button("🔄 Refresh Feed"):
            st.rerun()
            
    # Display Cards (Apply Filters Dynamically)
    if st.session_state.live_whales:
        for whale in st.session_state.live_whales:
            # Filter View
            if whale['Value'] < threshold:
                continue
                
            # Color logic
            color = "green" if whale['Side'] == "BUY" else "red"
            emoji = "🟢" if whale['Side'] == "BUY" else "🔴"
            
            with st.container():
                cols = st.columns([2, 1, 2, 4])
                # Beautify Time: currently HH:MM:SS, let's keep it or make it fuller? 
                # User asked for "Jan 05 06:58 PM" style. 
                # Live whales usually just have time, let's assume today.
                cols[0].write(f"**{whale['Time']}**") 
                cols[1].write(f"{emoji} **{whale['Side']}**")
                cols[2].write(f"**${whale['Value']:,.0f}**")
                cols[3].markdown(f"[{whale['Market']}]({whale['Link']})")
                
                with st.expander(f"Details: {whale['Outcome']} @ {whale['Price']}"):
                    st.write(f"Outcome: {whale['Outcome']}")
                    st.write(f"User Age: {whale.get('Age', 'N/A')} (Fresh: {whale['New User']})")
                    st.write(f"🔥 Urgency: {whale.get('Urgency', 0):.0f}% | ⚖️ Bias: {whale.get('Bias', 0):.2f} | 🌊 Liq/Vol: {whale.get('Liq/Vol', 0):.2f}")
                    # Insider Metrics
                    wc_tx = whale.get('WC/TX%', 100)
                    trade_conc = whale.get('Trade Conc.', 0)
                    insider_flag = "🚨 INSTANT ACTION!" if wc_tx < 5 else ""
                    st.write(f"⏱️ WC/TX: {wc_tx:.1f}% {insider_flag} | 🎯 Focus: {trade_conc:.0f}%")
                st.markdown("---")
    else:
        st.write("No whales found yet. Waiting for big splashes... 🌊")


# --- TAB 2: HISTORICAL SCAN ---
with tab_scan:
    st.subheader("Historical Market Scanner")
    st.markdown(f"**Settings:** Last {days_back} Days | Top {limit_markets} Markets | > ${threshold:,.0f}")
    
    if st.button("🚀 Run Historical Scan"):
        tracker = whale_tracker.PolymarketTracker()
        
        with st.status("Scanning Markets...", expanded=True) as status:
            st.write("Fetching active markets...")
            markets = tracker.fetch_active_markets(limit_override=limit_markets)
            
            # Helper to check sports tags (reusing logic)
            def is_sports_market(m):
                tags = [t.lower() for t in m.get('tags', [])]
                cat = m.get('category', '').lower()
                return 'sports' in tags or 'nba' in tags or 'nfl' in tags or 'soccer' in tags or cat == 'sports'

            if exclude_sports:
                markets = [m for m in markets if not is_sports_market(m)]
                
            st.write(f"Scanning {len(markets)} markets for trades > ${threshold:,.0f}...")
            
            # Re-implement scan logic locally to capture results for Dataframe
            found_whales = []
            scan_progress = st.progress(0)
            
            # Logic unified with whale_tracker.py to ensure persistence
            def process_market(market):
                try:
                    market_id = market.get('conditionId') or market.get('id')
                    trades = tracker.fetch_recent_trades(market_id)
                    results = []
                    for trade in trades:
                        # Prepare data for Unified Processor
                        # We need to construct 'trade_data' and 'market_data' matching process_whale expects
                        
                        # Size check at source to save processing (though process_whale checks too)
                        t_size = float(trade.get('size', 0))
                        t_price = float(trade.get('price', 0))
                        if (t_size * t_price) < threshold: continue

                        t_ts = float(trade.get('timestamp'))
                        # Fix timestamp scaling if needed
                        if t_ts > 10000000000: t_ts /= 1000
                        
                        # Time Window Check
                        if (time.time() - t_ts) > (days_back * 86400): continue

                        # Prepare Trade Data Payload
                        trade_payload = {
                            'market_id': market_id,
                            'price': t_price,
                            'size': t_size,
                            'side': trade.get('side'),
                            'timestamp': t_ts, # Use corrected float seconds
                            'outcome': trade.get('outcome'),
                            'outcome_label': None, # API usually provides outcome
                            'asset_id': trade.get('asset_id'),
                            'wallet': trade.get('taker_address') or trade.get('owner')
                        }

                        # Prepare Market Data (Normalize Keys)
                        # Gamma API uses 'question', process_whale expects 'title'
                        market_payload = market.copy()
                        if 'question' in market and 'title' not in market:
                            market_payload['title'] = market['question']
                        
                        # Ensure other keys exist to prevent errors
                        if 'volume24hr' not in market_payload: market_payload['volume24hr'] = market.get('volume', 0)
                        if 'liquidity' not in market_payload: market_payload['liquidity'] = market.get('liquidityNum', 0)

                        # Call the Unified Processor (Handles DB Save!)
                        # We pass historical=True so it doesn't print to console/discord
                        # We pass timestamp_override because it's a historical trade
                        processed_item = tracker.process_whale(
                            trade_payload, 
                            market_payload, 
                            historical=True, 
                            timestamp_override=t_ts
                        )

                        if processed_item:
                            # Map returning lowercase keys to UI Capitalized keys
                            # process_whale returns: time, market, value, outcome, wallet, fresh, side, price...
                            
                            results.append({
                                "Time": processed_item['time'],
                                "Value": processed_item['value'],
                                "Market": processed_item['market'],
                                "Outcome": processed_item['outcome'],
                                "Side": processed_item['side'],
                                "Wallet": processed_item['wallet'],
                                "Vol 24h": processed_item.get('vol_24h', 0),
                                "Liquidity": processed_item.get('liquidity', 0),
                                "_ts": processed_item['raw_timestamp'],
                                "Link": f"https://polymarket.com/event/{processed_item.get('slug')}",
                                "New User": "Yes" if processed_item['profile'].get('is_fresh') else "No",
                                "Age": processed_item['age'],
                                "Urgency": processed_item.get('urgency', 0),
                                "Bias": processed_item.get('bias', 0),
                                "Liq/Vol": processed_item.get('liq_vol_ratio', 0),
                                "WC/TX%": processed_item.get('wc_tx_pct', 100),
                                "Trade Conc.": processed_item.get('trade_concentration', 0),
                                "Radar Score": processed_item['profile'].get('profitability_score', 0)
                            })
                            
                    return results
                except Exception as e:
                    # print(f"Error in app scan: {e}")
                    return []

            # Parallel Execution
            completed = 0
            all_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = {executor.submit(process_market, m): m for m in markets}
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res:
                        all_results.extend(res)
                    completed += 1
                    if completed % 10 == 0:
                        scan_progress.progress(completed / len(markets))

            st.session_state.scan_results = all_results
            status.update(label="Scan Complete!", state="complete", expanded=False)
            
    # Results Display
    if st.session_state.scan_results:
        df = pd.DataFrame(st.session_state.scan_results)
        
        # Sort by Time (Newest first) or Value? Usually Value is fun, but Time is practical.
        # User asked for largest trades chart, maybe table by time?
        # Sort by Time (Newest first) or Value
        if "_ts" in df.columns:
            df = df.sort_values(by="_ts", ascending=False)
        else:
            # Fallback for old session state
            df = df.sort_values(by="Value", ascending=False)
        
        # Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("Whales Found", len(df))
        m2.metric("Total Volume", f"${df['Value'].sum():,.0f}")
        m3.metric("Top Whale", f"${df['Value'].max():,.0f}")
        
        # Chart (Top 10 by Value)
        st.subheader("Largest Trades")
        top_df = df.nlargest(10, "Value")
        fig = px.bar(top_df, x="Value", y="Market", orientation='h', color="Side", 
                     color_discrete_map={"BUY": "green", "SELL": "red"}, text_auto='.2s',
                     hover_data=["Outcome", "Time"])
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, width="stretch")
        
        # Table
        st.subheader("Detailed Logs")
        
        # Drop internal timestamp
        if "_ts" in df.columns:
            display_df = df.drop(columns=["_ts"])
        else:
            display_df = df
        
        st.dataframe(
            display_df,
            column_config={
                "Value": st.column_config.NumberColumn(format="$%d"),
                "Vol 24h": st.column_config.NumberColumn(format="$%d"),
                "Liquidity": st.column_config.NumberColumn(format="$%d"),
                "Market": st.column_config.LinkColumn("Market", display_text=".*"),
                "Age": st.column_config.TextColumn("Age"),
                "Urgency": st.column_config.ProgressColumn("Urgency 🔥", min_value=0, max_value=100, format="%.0f"),
                "Bias": st.column_config.NumberColumn("Bias ⚖️", format="%.2f"),
                "Liq/Vol": st.column_config.NumberColumn("Liq/Vol 🌊", format="%.2f"),
                "WC/TX%": st.column_config.NumberColumn("WC/TX% ⏱️", format="%.1f%%", help="Wallet age when trade executed. <5% = Instant action!"),
                "Trade Conc.": st.column_config.ProgressColumn("Focus 🎯", min_value=0, max_value=100, format="%.0f%%", help="% of user's total volume in this market"),
            },
            width='stretch',
            hide_index=True
        )

# --- TAB 3: DATABASE ---
with tab_db:
    st.subheader("Persisted Whale Data")
    
    col_d1, col_d2 = st.columns([1, 3])
    with col_d1:
        db_days = st.number_input("History (Days)", value=7, min_value=1, max_value=365, key="db_days")
        if st.button("🔄 Reload Data"):
            st.rerun()
            
    with col_d2:
        st.info("This data is persisted in `whale_alerts.db` from previous scans and live monitoring.")

    # Fetch Data
    try:
        data = database.get_recent_alerts(limit=5000, days=db_days)
        if data:
            df_db = pd.DataFrame(data)
            
            # Convert timestamp (DB now stores Milliseconds)
            df_db['datetime'] = pd.to_datetime(df_db['timestamp'], unit='ms')
            # Adjust to PST
            df_db['time_pst'] = df_db['datetime'].dt.tz_localize('UTC').dt.tz_convert('America/Los_Angeles')
            df_db['Time'] = df_db['time_pst'].dt.strftime('%b %d, %I:%M %p')
            
            # Metrics
            total_vol = df_db['value'].sum()
            unique_mkts = df_db['market_name'].nunique()
            top_whale_val = df_db['value'].max()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Alerts", len(df_db))
            m2.metric("Unique Markets", unique_mkts)
            m3.metric("Largest Record", f"${top_whale_val:,.0f}")
            
            # Charts
            st.markdown("### Top Markets by Volume")
            # Group by Market name
            top_mkts = df_db.groupby('market_name')['value'].sum().reset_index().sort_values('value', ascending=False).head(10)
            
            fig_db = px.bar(top_mkts, x='value', y='market_name', orientation='h', text_auto='.2s')
            fig_db.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Total Volume (USD)", yaxis_title=None)
            st.plotly_chart(fig_db, width="stretch")
            
            # Table
            st.markdown("### Recent Alerts")
            
            # Add clickable links - put URL in Market column itself
            df_db['Market'] = df_db.apply(lambda row: f"https://polymarket.com/event/{row['slug']}", axis=1)
            
            # Formatting for display
            display_db = df_db[['Time', 'value', 'side', 'outcome', 'price', 'Market', 'wallet']].copy()
            display_db.columns = ['Time', 'Value', 'Side', 'Outcome', 'Price', 'Market', 'Wallet']
            
            st.dataframe(
                display_db,
                column_config={
                    "Value": st.column_config.NumberColumn(format="$%d"),
                    "Price": st.column_config.NumberColumn(format="%.2f"),
                    "Market": st.column_config.LinkColumn("Market"),
                    "Wallet": st.column_config.TextColumn("Wallet", width="medium"),
                },
                width='stretch',
                hide_index=True
            )
        else:
            st.warning("No data found in database. Run a scan or start the monitor to collect data!")
            
    except Exception as e:
        st.error(f"Error loading database: {e}")

# --- TAB 4: SMART MONEY ---
with tab_smart:
    st.subheader("🧠 Smart Money Intelligence")
    st.caption("Tracking wallets with high win rates and profitability scores.")
    
    col_sm1, col_sm2 = st.columns([2, 1])
    
    with col_sm1:
        st.markdown("### 🏆 Top Smart Whales")
        try:
            whales = database.get_smart_whales(min_trades=3)
            if whales:
                df_w = pd.DataFrame(whales)
                # Convert win_rate float (0.55) to percent value (55.0) for display
                df_w['win_rate'] = df_w['win_rate'] * 100
                
                # Display Config
                st.dataframe(
                    df_w[['address', 'win_rate', 'total_trades', 'profitability_score']],
                    column_config={
                        "address": st.column_config.TextColumn("Wallet Address"),
                        "win_rate": st.column_config.NumberColumn("Win Rate", format="%.1f%%"),
                        "total_trades": st.column_config.NumberColumn("Trades"),
                        "profitability_score": st.column_config.ProgressColumn("Radar Score 🎯", min_value=0, max_value=100, format="%.0f"),
                    },
                    width='stretch',
                    hide_index=True
                )
            else:
                st.info("No smart whales identified yet. Need more data (min 3 trades).")
        except Exception as e:
            st.error(f"Error loading smart whales: {e}")

    with col_sm2:
        st.markdown("### 🕵️ Wallet Inspector")
        wallet_input = st.text_input("Enter Wallet Address", placeholder="0x...")
        
        if wallet_input:
            st.markdown(f"**History for `{wallet_input[:6]}...`**")
            try:
                # Efficient enough for local app
                all_alerts = database.get_recent_alerts(limit=5000)
                w_alerts = [a for a in all_alerts if a['wallet'] == wallet_input]
                
                if w_alerts:
                    df_wa = pd.DataFrame(w_alerts)
                    st.metric("Total Volume", f"${df_wa['value'].sum():,.0f}")
                    st.metric("Trade Count", len(df_wa))
                    
                    st.dataframe(
                        df_wa[['timestamp', 'market_name', 'value', 'outcome', 'side']],
                        width='stretch',
                        hide_index=True
                    )
                else:
                    st.warning("No recorded trades for this wallet in DB.")
            except Exception as e:
                st.error(f"Error inspecting wallet: {e}")

# --- TAB 5: INSIDER FINDER ---
with tab_insider:
    st.subheader("🕵️ Insider Finder")
    st.markdown("Filter trades for suspicious 'Insider' behavior using advanced metrics.")

    st.markdown("### 🔍 Filter Criteria")
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        wc_tx_filter = st.slider("Max WC/TX % (Time Delta)", 0, 100, 5, help="Time between wallet creation and trade. Lower = Sus.")
    with col_f2:
        conc_filter = st.slider("Min Trade Concentration %", 0, 100, 50, help="% of user volume in this specific market. Higher = Focused.")
    with col_f3:
        score_filter = st.slider("Min Radar Score", 0, 100, 80, help="Smart Money Score (Freshness + Focus + Speed).")

    st.divider()

    # 2. Data Processing
    if st.session_state.scan_results:
        df_insider = pd.DataFrame(st.session_state.scan_results)

        # Ensure columns exist (handle empty or old state)
        if "WC/TX%" in df_insider.columns and "Radar Score" in df_insider.columns:

            # Apply Filters
            filtered_df = df_insider[
                (df_insider["WC/TX%"] <= wc_tx_filter) &
                (df_insider["Trade Conc."] >= conc_filter) &
                (df_insider["Radar Score"] >= score_filter)
            ]

            # Metrics
            total_count = len(df_insider)
            match_count = len(filtered_df)
            match_rate = (match_count / total_count * 100) if total_count > 0 else 0

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Candidates", total_count)
            m2.metric("Suspects Found", match_count)
            m3.metric("Match Rate", f"{match_rate:.1f}%")

            if not filtered_df.empty:
                # Prepare Display
                show_df = filtered_df[[
                    "Wallet", "Market", "Value", "Age", "Urgency", "WC/TX%", "Trade Conc.", "Radar Score", "Link"
                ]].copy()

                # Sort by Radar Score desc
                show_df = show_df.sort_values(by="Radar Score", ascending=False)

                st.dataframe(
                    show_df,
                    column_config={
                        "Value": st.column_config.NumberColumn(format="$%d"),
                        "Market": st.column_config.LinkColumn("Market", display_text=".*"),
                        "Link": st.column_config.LinkColumn("Link", display_text="View"),
                        "Age": st.column_config.TextColumn("Age"),
                        "Urgency": st.column_config.ProgressColumn("Urgency 🔥", min_value=0, max_value=100, format="%.0f"),
                        "WC/TX%": st.column_config.NumberColumn("WC/TX% ⏱️", format="%.1f%%", help="Wallet age when trade executed. <5% = Instant action!"),
                        "Trade Conc.": st.column_config.ProgressColumn("Focus 🎯", min_value=0, max_value=100, format="%.0f%%"),
                        "Radar Score": st.column_config.ProgressColumn("Radar Score 🎯", min_value=0, max_value=100, format="%.0f"),
                    },
                    width='stretch',
                    hide_index=True
                )
            else:
                st.info("No trades match these strict criteria. Try relaxing the filters.")
        else:
            st.warning("Data missing metrics. Please run a fresh Historical Scan first.")
    else:
        st.warning("⚠️ No data available. Please run a **Historical Scan** (Tab 2) to populate this view.")
