import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import json
import os
from datetime import datetime
import pytz

# --- ⚙️ CONFIGURATION ---
TELEGRAM_TOKEN = '8506498777:AAF3ui-xPOgbBe20-DRvGCj_HiN7c0uawjw'
TELEGRAM_CHAT_ID = '6088825847'

# ✅ BINANCE SETUP WITH 451 ERROR BYPASS (API1/API2/API3)
future_ex = ccxt.binance({
    'options': {'defaultType': 'future'}, 
    'enableRateLimit': True,
    'urls': {
        'api': {
            'public': 'https://api1.binance.com/api/v3',
            'private': 'https://api1.binance.com/api/v3',
        },
        'fapiPublic': 'https://fapi.binance.com/fapi/v1',
        'fapiPrivate': 'https://fapi.binance.com/fapi/v1',
    }
})

pkt_timezone = pytz.timezone('Asia/Karachi')
STATE_FILE = 'state_history.json'

# Global storage for volume comparisons
prev_tickers_s4 = {}  # For Strategy 4
prev_tickers_s5 = {}  # For Strategy 5 (BULA)

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_pkt_now():
    return datetime.now(pkt_timezone).strftime('%d-%m-%Y | %I:%M:%S %p')

def load_states():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_states(data):
    try:
        with open(STATE_FILE, 'w') as f: json.dump(data, f)
    except: pass

# ==========================================
# STRATEGY 4: Volume Spikes (Top 15)
# ==========================================
def run_strat_4(current_tickers):
    global prev_tickers_s4
    try:
        vol_stats = []
        if prev_tickers_s4:
            for s, t in current_tickers.items():
                if '/USDT' in s and s in prev_tickers_s4:
                    old_v, new_v = prev_tickers_s4[s]['quoteVolume'], t['quoteVolume']
                    if old_v and old_v > 0:
                        vol_change = ((new_v - old_v) / old_v) * 100
                        vol_stats.append({'symbol': s, 'vol_change': vol_change})
            
            if vol_stats:
                v_gainers = pd.DataFrame(vol_stats).nlargest(15, 'vol_change')
                msg = f"🔥 *STRATEGY 4: TOP 15 VOLUME SPIKES*\n📅 {get_pkt_now()}\n\n"
                msg += "\n".join([f"📢 {r['symbol']} (+{r['vol_change']:.1f}%)" for _, r in v_gainers.iterrows()])
                send_telegram(msg)
        
        prev_tickers_s4 = current_tickers
    except Exception as e:
        print(f"S4 Error: {e}")

# ==========================================
# STRATEGY 5: BULA (Full Top 20 Inline)
# ==========================================
def run_strat_5_bula(current_tickers):
    global prev_tickers_s5
    try:
        stats = []
        if prev_tickers_s5:
            for s, t in current_tickers.items():
                if '/USDT' in s and s.endswith(':USDT') and s in prev_tickers_s5:
                    old_v = prev_tickers_s5[s]['quoteVolume']
                    new_v = t['quoteVolume']
                    if old_v and old_v > 0:
                        change = ((new_v - old_v) / old_v) * 100
                        stats.append({'symbol': s.replace(':USDT', ''), 'change': change})
        
        if stats:
            v_gainers = pd.DataFrame(stats).nlargest(20, 'change')
            inline_str = " | ".join([f"*{r['symbol']}* (+{r['change']:.1f}%)" for _, r in v_gainers.iterrows()])
            send_telegram(f"🐂 *STRATEGY 5: BULA (Top 20)*\n📅 {get_pkt_now()}\n\n{inline_str}")
            
        prev_tickers_s5 = current_tickers
    except Exception as e:
        print(f"S5 Error: {e}")

# --- Master Loop ---
if __name__ == "__main__":
    send_telegram(f"🚀 *Binance Volume Bot Online*\n📍 *Region:* {future_ex.urls['api']['public']}\n🕒 *PST:* {get_pkt_now()}")
    
    while True:
        try:
            hist = load_states()
            now = time.time()
            
            # Fetch all tickers once for both strategies
            all_tickers = future_ex.fetch_tickers()
            
            # Run Strategy 4 every 11 minutes
            if now - hist.get('t4', 0) >= (11 * 60):
                run_strat_4(all_tickers)
                hist['t4'] = now
                save_states(hist)
            
            # Run Strategy 5 every 30 minutes
            if now - hist.get('t5', 0) >= (30 * 60):
                run_strat_5_bula(all_tickers)
                hist['t5'] = now
                save_states(hist)
                
            time.sleep(30) # Check every 30 seconds
            
        except Exception as e:
            print(f"Main Loop Error: {e}")
            time.sleep(30)
