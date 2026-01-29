import streamlit as st
import pandas as pd
import requests
import time
from io import BytesIO

# --- 網頁設定 ---
st.set_page_config(page_title="Crypto 智慧資產管理", layout="wide", page_icon="💎")
st.title("💎 Crypto 智慧資產管理系統 (Pro)")

# ==========================================
# ⚠️ 請在此處填入你的 Google 試算表網址 ⚠️
# ==========================================
LOAN_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"
CRYPTO_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# ==========================================

# 1. 讀取 Google Sheets (含亂碼修復與去除空白)
def load_google_sheet(url):
    try:
        # 網址轉換：確保轉為 CSV 匯出格式
        if "edit#gid=" in url:
            export_url = url.replace("edit#gid=", "export?format=csv&gid=")
        elif "edit?gid=" in url:
            export_url = url.replace("edit?gid=", "export?format=csv&gid=")
        else:
            export_url = url.replace("/edit", "/export?format=csv")

        # 加上 User-Agent 偽裝成瀏覽器
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(export_url, headers=headers)
        response.raise_for_status()

        # 使用 UTF-8 讀取
        df = pd.read_csv(BytesIO(response.content), encoding='utf-8')
        df.columns = df.columns.str.strip() # 去除標題空白
        
        # 關鍵修正：去除「幣種」欄位內容的空白 (避免 "$ETH " 對不到)
        if "幣種" in df.columns:
            df["幣種"] = df["幣種"].astype(str).str.strip()
            
        return df
    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        return pd.DataFrame()

# --- 🧠 核心功能：自動搜尋 CoinGecko ID ---
@st.cache_data(ttl=86400)
def find_coin_id(symbol):
    """
    輸入幣種名稱 (例如 'PEPE')，自動去 CoinGecko 搜尋並回傳 ID。
    """
    clean_symbol = symbol.replace("$", "").strip().lower()
    search_url = f"https://api.coingecko.com/api/v3/search?query={clean_symbol}"
    headers = {"User-Agent": "Mozilla/5.0"} 
    
    try:
        time.sleep(1) # 禮貌性延遲，避免太快被 API 阻擋
        response = requests.get(search_url, headers=headers, timeout=5)
        data = response.json()
        if "coins" in data and len(data["coins"]) > 0:
            # 取第一個搜尋結果
            return data["coins"][0]["id"]
        return None
    except:
        return None

# --- 抓取幣價 (修正版：含 User-Agent 與 NIGHT 修正) ---
def get_live_prices_auto(symbols):
    # 預設已知清單 (在此修正特定幣種的 ID)
    known_mapping = {
        "$ADA": "cardano", 
        "$NIGHT": "midnight-3",  # ✅ 強制修正：對應到 midnight-3
        "$SNEK": "snek",
        "$USDT": "tether", 
        "$BTC": "bitcoin", 
        "$ETH": "ethereum",
        "$SOL": "solana", 
        "$XRP": "ripple", 
        "$DOGE": "dogecoin",
        "$BNB": "binancecoin", 
        "$PEPE": "pepe"
    }
    
    final_ids = {}
    unknown_symbols = []

    # 1. 比對已知清單 (忽略大小寫)
    for s in symbols:
        clean_s = s.strip()
        s_upper = clean_s.upper()
        
        if s_upper in known_mapping:
            final_ids[s] = known_mapping[s_upper]
        else:
            unknown_symbols.append(s)
    
    # 2. 自動搜尋未知幣種
    if unknown_symbols:
        status = st.empty()
        status.info(f"🔍 正在搜尋新幣種 ID: {unknown_symbols} ...")
        
        for s in unknown_symbols:
            found_id = find_coin_id(s)
            if found_id:
                final_ids[s] = found_id
            else:
                st.warning(f"⚠️ 找不到 {s}，請檢查拼字。")
        status.empty() # 搜尋完成後隱藏提示

    ids_list = list(set(final_ids.values()))
    if not ids_list: return {}

    # 3. 抓取價格
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids_list)}&vs_currencies=usd"
    headers = {"User-Agent": "Mozilla/5.0"} 
    
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        
        prices = {}
        for sym, cid in final_ids.items():
            if cid in res:
                prices[sym] = res[cid]['usd']
        return prices
    except Exception as e:
        st.sidebar.error(f"連線失敗: {e}")
        return {}

# ==========================================
# 主程式邏輯
# ==========================================

df_loan = load_google_sheet(LOAN_SHEET_URL)
df_crypto = load_google_sheet(CRYPTO_SHEET_URL)

if df_loan.empty or df_crypto.empty:
    st.warning("⚠️ 讀取中斷，請檢查網址是否正確。")
    st.stop()

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新最新幣價"):
        # 清除快取，強制重新抓取
        find_coin_id.clear()
        st.cache_data.clear()
        st.rerun()
    
    current_prices = get_live_prices_auto(df_crypto["幣種"].tolist())
    
    if current_prices:
        st.success(f"✅ 已更新 {len(current_prices)} 個幣種價格")
    else:
        st.warning("⚠️ 暫時無法獲取價格 (請稍後再試)")

    st.write("---")
    st.write("📊 個別報價:")
    for coin, p in current_prices.items():
        st.write(f"**{coin}**: ${p}")

# --- 主看板計算與顯示 ---
try:
    st.subheader("📊 智慧資產看板")
    
    # 1. 格式轉換 (轉為數字，錯誤補 0)
    cols = ["持有顆數", "平均成本(U)", "當前市價(U)"]
    for c in cols:
        if c in df_crypto.columns:
            df_crypto[c] = pd.to_numeric(df_crypto[c], errors='coerce').fillna(0)
    
    # 2. 填入最新價格
    for i, row in df_crypto.iterrows():
        if row['幣種'] in current_prices:
            df_crypto.at