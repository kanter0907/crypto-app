import streamlit as st
import pandas as pd
import os
import requests
import time
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="資產管理系統 V3.0", layout="wide", page_icon="💰")
st.title("💰 Crypto 資產與資金連動管理系統")

# --- 檔案路徑 ---
LOAN_FILE = 'loans.csv'
CRYPTO_FILE = 'crypto.csv'

# --- 1. 讀取資料 ---
def load_data(file_name):
    if os.path.exists(file_name):
        return pd.read_csv(file_name)
    else:
        st.error(f"❌ 找不到 {file_name}，請先執行 create_files.py")
        return pd.DataFrame()

# --- 2. 儲存資料 ---
def save_data(df, file_name):
    df.to_csv(file_name, index=False, encoding="utf-8-sig")
    st.toast(f"✅ {file_name} 資料已儲存！")

# --- 3. 自動抓價引擎 (CoinGecko) ---
# 說明：因為 SNEK/Night 不在幣安，我們用 CoinGecko 可以一次抓全部
def get_coingecko_prices(symbols):
    # 幣種 ID 對照表 (如果要加新幣，請在這裡查 CoinGecko ID 加入)
    mapping = {
        "$ADA": "cardano",
        "$Night": "night-verse",
        "$SNEK": "snek",
        "$USDT": "tether",
        "$BTC": "bitcoin",
        "$ETH": "ethereum"
    }
    
    ids = [mapping.get(s) for s in symbols if mapping.get(s)]
    ids_string = ",".join(ids)
    
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids_string}&vs_currencies=usd"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        new_prices = {}
        for s in symbols:
            coin_id = mapping.get(s)
            if coin_id and coin_id in data:
                new_prices[s] = data[coin_id]['usd']
        return new_prices
    except Exception as e:
        st.error(f"⚠️ 抓價失敗 (API 可能忙線中)，請稍後再試。錯誤: {e}")
        return {}

# ==========================================
# 核心邏輯區
# ==========================================

# 1. 載入資料
df_loan = load_data(LOAN_FILE)
df_crypto = load_data(CRYPTO_FILE)

# 2. 側邊欄：操作區
with st.sidebar:
    st.header("⚙️ 控制台")
    
    # 手動更新按鈕
    if st.button("🔄 立即更新最新幣價"):
        with st.spinner("正在連線 CoinGecko 抓取全球報價..."):
            # 抓取價格
            price_map = get_coingecko_prices(df_crypto["幣種"].tolist())
            
            # 更新 DataFrame
            if price_map:
                for index, row in df_crypto.iterrows():
                    coin = row['幣種']
                    if coin in price_map:
                        df_crypto.at[index, '當前市價(U)'] = price_map[coin]
                
                # 存檔
                save_data(df_crypto, CRYPTO_FILE)
                st.success(f"更新成功！時間: {datetime.now().strftime('%H:%M:%S')}")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("沒有抓到數據，請檢查網路或稍後再試。")

    st.markdown("---")
    st.info("💡 **提示**：系統使用 CoinGecko API，可同時支援 ADA (幣安) 與 SNEK/Night (鏈上) 的價格查詢。")

# ==========================================
# 主畫面：資金連動儀表板
# ==========================================

# --- 計算邏輯 (Excel 連動還原) ---
# A. 總資金池 (從 loans.csv 讀取)
total_pool_usdt = df_loan["總資金(USDT)"].sum()

# B. 已投入成本 (從 crypto.csv 計算：持有顆數 * 平均成本)
# 注意：這裡我們用「目前持倉」的成本來算
df_crypto["總成本(U)"] = df_crypto["持有顆數"] * df_crypto["平均成本(U)"]
total_invested_usdt = df_crypto["總成本(U)"].sum()

# C. 剩餘子彈 (連動核心：池子 - 已用)
remaining_ammo = total_pool_usdt - total_invested_usdt

# D. 目前市值與損益
df_crypto["目前市值(U)"] = df_crypto["持有顆數"] * df_crypto["當前市價(U)"]
df_crypto["未實現損益(U)"] = df_crypto["目前市值(U)"] - df_crypto["總成本(U)"]
df_crypto["報酬率(%)"] = (df_crypto["未實現損益(U)"] / df_crypto["總成本(U)"]) * 100

total_market_value = df_crypto["目前市值(U)"].sum()
total_pnl = df_crypto["未實現損益(U)"].sum()
total_pnl_percent = (total_pnl / total_invested_usdt * 100) if total_invested_usdt > 0 else 0

# --- 顯示頂部大看板 ---
st.subheader("📊 資產連動總覽")

# 第一排：資金流向
c1, c2, c3 = st.columns(3)
c1.metric("1. 總資金池 (USDT)", f"${total_pool_usdt:,.2f}", "原始資金來源")
c2.metric("2. 已投入成本 (USDT)", f"${total_invested_usdt:,.2f}", "所有持倉成本總和")
c3.metric("3. 剩餘可投入子彈 (USDT)", f"${remaining_ammo:,.2f}", 
          delta=f"{remaining_ammo:,.2f}", delta_color="normal",
          help="這就是 Excel 裡的「剩餘可投入資金」")

st.markdown("---")

# 第二排：投資表現
c4, c5, c6 = st.columns(3)
c4.metric("目前持倉市值 (USDT)", f"${total_market_value:,.2f}", help="根據最新市價計算")
c5.metric("未實現損益 (USDT)", f"${total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
c6.metric("總報酬率 (%)", f"{total_pnl_percent:.2f}%", delta=f"{total_pnl_percent:.2f}%")

# --- 詳細持倉表格 (可編輯) ---
st.subheader("🚀 持倉管理明細")
st.caption("👇 你可以直接修改「顆數」或「成本」，修改後按 Enter，上方數據會自動連動更新。")

# 顯示編輯器
edited_crypto = st.data_editor(
    df_crypto[["幣種", "持有顆數", "平均成本(U)", "當前市價(U)"]], # 只讓用戶改這幾欄
    num_rows="dynamic",
    key="crypto_editor",
    use_container_width=True
)

# 儲存按鈕
if st.button("💾 儲存表格修改"):
    # 這裡只存基礎欄位，計算欄位交給程式即時算
    save_data(edited_crypto, CRYPTO_FILE)
    st.rerun()

# --- 底部：資金池設定 (折疊起來以免誤觸) ---
with st.expander("🏦 設定總資金池 (Line貸/自有資金)"):
    edited_loan = st.data_editor(df_loan, num_rows="dynamic")
    if st.button("💾 儲存資金池設定"):
        save_data(edited_loan, LOAN_FILE)
        st.rerun()