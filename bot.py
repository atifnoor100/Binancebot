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

# Binance Futures Setup
future_ex = ccxt.binance({
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})
pkt_timezone = pytz.timezone('Asia/Karachi')

STATE_FILE = 'state_history.json'

# Global storage for volume comparisons
prev_tickers    = {}   # For Strategy 4
prev_tickers_s5 = {}   # For Strategy 5 (BULA)

# Strategy intervals (minutes)
STRAT_INTERVALS = {
    '4': 11,
    '5': 30,
}

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception:
        pass

def get_pkt_now():
    return datetime.now(pkt_timezone).strftime('%d-%m-%Y | %I:%M:%S %p')

def load_states():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_states(data):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass

def seconds_until_next_run(last_run: float, interval_minutes: int) -> float:
    """How many seconds remain until this strategy is due to run again."""
    due_at = last_run + interval_minutes * 60
    return max(0.0, due_at - time.time())

def compute_sleep_duration(hist: dict) -> float:
    """
    Find the shortest wait across all strategies so the bot sleeps
    exactly until the next strategy is due.
    Returns 0 if any strategy is already overdue.
    """
    waits = []
    for s_num, interval in STRAT_INTERVALS.items():
        t_key = f't{s_num}'
        last = hist.get(t_key, 0)
        waits.append(seconds_until_next_run(last, interval))
    return min(waits) if waits else 30

# ─────────────────────────────────────────
# STRATEGY 4: Volume Spikes (Top 15)
# ─────────────────────────────────────────

def run_strat_4(current_tickers):
    global prev_tickers
    try:
        vol_stats = []
        if prev_tickers:
            for s, t in current_tickers.items():
                try:
                    if '/USDT' not in s or s not in prev_tickers:
                        continue
                    old_v = prev_tickers[s].get('quoteVolume') or 0
                    new_v = t.get('quoteVolume') or 0
                    if old_v > 0:
                        vol_change = ((new_v - old_v) / old_v) * 100
                        vol_stats.append({'symbol': s, 'vol_change': vol_change})
                except Exception:
                    continue  # skip this coin, don't crash

            if vol_stats:
                df = pd.DataFrame(vol_stats)
                v_gainers = df.nlargest(15, 'vol_change')
                msg = f"🔥 *STRATEGY 4: TOP 15 VOLUME SPIKES*\n📅 {get_pkt_now()}\n\n"
                msg += "\n".join(
                    [f"📢 {r['symbol']} (+{r['vol_change']:.1f}%)" for _, r in v_gainers.iterrows()]
                )
                send_telegram(msg)
        prev_tickers = current_tickers
    except Exception:
        pass

# ─────────────────────────────────────────
# STRATEGY 5: BULA (Full Top 20 Inline)
# ─────────────────────────────────────────

def run_strat_5_bula(current_tickers):
    global prev_tickers_s5
    try:
        stats = []
        if prev_tickers_s5:
            for s, t in current_tickers.items():
                try:
                    if '/USDT' not in s or not s.endswith(':USDT') or s not in prev_tickers_s5:
                        continue
                    old_v = prev_tickers_s5[s].get('quoteVolume') or 0
                    new_v = t.get('quoteVolume') or 0
                    if old_v > 0:
                        change = ((new_v - old_v) / old_v) * 100
                        stats.append({'symbol': s.replace(':USDT', ''), 'change': change})
                except Exception:
                    continue  # skip this coin, don't crash

        if stats:
            df = pd.DataFrame(stats)
            v_gainers = df.nlargest(20, 'change')
            inline_str = " | ".join(
                [f"*{r['symbol']}* (+{r['change']:.1f}%)" for _, r in v_gainers.iterrows()]
            )
            send_telegram(f"🐂 *STRATEGY 5: BULA (Top 20)*\n📅 {get_pkt_now()}\n\n{inline_str}")

        prev_tickers_s5 = current_tickers
    except Exception:
        pass

# ─────────────────────────────────────────
# MASTER LOOP
# ─────────────────────────────────────────

def main_loop():
    send_telegram(f"🚀 *Binance Bot Online*\n📍 *PST Time:* {get_pkt_now()}")

    while True:
        try:
            hist = load_states()
            now  = time.time()

            for s_num, interval in STRAT_INTERVALS.items():
                t_key = f't{s_num}'
                if now - hist.get(t_key, 0) >= interval * 60:
                    # Fetch tickers safely — if this fails, skip this cycle
                    try:
                        all_tickers = future_ex.fetch_tickers()
                    except Exception:
                        time.sleep(15)
                        break  # retry next iteration

                    if s_num == '4':
                        run_strat_4(all_tickers)
                    elif s_num == '5':
                        run_strat_5_bula(all_tickers)

                    hist[t_key] = time.time()
                    save_states(hist)

            # ── SLEEP until the next strategy is due ──
            sleep_secs = compute_sleep_duration(load_states())
            if sleep_secs > 0:
                # Clamp to a max of 5 minutes so we never miss a run by too long
                sleep_secs = min(sleep_secs, 300)
                time.sleep(sleep_secs)
            else:
                time.sleep(2)   # overdue — check again immediately

        except Exception:
            # Unexpected crash: wait briefly then continue the loop (auto-restart)
            time.sleep(15)


# ─────────────────────────────────────────
# ENTRY POINT — outer watchdog for full crashes
# ─────────────────────────────────────────

if __name__ == "__main__":
    while True:
        try:
            main_loop()
        except Exception:
            # If main_loop itself somehow exits or raises, restart it
            send_telegram(f"⚠️ *Bot restarting after unexpected error*\n📅 {get_pkt_now()}")
            time.sleep(15)
