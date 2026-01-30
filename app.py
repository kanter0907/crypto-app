import streamlit as st
import pandas as pd
import requests
import time
import re
import altair as alt
from io import BytesIO

# --- 網頁設定 ---
st.set_page_config(page_title="Crypto 資金戰情室", layout="wide", page_icon="🏦")
st.title("🏦 Crypto 資金戰情室 (Pro Max)")

# ==========================================
# ⚠️ 請在此處填入你的 Google 試算表網址 ⚠️
# ==========================================
# 1. 交易紀錄分頁
TX_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# 2. 資金紀錄分頁
USDT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"

# ==========================================

# 1. 讀取資料函式
def load_google_sheet(url, sheet_type="tx"):
    try:
        if "edit#gid=" in url:
            export_url = url.replace("edit#gid=", "export?format=csv&gid=")
        elif "edit?gid=" in url:
            export_url = url.replace("edit?gid=", "export?format=csv&gid=")
        else:
            export_url = url.replace("/edit", "/export?format=csv")

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(export_url, headers=headers)
        response.raise_for_status()

        df = pd.read_csv(BytesIO(response.content), encoding='utf-8')
        df.columns = df.columns.str.strip() 
        
        def clean_number(value):
            if pd.isna(value): return 0
            val_str = str(value)
            clean_val = re.sub(r'[^\d.-]', '', val_str) 
            try:
                return float(clean_val)
            except:
                return 0

        if sheet_type == "usdt":
            required = ["投入台幣", "買入USDT"]
            if "TWD" in df.columns: df.rename(columns={"TWD": "投入台幣"}, inplace=True)
            if "USDT" in df.columns: df.rename(columns={"USDT": "買入USDT"}, inplace=True)
            for col in required:
                if col in df.columns:
                    df[col] = df[col].apply(clean_number)
                else:
                    df[col] = 0.0

        elif sheet_type == "tx":
            if "幣種" not in df.columns and "Coin" in df.columns: df.rename(columns={"Coin": "幣種"}, inplace=True)
            if "投入金額(U)" not in df.columns and "金額" in df.columns: df.rename(columns={"金額": "投入金額(U)"}, inplace=True)
            if "持有顆數" not in df.columns and "顆數" in df.columns: df.rename(columns={"顆數": "持有顆數"}, inplace=True)
            
            if "幣種" in df.columns:
                df["幣種"] = df["幣種"].astype(str).str.strip()
            
            for col in ["投入金額(U)", "持有顆數"]:
                if col in df.columns:
                    df[col] = df[col].apply(clean_number)
                else:
                    df[col] = 0.0
                    
        return df
    except Exception as e:
        return pd.DataFrame()

# 2. 自動搜尋 ID (快取 24 小時)
@st.cache_data(ttl=86400)
def find_coin_id(symbol):
    if not isinstance(symbol, str): return None
    clean_symbol = symbol.replace("$", "").strip().lower()
    search_url = f"https://api.coingecko.com/api/v3/search?query={clean_symbol}"
    headers = {"User-Agent": "Mozilla/5.0"} 
    try:
        time.sleep(1)
        res = requests.get(search_url, headers=headers, timeout=5).json()
        if "coins" in res and len(res["coins"]) > 0:
            return res["coins"][0]["id"]
        return None
    except:
        return None

# 3. 抓取幣價 (快取 10 分鐘)
@st.cache_data(ttl=600)
def get_live_prices_auto(symbols):
    known_mapping = {
        "$ADA": "cardano", "$NIGHT": "midnight-3", "$SNEK": "snek",
        "$USDT": "tether", "$BTC": "bitcoin", "$ETH": "ethereum",
        "$SOL": "solana", "$XRP": "ripple", "$DOGE": "dogecoin",
        "$BNB": "binancecoin", "$PEPE": "pepe"
    }
    
    final_ids = {}
    unknown_symbols = []

    for s in symbols:
        if not isinstance(s, str): continue
        clean_s = s.strip().upper()
        match = None
        for k, v in known_mapping.items():
            if k.upper() == clean_s:
                match = v
                break
        
        if match:
            final_ids[s] = match
        else:
            unknown_symbols.append(s)
    
    for s in unknown_symbols:
        fid = find_coin_id(s)
        if fid: final_ids[s] = fid

    ids_list = list(set(final_ids.values()))
    if not ids_list: return {}

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids_list)}&vs_currencies=usd"
    headers = {"User-Agent": "Mozilla/5.0"} 
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            prices = {}
            for sym, cid in final_ids.items():
                if cid in data:
                    prices[sym] = data[cid]['usd']
            return prices
        else:
            return {}
    except Exception:
        return {}

# 4. 【關鍵修改】抓取 USDT/TWD 匯率 (改用 BitoPro API)
@st.cache_data(ttl=600)
def get_usdt_twd_rate():
    # 來源：BitoPro 台灣幣託交易所 (公開 API，穩定且準確)
    url = "https://api.bitopro.com/v3/tickers/usdt_twd"
    headers = {"User-Agent": "Mozilla/5.0"} 
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            # BitoPro 回傳格式: {'data': {'lastPrice': '32.45', ...}}
            return float(data.get("data", {}).get("lastPrice", 0))
    except:
        pass
    return None

# ==========================================
# 主程式邏輯
# ==========================================

# 1. 讀取資料
df_usdt = load_google_sheet(USDT_SHEET_URL, sheet_type="usdt")
df_tx = load_google_sheet(TX_SHEET_URL, sheet_type="tx")

# 2. 預先初始化變數
avg_exchange_rate =