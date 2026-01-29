import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# --- 網頁設定 ---
st.set_page_config(page_title="資產管理系統-唯讀版", layout="wide", page_icon="📈")
st.title("📈 Crypto 資產管理系統 (唯讀同步版)")

# ==========================================
# ⚠️ 請在此處填入你「發佈到網路」的 CSV 網址 ⚠️
# ==========================================
# 提示：如果你發佈的是全文件，這裡填寫該網址。
# 如果你有兩個分頁，最保險是分別發佈 loans 頁和 crypto 頁，並把網址貼在下面。
LOAN_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTa5SSqEEWRDVGAhj64fMzrY3Oxy-Fhkv9Buq9UYV2Fx2ZwZj0OU2i1-6I92-WgUKiRFlvU5meQyV-2/pub?output=csv"
CRYPTO_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTa5SSqEEWRDVGAhj64fMzrY3Oxy-Fhkv9Buq9UYV2Fx2ZwZj0OU2i1-6I92-WgUKiRFlvU5meQyV-2/pub?output=csv"

# --- 讀取資料函式 ---
def load_data_from_url(url):
    try:
        # 加上隨機參數避免瀏覽器快取舊資料
        cache_buster = f"?v={datetime.now().timestamp()}"
        df = pd.read_csv(url + cache_buster)
        return df
    except Exception as e:
        st.error(f"讀取失敗，請檢查網址或發佈設定。")
        return pd.DataFrame()

# --- 抓取 CoinGecko 幣價 ---
def get_live_prices(symbols):
    mapping = {"$ADA": "cardano", "$Night": "night-verse", "$SNEK": "snek"}
    ids = [mapping.get(s) for s in symbols if mapping.get(s)]
    if not ids: return {}
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies=usd"
    try:
        res = requests.get(url, timeout=10).json()
        return {s: res[mapping[s]]['usd'] for s in symbols if mapping.get(s) in res}
    except:
        return {}

# 1. 載入資料
df_loan = load_data_from_url(LOAN_CSV_URL)
df_crypto = load_data_from_url(CRYPTO_CSV_URL)

if df_loan.empty or df_crypto.empty:
    st.warning("🔄 正在等待 Google 試算表發佈數據... 請確保網址正確並已發佈為 CSV。")
    st.info("💡 提醒：請在 Google 試算表執行「檔案 > 共用 > 發佈到網路」，選擇分頁並選「CSV」格式。")
    st.stop()

# 2. 側邊欄：即時報價
with st.sidebar:
    st.header("⚡ 即時報價")
    if st.button("🔄 刷新最新幣價"):
        st.rerun()
    
    prices = get_live_prices(df_crypto["幣種"].tolist())
    for coin, p in prices.items():
        st.write(f"{coin}: **${p}**")

# 3. 數據計算 (連動邏輯)
try:
    # 資金池 (抓取第一行)
    total_pool = df_loan["總資金(USDT)"].iloc[0]
    
    # 轉換數字格式
    for col in ["持有顆數", "平均成本(U)", "當前市價(U)"]:
        df_crypto[col] = pd.to_numeric(df_crypto[col], errors='coerce').fillna(0)

    # 如果有抓到即時價，就替換掉原本的市價
    for i, row in df_crypto.iterrows():
        if row['幣種'] in prices:
            df_crypto.at[i, '當前市價(U)'] = prices[row['幣種']]

    invested = (df_crypto["持有顆數"] * df_crypto["平均成本(U)"]).sum()
    remaining = total_pool - invested
    market_val = (df_crypto["持有顆數"] * df_crypto["當前市價(U)"]).sum()
    pnl = market_val - invested

    # 顯示看板
    c1, c2, c3 = st.columns(3)
    c1.metric("總資金池 (USDT)", f"${total_pool:,.2f}")
    c2.metric("已投入成本 (USDT)", f"${invested:,.2f}")
    c3.metric("剩餘子彈 (USDT)", f"${remaining:,.2f}", delta=f"{remaining:,.2f}")

    st.markdown("---")
    
    c4, c5 = st.columns(2)
    c4.metric("持倉總市值 (USDT)", f"${market_val:,.2f}")
    c5.metric("未實現總損益 (USDT)", f"${pnl:,.2f}", delta=f"{pnl:,.2f}")

    st.subheader("📋 詳細持倉清單")
    st.dataframe(df_crypto, use_container_width=True)

except Exception as e:
    st.error(f"數據解析錯誤，請確保 Excel 標題正確。")