import streamlit as st
import pandas as pd
import requests
import time
from io import BytesIO

# --- 網頁設定 ---
st.set_page_config(page_title="Crypto 智慧資產管理", layout="wide", page_icon="🤖")
st.title("🤖 Crypto 智慧資產管理系統 (自動偵測新幣種)")

# ==========================================
# ⚠️ 請在此處填入你的 Google 試算表網址 ⚠️
# ==========================================
LOAN_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"
CRYPTO_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# ==========================================

# 1. 讀取 Google Sheets (維持不變)
def load_google_sheet(url):
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
        return df
    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        return pd.DataFrame()

# --- 🧠 核心功能：自動搜尋 CoinGecko ID ---
# 使用 cache_data 避免每次重整都重新搜尋 (節省 API 額度)
@st.cache_data(ttl=86400)  # 搜尋結果快取 24 小時
def find_coin_id(symbol):
    """
    輸入幣種名稱 (例如 'DOGE' 或 '$DOGE')，
    自動去 CoinGecko 搜尋並回傳最可能的 ID。
    """
    clean_symbol = symbol.replace("$", "").strip().lower()
    
    # 搜尋 API
    search_url = f"https://api.coingecko.com/api/v3/search?query={clean_symbol}"
    
    try:
        # 為了避免太快觸發 API 限制，稍微休息 0.5 秒
        time.sleep(0.5)
        response = requests.get(search_url, timeout=5)
        data = response.json()
        
        # 檢查是否有搜尋結果
        if "coins" in data and len(data["coins"]) > 0:
            # 取第一個結果 (通常是最熱門的那個)
            found_id = data["coins"][0]["id"]
            return found_id
        else:
            return None
    except:
        return None

# --- 抓取幣價 (升級版) ---
def get_live_prices_auto(symbols):
    # 1. 預設的已知清單 (常用的先寫好，速度比較快)
    known_mapping = {
        "$ADA": "cardano", "$Night": "night-verse", "$SNEK": "snek",
        "$USDT": "tether", "$BTC": "bitcoin", "$ETH": "ethereum",
        "$SOL": "solana", "$XRP": "ripple", "$DOGE": "dogecoin",
        "$BNB": "binancecoin"
    }
    
    final_ids = {}
    unknown_symbols = []

    # 2. 分類：哪些是已知的，哪些是新幣？
    for s in symbols:
        if s in known_mapping:
            final_ids[s] = known_mapping[s]
        else:
            unknown_symbols.append(s)
    
    # 3. 對於未知的新幣，啟動自動搜尋
    if unknown_symbols:
        status_text = st.empty() # 建立一個空元件顯示進度
        status_text.info(f"🔍 發現新幣種 {unknown_symbols}，正在嘗試自動搜尋 ID...")
        
        for s in unknown_symbols:
            found_id = find_coin_id(s)
            if found_id:
                final_ids[s] = found_id
            else:
                st.warning(f"⚠️ 找不到 {s} 的資料，請確認拼字正確。")
        
        status_text.empty() # 搜尋完清空提示

    # 4. 統一抓取價格
    ids_list = list(final_ids.values())
    if not ids_list: return {}

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids_list)}&vs_currencies=usd"
    
    try:
        res = requests.get(url, timeout=10).json()
        # 回傳格式：{"$DOGE": 0.12, "$BTC": 60000}
        prices = {}
        for sym, cid in final_ids.items():
            if cid in res:
                prices[sym] = res[cid]['usd']
        return prices
    except:
        return {}

# ==========================================
# 主程式邏輯
# ==========================================

# 1. 載入資料
df_loan = load_google_sheet(LOAN_SHEET_URL)
df_crypto = load_google_sheet(CRYPTO_SHEET_URL)

if df_loan.empty or df_crypto.empty:
    st.warning("⚠️ 讀取中斷，請檢查網址。")
    st.stop()

# 2. 側邊欄
with st.sidebar:
    st.header("⚡ 控制台")
    if st.button("🔄 刷新最新幣價"):
        # 清除快取，強制重新搜尋 (如果想更新搜尋結果可以按這個)
        find_coin_id.clear()
        st.cache_data.clear()
        st.rerun()
    
    # 這裡使用新的自動抓價函式
    current_prices = get_live_prices_auto(df_crypto["幣種"].tolist())
    
    st.write("---")
    st.write("📊 即時報價 (來源: CoinGecko)")
    for coin, p in current_prices.items():
        st.write(f"**{coin}**: ${p}")

# 3. 數據計算與看板
try:
    st.subheader("📊 智慧資產看板")
    
    # --- 格式轉換 ---
    cols = ["持有顆數", "平均成本(U)", "當前市價(U)"]
    for c in cols:
        if c in df_crypto.columns:
            df_crypto[c] = pd.to_numeric(df_crypto[c], errors='coerce').fillna(0)
    
    # --- 更新單價 ---
    for i, row in df_crypto.iterrows():
        if row['幣種'] in current_prices:
            df_crypto.at[i, '當前市價(U)'] = current_prices[row['幣種']]

    # --- 欄位改名與計算 (你要求的第 3 點) ---
    # A. 改名：原本的「當前市價(U)」變成「目前幣價」
    df_crypto.rename(columns={"當前市價(U)": "目前幣價"}, inplace=True)

    # B. 新增：總價值欄位
    df_crypto["當前市價(U)"] = df_crypto["持有顆數"] * df_crypto["目前幣價"]

    # --- 核心指標 ---
    total_pool = pd.to_numeric(df_loan["總資金(USDT)"].iloc[0], errors='coerce')
    invested = (df_crypto["持有顆數"] * df_crypto["平均成本(U)"]).sum()
    remaining = total_pool - invested
    market_val = df_crypto["當前市價(U)"].sum()
    pnl = market_val - invested
    
    # --- 顯示 ---
    c1, c2, c3 = st.columns(3)
    c1.metric("總資金池", f"${total_pool:,.2f}")
    c2.metric("已投入成本", f"${invested:,.2f}")
    c3.metric("剩餘子彈", f"${remaining:,.2f}", delta=f"{remaining:,.2f}")
    
    st.markdown("---")
    c4, c5 = st.columns(2)
    c4.metric("持倉總市值", f"${market_val:,.2f}")
    c5.metric("未實現損益", f"${pnl:,.2f}", delta=f"{pnl:,.2f}")
    
    # --- 詳細清單 ---
    st.subheader("📋 持倉詳細清單")
    
    # 調整欄位順序：把重要資訊放前面
    target_cols = ["幣種", "持有顆數", "平均成本(U)", "目前幣價", "當前市價(U)"]
    other_cols = [c for c in df_crypto.columns if c not in target_cols]
    final_df = df_crypto[target_cols + other_cols]

    st.dataframe(
        final_df.style.format({
            "持有顆數": "{:,.2f}", 
            "平均成本(U)": "{:.6f}",
            "目前幣價": "{:.6f}",     # 單價
            "當前市價(U)": "{:,.2f}"  # 總價值
        }), 
        use_container_width=True
    )

except Exception as e:
    st.error(f"計算時發生錯誤: {e}")