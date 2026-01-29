import streamlit as st
import pandas as pd
import requests
from io import BytesIO

# --- 網頁設定 ---
st.set_page_config(page_title="Crypto 資產管理系統", layout="wide", page_icon="📈")
st.title("📈 Crypto 資產管理系統 (UTF-8 強制修復版)")

# ==========================================
# ⚠️ 請在此處貼上你的 Google 試算表網址 ⚠️
# ==========================================
# 請確保兩個網址不一樣 (gid 不同)
LOAN_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"
CRYPTO_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# ==========================================

def load_google_sheet(url):
    try:
        # 1. 網址轉換：把編輯網址轉成匯出網址
        if "edit#gid=" in url:
            export_url = url.replace("edit#gid=", "export?format=csv&gid=")
        elif "edit?gid=" in url:
            export_url = url.replace("edit?gid=", "export?format=csv&gid=")
        else:
            export_url = url.replace("/edit", "/export?format=csv")

        # 2. 偽裝成瀏覽器下載
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(export_url, headers=headers)
        response.raise_for_status()

        # 3. 【關鍵修正】強制使用 UTF-8 編碼讀取
        # 使用 BytesIO 直接讀取原始字元，避免 Windows/Linux 系統編碼差異
        df = pd.read_csv(BytesIO(response.content), encoding='utf-8')
        
        # 4. 清理欄位名稱 (去除前後空白)
        df.columns = df.columns.str.strip()
        
        return df

    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        return pd.DataFrame()

# --- 抓取 CoinGecko 幣價 ---
def get_live_prices(symbols):
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
        return {s: res[mapping[s]]['usd'] for s in symbols if mapping.get(s) in res}
    except:
        return {}

# ==========================================
# 主程式邏輯
# ==========================================

# 1. 載入資料
df_loan = load_google_sheet(LOAN_SHEET_URL)
df_crypto = load_google_sheet(CRYPTO_SHEET_URL)

# 停止條件：如果有任何一張表讀失敗
if df_loan.empty or df_crypto.empty:
    st.warning("⚠️ 讀取中斷，請檢查網址是否正確。")
    st.stop()

# 2. 檢查關鍵欄位 (防呆)
if "幣種" not in df_crypto.columns:
    st.error("❌ 在 Crypto 表中找不到「幣種」欄位！(亂碼已修復，請檢查 Google 試算表欄位名稱)")
    st.write("目前讀到的欄位:", df_crypto.columns.tolist())
    st.stop()

if "總資金(USDT)" not in df_loan.columns:
    st.error("❌ 在 Loans 表中找不到「總資金(USDT)」欄位！")
    st.write("目前讀到的欄位:", df_loan.columns.tolist())
    st.stop()

# 3. 側邊欄：即時報價
with st.sidebar:
    st.header("⚡ 即時報價")
    if st.button("🔄 刷新最新幣價"):
        st.rerun()
    
    current_prices = get_live_prices(df_crypto["幣種"].tolist())
    for coin, p in current_prices.items():
        st.write(f"**{coin}**: ${p}")

# 4. 數據計算與顯示
try:
    st.subheader("📊 資產總覽看板")
    
    # 轉換數字
    cols = ["持有顆數", "平均成本(U)", "當前市價(U)"]
    for c in cols:
        if c in df_crypto.columns:
            df_crypto[c] = pd.to_numeric(df_crypto[c], errors='coerce').fillna(0)
    
    # 更新幣價
    for i, row in df_crypto.iterrows():
        if row['幣種'] in current_prices:
            df_crypto.at[i, '當前市價(U)'] = current_prices[row['幣種']]

    # 計算
    total_pool = pd.to_numeric(df_loan["總資金(USDT)"].iloc[0], errors='coerce')
    invested = (df_crypto["持有顆數"] * df_crypto["平均成本(U)"]).sum()
    remaining = total_pool - invested
    market_val = (df_crypto["持有顆數"] * df_crypto["當前市價(U)"]).sum()
    pnl = market_val - invested
    
    # 顯示
    c1, c2, c3 = st.columns(3)
    c1.metric("總資金池 (USDT)", f"${total_pool:,.2f}")
    c2.metric("已投入成本 (USDT)", f"${invested:,.2f}")
    c3.metric("剩餘子彈 (USDT)", f"${remaining:,.2f}", delta=f"{remaining:,.2f}")
    
    st.markdown("---")
    c4, c5 = st.columns(2)
    c4.metric("持倉市值", f"${market_val:,.2f}")
    c5.metric("未實現損益", f"${pnl:,.2f}", delta=f"{pnl:,.2f}")
    
    st.subheader("📋 持倉清單")
    st.dataframe(df_crypto.style.format({"持有顆數": "{:,.2f}", "當前市價(U)": "{:.6f}"}), use_container_width=True)

except Exception as e:
    st.error(f"計算時發生錯誤: {e}")