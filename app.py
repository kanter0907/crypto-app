import streamlit as st
import pandas as pd
import requests
import time
from io import BytesIO

# --- 網頁設定 ---
st.set_page_config(page_title="Crypto 專業投資看板", layout="wide", page_icon="📊")
st.title("📊 Crypto 專業投資看板 (交易明細版)")

# ==========================================
# ⚠️ 請在此處填入你的 Google 試算表網址 ⚠️
# ==========================================
LOAN_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"
CRYPTO_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# ==========================================

# 1. 讀取資料函式
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
        
        # 針對 Crypto 表的特殊處理
        if "幣種" in df.columns:
            df["幣種"] = df["幣種"].astype(str).str.strip()
            # 確保數值欄位是數字
            for col in ["投入金額(U)", "持有顆數"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    
        return df
    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        return pd.DataFrame()

# 2. 自動搜尋 ID
@st.cache_data(ttl=86400)
def find_coin_id(symbol):
    clean_symbol = symbol.replace("$", "").strip().lower()
    search_url = f"https://api.coingecko.com/api/v3/search?query={clean_symbol}"
    headers = {"User-Agent": "Mozilla/5.0"} 
    try:
        time.sleep(0.5)
        res = requests.get(search_url, headers=headers, timeout=5).json()
        if "coins" in res and len(res["coins"]) > 0:
            return res["coins"][0]["id"]
        return None
    except:
        return None

# 3. 抓取幣價
def get_live_prices_auto(symbols):
    known_mapping = {
        "$ADA": "cardano", "$NIGHT": "midnight-3", "$SNEK": "snek",
        "$USDT": "tether", "$BTC": "bitcoin", "$ETH": "ethereum",
        "$SOL": "solana", "$XRP": "ripple", "$DOGE": "dogecoin",
        "$BNB": "binancecoin", "$PEPE": "pepe"
    }
    
    final_ids = {}
    unknown_symbols = []

    for s in symbols:
        clean_s = s.strip().upper()
        # 簡單比對
        match = None
        for k, v in known_mapping.items():
            if k.upper() == clean_s:
                match = v
                break
        
        if match:
            final_ids[s] = match
        else:
            unknown_symbols.append(s)
    
    # 自動搜尋
    if unknown_symbols:
        with st.sidebar:
            st.info(f"🔍 搜尋新幣種 ID: {unknown_symbols}")
            for s in unknown_symbols:
                fid = find_coin_id(s)
                if fid: final_ids[s] = fid

    ids_list = list(set(final_ids.values()))
    if not ids_list: return {}

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids_list)}&vs_currencies=usd"
    headers = {"User-Agent": "Mozilla/5.0"} 
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
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

df_loan = load_google_sheet(LOAN_SHEET_URL)
df_tx = load_google_sheet(CRYPTO_SHEET_URL) # 這裡是讀取交易清單

if df_loan.empty or df_tx.empty:
    st.warning("⚠️ 請檢查網址或確認 Google 試算表欄位名稱是否正確 (幣種, 投入金額(U), 持有顆數)")
    st.stop()

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("⚙️ 設定與報價")
    
    # 匯率輸入
    twd_rate = st.number_input("🇺🇸 USDT / 🇹🇼 TWD 匯率", value=32.50, step=0.1, format="%.2f")
    
    if st.button("🔄 刷新最新幣價"):
        find_coin_id.clear()
        st.cache_data.clear()
        st.rerun()

    # 取得幣價
    unique_coins = df_tx["幣種"].unique().tolist()
    current_prices = get_live_prices_auto(unique_coins)
    
    st.write("---")
    st.write("📊 即時單價 (CoinGecko):")
    for coin, p in current_prices.items():
        st.write(f"**{coin}**: ${p}")

# --- 資料處理與計算 ---

# 1. 計算每一筆的「購入單價」
df_tx["購入單價"] = df_tx.apply(lambda x: x["投入金額(U)"] / x["持有顆數"] if x["持有顆數"] > 0 else 0, axis=1)

# 2. 彙整 (Group By) 算出持倉總表
df_summary = df_tx.groupby("幣種").agg({
    "投入金額(U)": "sum",
    "持有顆數": "sum"
}).reset_index()

# 3. 計算平均成本與市值
df_summary["平均成本(U)"] = df_summary["投入金額(U)"] / df_summary["持有顆數"]
df_summary["目前幣價"] = df_summary["幣種"].map(current_prices).fillna(0)
df_summary["目前市值(U)"] = df_summary["持有顆數"] * df_summary["目前幣價"]
df_summary["損益金額(U)"] = df_summary["目前市值(U)"] - df_summary["投入金額(U)"]
df_summary["損益率(%)"] = (df_summary["損益金額(U)"] / df_summary["投入金額(U)"]) * 100

