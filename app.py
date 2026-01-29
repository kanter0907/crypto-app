import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import requests
import time

# --- 網頁設定 ---
st.set_page_config(page_title="雲端資產管理系統", layout="wide", page_icon="☁️")
st.title("☁️ Crypto 資產管理系統 (Google Sheets 連動版)")

# --- 建立 Google Sheets 連線 ---
# 使用 ttl=0 確保每次都抓到最新資料，不會被快取卡住
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 定義分頁位置 (解決名稱錯誤的關鍵) ---
# 0 代表第一張分頁 (資金池/Loans)
# 1 代表第二張分頁 (加密貨幣/Crypto)
SHEET_IDX_LOANS = 0  
SHEET_IDX_CRYPTO = 1

# --- 1. 讀取資料函式 ---
def load_data():
    try:
        # 強制讀取第 1 頁和第 2 頁，不管名稱叫什麼
        df_loan = conn.read(worksheet=SHEET_IDX_LOANS, ttl=0)
        df_crypto = conn.read(worksheet=SHEET_IDX_CRYPTO, ttl=0)
        
        # 簡單的錯誤防護：如果讀出來是空的，給個空表
        if df_loan is None: df_loan = pd.DataFrame()
        if df_crypto is None: df_crypto = pd.DataFrame()
        
        return df_loan, df_crypto
    except Exception as e:
        st.error(f"⚠️ 讀取 Google Sheets 失敗，請檢查權限設定！錯誤訊息: {e}")
        return pd.DataFrame(), pd.DataFrame()

# --- 2. 儲存資料函式 ---
def save_data(df, sheet_index):
    try:
        conn.update(worksheet=sheet_index, data=df)
        st.toast("✅ 資料已成功同步回 Google Sheets！")
        time.sleep(1) # 給一點緩衝時間
    except Exception as e:
        st.error(f"❌ 存檔失敗: {e}")

# --- 3. 抓取 CoinGecko 幣價 ---
def get_coingecko_prices(symbols):
    # ID 對照表：如果有新幣種，請在這裡新增
    mapping = {
        "$ADA": "cardano",
        "$Night": "night-verse",
        "$SNEK": "snek",
        "$USDT": "tether",
        "$BTC": "bitcoin",
        "$ETH": "ethereum",
        "$SOL": "solana"
    }
    
    # 轉換成 ID
    ids = [mapping.get(s) for s in symbols if mapping.get(s)]
    if not ids:
        return {}
        
    ids_string = ",".join(ids)
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids_string}&vs_currencies=usd"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            st.warning("抓取價格失敗 (API 可能忙線中)")
            return {}
    except:
        return {}

# ==========================================
# 程式主邏輯
# ==========================================

# 1. 載入資料
df_loan, df_crypto = load_data()

# 如果讀不到資料，就停止執行後面程式，避免報錯
if df_loan.empty or df_crypto.empty:
    st.warning("⚠️ 目前讀不到資料。請確認 Google 試算表有兩個分頁，且權限已設為「知道連結的任何人 (編輯者)」。")
    st.stop()

# 2. 側邊欄控制
with st.sidebar:
    st.header("⚙️ 控制台")
    
    # 手動更新按鈕
    if st.button("🔄 更新幣價並同步"):
        with st.spinner("正在連線 CoinGecko..."):
            # 抓價格
            price_map = get_coingecko_prices(df_crypto["幣種"].tolist())
            mapping = {"$ADA": "cardano", "$Night": "night-verse", "$SNEK": "snek", "$USDT": "tether", "$BTC": "bitcoin", "$ETH": "ethereum"}
            
            # 更新 DataFrame
            updated_count = 0
            for index, row in df_crypto.iterrows():
                coin_symbol = row['幣種']
                coin_id = mapping.get(coin_symbol)
                
                if coin_id and coin_id in price_map:
                    new_price = price_map[coin_id]['usd']
                    df_crypto.at[index, '當前市價(U)'] = new_price
                    updated_count += 1
            
            # 寫回 Google Sheets (第 2 頁)
            if updated_count > 0:
                save_data(df_crypto, SHEET_IDX_CRYPTO)
                st.success(f"成功更新 {updated_count} 個幣種價格！")
                st.rerun()
            else:
                st.warning("沒有抓到新價格，請稍後再試。")

# ==========================================
# 主畫面：資金連動儀表板
# ==========================================

st.subheader("📊 資金連動看板")

# --- 數學計算區 ---
try:
    # 1. 總資金池 (從第 1 頁讀取)
    # 假設 Excel 格式固定，直接抓欄位加總
    if "總資金(USDT)" in df_loan.columns:
        total_pool_usdt = df_loan["總資金(USDT)"].sum()
    else:
        # 防呆：如果欄位名稱不對，試著抓最後一欄或給預設值
        total_pool_usdt = 0
        st.error("⚠️ 找不到「總資金(USDT)」欄位，請檢查 Google Sheets 第 1 頁標題。")

    # 2. 已投入成本 & 3. 剩餘子彈
    # 確保欄位是數字格式
    df_crypto["持有顆數"] = pd.to_numeric(df_crypto["持有顆數"], errors='coerce').fillna(0)
    df_crypto["平均成本(U)"] = pd.to_numeric(df_crypto["平均成本(U)"], errors='coerce').fillna(0)
    df_crypto["當前市價(U)"] = pd.to_numeric(df_crypto["當前市價(U)"], errors='coerce').fillna(0)

    # 計算
    invested_usdt = (df_crypto["持有顆數"] * df_crypto["平均成本(U)"]).sum()
    remaining_ammo = total_pool_usdt - invested_usdt

    # 4. 市值與損益
    current_market_value = (df_crypto["持有顆數"] * df_crypto["當前市價(U)"]).sum()
    total_pnl = current_market_value - invested_usdt
    pnl_percent = (total_pnl / invested_usdt * 100) if invested_usdt > 0 else 0

    # --- 顯示 Metrics ---
    col1, col2, col3 = st.columns(3)
    col1.metric("總資金池 (USDT)", f"${total_pool_usdt:,.2f}")
    col2.metric("已投入成本 (USDT)", f"${invested_usdt:,.2f}")
    col3.metric("剩餘子彈 (USDT)", f"${remaining_ammo:,.2f}", delta_color="normal")

    st.markdown("---")

    col4, col5, col6 = st.columns(3)
    col4.metric("目前持倉市值", f"${current_market_value:,.2f}")
    col5.metric("未實現損益", f"${total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
    col6.metric("投報率 %", f"{pnl_percent:.2f}%", delta=f"{pnl_percent:.2f}%")

except Exception as e:
    st.error(f"計算數據時發生錯誤，請檢查 Excel 內容格式是否正確。錯誤: {e}")

# ==========================================
# 編輯區
# ==========================================
st.subheader("📝 持倉管理 (雙向同步)")
st.info("👇 修改下方表格並按 Enter，確認無誤後點擊「儲存」按鈕寫入 Google Sheets。")

# 顯示編輯器
edited_crypto = st.data_editor(df_crypto, num_rows="dynamic", use_container_width=True)

if st.button("💾 儲存修改到雲端 (Google Sheets)"):
    save_data(edited_crypto, SHEET_IDX_CRYPTO)
    st.rerun()

# 資金池設定 (折疊)
with st.expander("🏦 設定資金池 (Google Sheets 第 1 頁)"):
    edited_loan = st.data_editor(df_loan, num_rows="dynamic")
    if st.button("💾 儲存資金池設定"):
        save_data(edited_loan, SHEET_IDX_LOANS)
        st.rerun()