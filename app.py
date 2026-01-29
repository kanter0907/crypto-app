import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import time

# --- 網頁設定 ---
st.set_page_config(page_title="Google Sheets 雲端版資產管理", layout="wide")
st.title("☁️ Crypto 資產管理系統 (Google Sheets 版)")

# --- 建立 Google Sheets 連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 1. 讀取資料函式 ---
def load_data():
    # 讀取 loans 分頁
    df_loan = conn.read(worksheet="loans")
    # 讀取 crypto 分頁
    df_crypto = conn.read(worksheet="crypto")
    return df_loan, df_crypto

# --- 2. 儲存資料函式 ---
def save_data(df, worksheet_name):
    conn.update(worksheet=worksheet_name, data=df)
    st.toast(f"✅ {worksheet_name} 已同步至 Google Sheets！")

# --- 3. 抓取幣價 (維持原本邏輯) ---
def get_coingecko_prices(symbols):
    mapping = {"$ADA": "cardano", "$Night": "night-verse", "$SNEK": "snek", "$USDT": "tether"}
    ids = ",".join([mapping.get(s) for s in symbols if mapping.get(s)])
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
    try:
        response = requests.get(url, timeout=10)
        return response.json()
    except:
        return {}

# 載入資料
df_loan, df_crypto = load_data()

# --- 側邊欄與邏輯 ---
with st.sidebar:
    st.header("⚙️ 雲端同步控制")
    if st.button("🔄 更新幣價並同步雲端"):
        price_data = get_coingecko_prices(df_crypto["幣種"].tolist())
        mapping = {"$ADA": "cardano", "$Night": "night-verse", "$SNEK": "snek"}
        for i, row in df_crypto.iterrows():
            coin_id = mapping.get(row['幣種'])
            if coin_id in price_data:
                df_crypto.at[i, '當前市價(U)'] = price_data[coin_id]['usd']
        save_data(df_crypto, "crypto")
        st.rerun()

# --- 顯示與連動 (同 V3.0) ---
st.subheader("📊 資金連動總覽")
# (這裡保留原本的 Metric 計算代碼...)
# ... [省略中間顯示邏輯，與 V3.0 相同] ...

# 編輯與儲存
st.subheader("📝 編輯持倉")
edited_crypto = st.data_editor(df_crypto, num_rows="dynamic")
if st.button("💾 將修改存入 Google Sheets"):
    save_data(edited_crypto, "crypto")
    st.rerun()