# 4. 計算佔比
total_invested = df_summary["投入金額(U)"].sum()
current_total_value = df_summary["目前市值(U)"].sum()
df_summary["持倉佔比(%)"] = (df_summary["目前市值(U)"] / current_total_value) * 100

# 5. 總資金池 (從 Loan 表抓)
loan_total = 0
if "總資金(USDT)" in df_loan.columns:
    loan_total = pd.to_numeric(df_loan["總資金(USDT)"].iloc[0], errors='coerce')

# ==========================================
# 頁面顯示
# ==========================================

# 建立兩個分頁
tab1, tab2 = st.tabs(["📈 總資產看板 (彙整)", "📝 交易明細 (清單)"])

with tab1:
    st.subheader("💰 總持倉價值與損益")
    
    # 核心指標 (USDT)
    remaining_ammo = loan_total - total_invested
    total_pnl = df_summary["損益金額(U)"].sum()
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總持倉價值 (USDT)", f"${current_total_value:,.2f}")
    c2.metric("總損益金額 (USDT)", f"${total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
    c3.metric("總損益率 (%)", f"{total_pnl_pct:.2f}%", delta=f"{total_pnl_pct:.2f}%")
    c4.metric("剩餘子彈 (USDT)", f"${remaining_ammo:,.2f}")

    st.markdown("---")
    
    # 核心指標 (TWD) - 根據使用者輸入的匯率
    st.caption(f"💡 台幣計算基準：1 USDT = {twd_rate} TWD")
    twd_val = current_total_value * twd_rate
    twd_pnl = total_pnl * twd_rate
    
    c5, c6 = st.columns(2)
    c5.metric("🇹🇼 總持倉價值 (台幣)", f"NT$ {twd_val:,.0f}")
    c6.metric("🇹🇼 總損益金額 (台幣)", f"NT$ {twd_pnl:,.0f}", delta=f"{twd_pnl:,.0f}")
    
    st.markdown("---")
    
    st.subheader("📊 各幣種持倉表現")
    
    # 整理顯示欄位
    display_df = df_summary[[
        "幣種", "目前幣價", "持有顆數", "平均成本(U)", 
        "投入金額(U)", "目前市值(U)", "損益金額(U)", "損益率(%)", "持倉佔比(%)"
    ]].copy()
    
    # 排序 (按市值大到小)
    display_df = display_df.sort_values("目前市值(U)", ascending=False).reset_index(drop=True)
    display_df.index = display_df.index + 1 # 序號從 1 開始

    st.dataframe(
        display_df.style.format({
            "目前幣價": "{:.6f}",
            "持有顆數": "{:,.2f}",
            "平均成本(U)": "{:.6f}",
            "投入金額(U)": "{:,.2f}",
            "目前市值(U)": "{:,.2f}",
            "損益金額(U)": "{:,.2f}",
            "損益率(%)": "{:+.2f}%",
            "持倉佔比(%)": "{:.1f}%"
        }).background_gradient(subset=["損益率(%)"], cmap="RdYlGn", vmin=-50, vmax=50),
        use_container_width=True
    )

with tab2:
    st.subheader("🧾 購買清單與合計")
    st.info("💡 此處顯示 Google 試算表中紀錄的每一筆交易。若要新增，請至 Google Sheets 新增一行。")
    
    # 讓使用者選擇幣種來查看細節 (類似 Excel 的分類)
    all_coins = ["全部"] + sorted(unique_coins)
    selected_coin = st.selectbox("🔍 篩選幣種", all_coins)
    
    if selected_coin == "全部":
        filtered_tx = df_tx.copy()
    else:
        filtered_tx = df_tx[df_tx["幣種"] == selected_coin].copy()

    # 顯示交易明細
    filtered_tx.index = filtered_tx.index + 1
    st.dataframe(
        filtered_tx.style.format({
            "投入金額(U)": "{:,.2f}",
            "持有顆數": "{:,.2f}",
            "購入單價": "{:.6f}"
        }),
        use_container_width=True
    )
    
    # 如果選了特定幣種，顯示該幣種的合計列 (模仿 Excel 效果)
    if selected_coin != "全部":
        coin_sum = df_summary[df_summary["幣種"] == selected_coin].iloc[0]
        st.markdown(f"**👉 {selected_coin} 合計：**")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("總投入金額", f"${coin_sum['投入金額(U)']:,.2f}")
        col2.metric("總持有顆數", f"{coin_sum['持有顆數']:,.2f}")
        col3.metric("平均成本", f"${coin_sum['平均成本(U)']:,.6f}")
        col4.metric("目前損益", f"${coin_sum['損益金額(U)']:,.2f}", delta=f"{coin_sum['損益率(%)']:.2f}%")