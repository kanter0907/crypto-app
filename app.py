import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import time

# --- 網頁設定 ---
st.set_page_config(page_title="雲端資產管理系統", layout="wide", page_icon="☁️")
st.title("☁️ Crypto 資產管理系統 (Google Sheets 連動版)")

# ==========================================
# ⚠️ 請在下方引號內，貼上你的 Google 試算表網址 ⚠️
# ==========================================
sheet_url = "https://docs.google.com/spreadsheets/d/https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?usp=sharing/edit"

# 如果你忘了貼，這裡會提醒你
if "你的網址貼在這裡" in sheet_url:
    st.error("🚨 請打開 app.py，在第 14 行貼上你的 Google 試算表網址！")
    st.stop()

# --- 建立 Google Sheets 連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 定義分頁位置 ---
SHEET_IDX_LOANS = 0  
SHEET_IDX_CRYPTO = 1

# --- 1. 讀取資料函式 ---
def load_data():
    try:
        # 我們直接把 sheet_url 傳進去，不透過 secrets，這樣最準
        df_loan = conn.read(spreadsheet=sheet_url, worksheet=SHEET_IDX_LOANS, ttl=0)
        df_crypto = conn.read(spreadsheet=sheet_url, worksheet=SHEET_IDX_CRYPTO, ttl=0)
        
        # 簡單的錯誤防護
        if df_loan is None: df_loan = pd.DataFrame()
        if df_crypto is None: df_crypto = pd.DataFrame()
        
        return df_loan, df_crypto
    except Exception as e:
        st.error(f"❌ 讀取失敗！請確認網址是否正確。錯誤訊息: {e}")
        return pd.DataFrame(), pd.DataFrame()

# --- 2. 儲存資料函式 ---
def save_data(df, sheet_index):
    try:
        # 嘗試寫入
        conn.update(spreadsheet=sheet_url, worksheet=sheet_index, data=df)
        st.toast("✅ 資料已同步！")
        time.sleep(1)
    except Exception as e:
        st.error(f"❌ 存檔失敗 (可能是權限問題): {e}")
        st.info("💡 如果讀取成功但存檔失敗，通常是因為缺少 Service Account。目前請先確認讀取是否正常。")

# --- 3. 抓取 CoinGecko 幣價 ---
def get_coingecko_prices(symbols):
    mapping = {
        "$ADA": "cardano", "$Night": "night-verse", "$SNEK": "snek", 
        "$USDT": "tether", "$BTC": "bitcoin", "$ETH": "ethereum", "$SOL": "solana"
    }
    ids = [mapping.get(s) for s in symbols if mapping.get(s)]
    if not ids: return {}
    
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies=usd"
    try:
        response = requests.get(url, timeout=10)
        return response.json() if response.status_code == 200 else {}
    except:
        return {}

# ==========================================
# 主畫面邏輯
# ==========================================

# 1. 載入資料
df_loan, df_crypto = load_data()

# 停止條件
if df_loan.empty or df_crypto.empty:
    st.warning("⚠️ 無法讀取資料，請檢查網址。")
    st.stop()

# 2. 側邊欄
with st.sidebar:
    st.header("⚙️ 控制台")
    if st.button("🔄 更新幣價"):
        with st.spinner("更新中..."):
            price_map = get_coingecko_prices(df_crypto["幣種"].tolist())
            mapping = {"$ADA": "cardano", "$Night": "night-verse", "$SNEK": "snek", "$USDT": "tether"}
            
            updated_count = 0
            for index, row in df_crypto.iterrows():
                cid = mapping.get(row['幣種'])
                if cid and cid in price_map:
                    df_crypto.at[index, '當前市價(U)'] = price_map[cid]['usd']
                    updated_count += 1
            
            if updated_count > 0:
                save_data(df_crypto, SHEET_IDX_CRYPTO)
                st.success("更新完成！")
                st.rerun()

# 3. 顯示看板
st.subheader("📊 資產看板")
try:
    total_pool = df_loan.iloc[0, df_loan.columns.get_loc("總資金(USDT)")] if "總資金(USDT)" in df_loan.columns else 0
    
    # 轉型計算
    for col in ["持有顆數", "平均成本(U)", "當前市價(U)"]:
        df_crypto[col] = pd.to_numeric(df_crypto[col], errors='coerce').fillna(0)
    
    invested = (df_crypto["持有顆數"] * df_crypto["平均成本(U)"]).sum()
    remaining = total_pool - invested
    market_val = (df_crypto["持有顆數"] * df_crypto["當前市價(U)"]).sum()
    pnl = market_val - invested
    
    c1, c2, c3 = st.columns(3)
    c1.metric("總資金池", f"${total_pool:,.2f}")
    c2.metric("已投入", f"${invested:,.2f}")
    c3.metric("剩餘子彈", f"${remaining:,.2f}")
    
    st.markdown("---")
    c4, c5 = st.columns(2)
    c4.metric("目前市值", f"${market_val:,.2f}")
    c5.metric("總損益", f"${pnl:,.2f}", delta=f"{pnl:,.2f}")

except Exception as e:
    st.error(f"數據計算錯誤: {e}")

# 4. 編輯區
st.subheader("📝 持倉編輯")
edited = st.data_editor(df_crypto, num_rows="dynamic", use_container_width=True)
if st.button("💾 儲存修改"):
    save_data(edited, SHEET_IDX_CRYPTO)
    st.rerun()