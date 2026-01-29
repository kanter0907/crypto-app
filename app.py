import streamlit as st
import pandas as pd
import requests
from io import StringIO

# --- 網頁設定 ---
st.set_page_config(page_title="資產管理系統", layout="wide", page_icon="🔍")
st.title("🔍 系統自我診斷模式")

# ==========================================
# ⚠️ 請在下方再次確認你的網址 ⚠️
# ==========================================
# 請確保這兩個網址是不一樣的！(gid= 後面的數字應該不同)

LOAN_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"
CRYPTO_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# ==========================================

def load_google_sheet(url, name):
    try:
        # 網址轉換邏輯
        if "edit#gid=" in url:
            export_url = url.replace("edit#gid=", "export?format=csv&gid=")
        elif "edit?gid=" in url:
            export_url = url.replace("edit?gid=", "export?format=csv&gid=")
        else:
            export_url = url.replace("/edit", "/export?format=csv")
            
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(export_url, headers=headers)
        response.raise_for_status()
        
        df = pd.read_csv(StringIO(response.text))
        df.columns = df.columns.str.strip() # 去除空白
        return df
        
    except Exception as e:
        st.error(f"❌ {name} 讀取失敗: {e}")
        return pd.DataFrame()

# --- 診斷開始 ---
st.subheader("1️⃣ 檢查 Crypto (加密貨幣) 分頁")
df_crypto = load_google_sheet(CRYPTO_SHEET_URL, "Crypto表")

if not df_crypto.empty:
    st.write("📊 程式讀到的欄位名稱有：")
    st.code(df_crypto.columns.tolist())
    
    if "幣種" in df_crypto.columns:
        st.success("✅ 成功找到「幣種」欄位！這張表是對的。")
    elif "總資金(USDT)" in df_crypto.columns:
        st.error("🚨 抓包了！你把「資金池 (Loans)」的網址貼到「Crypto」這邊了！")
        st.info("💡 請去 Google 試算表切換到 Crypto 分頁，複製那串 gid 不一樣的網址。")
    else:
        st.error(f"❌ 找不到「幣種」欄位。請檢查上方顯示的欄位名稱。")
        st.dataframe(df_crypto.head())

st.subheader("2️⃣ 檢查 Loans (資金池) 分頁")
df_loan = load_google_sheet(LOAN_SHEET_URL, "Loans表")

if not df_loan.empty:
    st.write("📊 程式讀到的欄位名稱有：")
    st.code(df_loan.columns.tolist())
    
    if "總資金(USDT)" in df_loan.columns:
        st.success("✅ 成功找到「總資金(USDT)」欄位！這張表是對的。")
    else:
        st.warning("⚠️ 這張表看起來不像資金池，請確認網址。")

# --- 如果兩張表都對，才顯示原本的介面 ---
if "幣種" in df_crypto.columns and "總資金(USDT)" in df_loan.columns:
    st.divider()
    st.subheader("🎉 診斷通過！顯示資產看板")
    
    # 這裡放原本的計算邏輯
    try:
        total_pool = df_loan["總資金(USDT)"].iloc[0]
        
        # 簡單計算展示
        invested = 0
        market_val = 0
        
        # 嘗試計算 (若欄位齊全)
        if set(["持有顆數", "平均成本(U)"]).issubset(df_crypto.columns):
            # 轉數字
            for col in ["持有顆數", "平均成本(U)", "當前市價(U)"]:
                if col in df_crypto.columns:
                    df_crypto[col] = pd.to_numeric(df_crypto[col], errors='coerce').fillna(0)
            
            invested = (df_crypto["持有顆數"] * df_crypto["平均成本(U)"]).sum()
            
            col1, col2 = st.columns(2)
            col1.metric("總資金池", f"${total_pool:,.2f}")
            col2.metric("已投入成本", f"${invested:,.2f}")
            
            st.dataframe(df_crypto)
            
    except Exception as e:
        st.error(f"計算錯誤: {e}")