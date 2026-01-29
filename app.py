import streamlit as st
import pandas as pd
import requests
from io import StringIO

# --- 網頁設定 ---
st.set_page_config(page_title="資產管理系統-穩定版", layout="wide", page_icon="📈")
st.title("📈 Crypto 資產管理系統 (穩定同步版)")

# ==========================================
# ⚠️ 請在下方貼上你「瀏覽器上方」的網址 ⚠️
# ==========================================
# 注意：請直接貼上你在編輯 Google 試算表時看到的網址即可
# 格式通常是 .../edit#gid=...

LOAN_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"
CRYPTO_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# ==========================================

# --- 核心：網址轉換與讀取函式 ---
def load_google_sheet(url):
    try:
        # 1. 如果使用者貼的是編輯網址，自動轉換成 CSV 下載連結
        if "edit#gid=" in url:
            export_url = url.replace("edit#gid=", "export?format=csv&gid=")
        elif "edit?gid=" in url:
            export_url = url.replace("edit?gid=", "export?format=csv&gid=")
        else:
            # 如果網址格式怪怪的，嘗試通用轉換
            export_url = url.replace("/edit", "/export?format=csv")
            
        # 2. 偽裝成瀏覽器 (騙過 Google 的防機器人機制)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # 3. 下載資料
        response = requests.get(export_url, headers=headers)
        response.raise_for_status() # 檢查是否有 404 或 403 錯誤
        
        # 4. 轉換成 DataFrame
        df = pd.read_csv(StringIO(response.text))
        return df
        
    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        st.write(f"嘗試讀取的網址: {url}") # 顯示出來方便除錯
        return pd.DataFrame()

# --- 抓取 CoinGecko 幣價 ---
def get_live_prices(symbols):
    # 建立 ID 對照表 (在此新增幣種)
    mapping = {
        "$ADA": "cardano", 
        "$Night": "night-verse", 
        "$SNEK": "snek",
        "$USDT": "tether",
        "$BTC": "bitcoin",
        "$ETH": "ethereum",
        "$SOL": "solana"
    }
    
    ids = [mapping.get(s) for s in symbols if mapping.get(s)]
    if not ids: return {}
    
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies=usd"
    try:
        res = requests.get(url, timeout=10).json()
        new_prices = {}
        for s in symbols:
            coin_id = mapping.get(s)
            if coin_id and coin_id in res:
                new_prices[s] = res[coin_id]['usd']
        return new_prices
    except:
        return {}

# ==========================================
# 主程式邏輯
# ==========================================

# 1. 載入資料
df_loan = load_google_sheet(LOAN_SHEET_URL)
df_crypto = load_google_sheet(CRYPTO_SHEET_URL)

# 停止條件
if df_loan.empty or df_crypto.empty:
    st.warning("⚠️ 無法讀取資料。請確認：")
    st.markdown("1. 網址是否正確貼上（要是瀏覽器上方的編輯網址）。")
    st.markdown("2. Google 試算表的共用權限是否已設為**「知道連結的任何人」**。")
    st.stop()

# 2. 側邊欄：即時報價
with st.sidebar:
    st.header("⚡ 即時報價")
    if st.button("🔄 刷新最新幣價"):
        st.rerun()
    
    # 抓取並顯示
    current_prices = get_live_prices(df_crypto["幣種"].tolist())
    for coin, p in current_prices.items():
        st.write(f"**{coin}**: ${p}")

# 3. 數據計算與顯示
try:
    st.subheader("📊 資產總覽看板")
    
    # A. 處理資金池 (抓取第一列)
    total_pool = df_loan["總資金(USDT)"].iloc[0] if "總資金(USDT)" in df_loan.columns else 0
    
    # B. 處理 Crypto 數據 (轉成數字格式以免出錯)
    cols_to_fix = ["持有顆數", "平均成本(U)", "當前市價(U)"]
    for col in cols_to_fix:
        if col in df_crypto.columns:
            df_crypto[col] = pd.to_numeric(df_crypto[col], errors='coerce').fillna(0)
    
    # C. 更新為最新幣價 (如果有抓到的話)
    for i, row in df_crypto.iterrows():
        coin = row['幣種']
        if coin in current_prices:
            df_crypto.at[i, '當前市價(U)'] = current_prices[coin]

    # D. 計算核心指標
    invested = (df_crypto["持有顆數"] * df_crypto["平均成本(U)"]).sum()
    remaining = total_pool - invested
    market_val = (df_crypto["持有顆數"] * df_crypto["當前市價(U)"]).sum()
    pnl = market_val - invested
    
    # E. 顯示 Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("總資金池 (USDT)", f"${total_pool:,.2f}")
    c2.metric("已投入成本 (USDT)", f"${invested:,.2f}")
    c3.metric("剩餘子彈 (USDT)", f"${remaining:,.2f}", delta=f"{remaining:,.2f}", delta_color="normal")
    
    st.markdown("---")
    
    c4, c5 = st.columns(2)
    c4.metric("持倉總市值 (USDT)", f"${market_val:,.2f}")
    c5.metric("未實現總損益 (USDT)", f"${pnl:,.2f}", delta=f"{pnl:,.2f}")
    
    # F. 顯示詳細表格
    st.subheader("📋 詳細持倉清單")
    st.caption("💡 此表格資料來自 Google Sheets，如需修改請直接去試算表編輯。")
    
    # 格式化顯示 (小數點)
    st.dataframe(df_crypto.style.format({
        "持有顆數": "{:,.2f}",
        "平均成本(U)": "{:.6f}",
        "當前市價(U)": "{:.6f}",
    }), use_container_width=True)

except Exception as e:
    st.error(f"數據計算錯誤: {e}")
    st.write("請檢查 Excel 內的欄位名稱是否與原本 CSV 一致。")