import streamlit as st
import pandas as pd
import requests
import time
import re # 引入正規表達式來處理 "200u" 這種字串
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

# 1. 讀取資料函式 (增強版：智慧欄位對應 + 資料清洗)
def load_google_sheet(url, sheet_type="tx"):
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
        df.columns = df.columns.str.strip() # 去除標題空白
        
        # --- 智慧欄位對應 ---
        if sheet_type == "tx":
            # 處理幣種
            if "幣種" not in df.columns:
                for col in ["Coin", "Symbol", "購買幣種"]:
                    if col in df.columns:
                        df.rename(columns={col: "幣種"}, inplace=True)
                        break
            # 處理金額
            if "投入金額(U)" not in df.columns:
                for col in ["金額", "Amount", "投入金額", "USDT"]:
                    if col in df.columns:
                        df.rename(columns={col: "投入金額(U)"}, inplace=True)
                        break
            # 處理顆數
            if "持有顆數" not in df.columns:
                for col in ["顆數", "Qty", "Quantity", "數量"]:
                    if col in df.columns:
                        df.rename(columns={col: "持有顆數"}, inplace=True)
                        break

            # --- 資料清洗防呆 (解決 "200u" 問題) ---
            def clean_number(value):
                # 把不是數字和小數點的東西都刪掉
                if pd.isna(value): return 0
                val_str = str(value)
                # 只保留數字、負號和小數點
                clean_val = re.sub(r'[^\d.-]', '', val_str) 
                try:
                    return float(clean_val)
                except:
                    return 0

            if "幣種" in df.columns:
                df["幣種"] = df["幣種"].astype(str).str.strip()
            
            for col in ["投入金額(U)", "持有顆數"]:
                if col in df.columns:
                    # 套用清洗函式
                    df[col] = df[col].apply(clean_number)
                else:
                    df[col] = 0.0 # 缺欄位補 0
                    
        return df
    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        return pd.DataFrame()

# 2. 自動搜尋 ID
@st.cache_data(ttl=86400)
def find_coin_id(symbol):
    if not isinstance(symbol, str): return None
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
        if not isinstance(s, str): continue
        clean_s = s.strip().upper()
        match = None
        for k, v in known_mapping.items():
            if k.upper() == clean_s:
                match = v
                break
        
        if match:
            final_ids[s] = match
        else:
            unknown_symbols.append(s)
    
    if unknown_symbols:
        # 使用 spinner 避免畫面跳動
        with st.spinner(f"🔍 搜尋新幣種 ID..."):
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

# 4. 文字變色函式 (替代原本的漸層色，解決 ImportError)
def color_pnl(val):
    """
    數值 > 0 : 綠色
    數值 < 0 : 紅色
    數值 = 0 : 黑色
    """
    if isinstance(val, (int, float)):
        if val > 0:
            return 'color: #28a745; font-weight: bold;' # 綠色
        elif val < 0:
            return 'color: #dc3545; font-weight: bold;' # 紅色
    return ''

# ==========================================
# 主程式邏輯
# ==========================================

df_loan = load_google_sheet(LOAN_SHEET_URL, sheet_type="loan")
df_tx = load_google_sheet(CRYPTO_SHEET_URL, sheet_type="tx")

if df_loan.empty or df_tx.empty:
    st.warning("⚠️ 等待資料讀取中... 請確認網址正確。")
    st.stop()

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 設定與報價")
    twd_rate = st.number_input("🇺🇸 USDT / 🇹🇼 TWD 匯率", value=32.50, step=0.1, format="%.2f")
    
    if st.button("🔄 刷新最新幣價"):
        find_coin_id.clear()
        st.cache_data.clear()
        st.rerun()

    if "幣種" in df_tx.columns:
        unique_coins = df_tx["幣種"].unique().tolist()
        current_prices = get_live_prices_auto(unique_coins)
        
        st.write("---")
        st.write("📊 即時單價 (CoinGecko):")
        for coin, p in current_prices.items():
            st.write(f"**{coin}**: ${p}")

# --- 資料計算 ---

# 1. 計算每一筆的「購入單價」
df_tx["購入單價"] = df_tx.apply(lambda x: x["投入金額(U)"] / x["持有顆數"] if x["持有顆數"] > 0 else 0, axis=1)

# 2. 彙整 (Group By)
clean_tx = df_tx[df_tx["幣種"] != "0"].copy()
clean_tx = clean_tx[clean_tx["幣種"] != "nan"]

df_summary = clean_tx.groupby("幣種").agg({
    "投入金額(U)": "sum",
    "持有顆數": "sum"
}).reset_index()

# 3. 計算平均成本與市值
df_summary["平均成本(U)"] = df_summary.apply(lambda x: x["投入金額(U)"] / x["持有顆數"] if x["持有顆數"] > 0 else 0, axis=1)
df_summary["目前幣價"] = df_summary["幣種"].map(current_prices).fillna(0)
df_summary["目前市值(U)"] = df_summary["持有顆數"] * df_summary["目前幣價"]
df_summary["損益金額(U)"] = df_summary["目前市值(U)"] - df_summary["投入金額(U)"]
df_summary["損益率(%)"] = df_summary.apply(lambda x: (x["損益金額(U)"] / x["投入金額(U)"] * 100) if x["投入金額(U)"] > 0 else 0, axis=1)

# 4. 計算佔比
total_invested = df_summary["投入金額(U)"].sum()
current_total_value = df_summary["目前市值(U)"].sum()
df_summary["持倉佔比(%)"] = df_summary.apply(lambda x: (x["目前市值(U)"] / current_total_value * 100) if current_total_value > 0 else 0, axis=1)

# 5. 總資金池
loan_total = 0
if "總資金(USDT)" in df_loan.columns:
    # 同樣套用清洗函式
    clean_loan = re.sub(r'[^\d.-]', '', str(df_loan["總資金(USDT)"].iloc[0]))
    try:
        loan_total = float(clean_loan)
    except:
        loan_total = 0

# ==========================================
# 頁面顯示
# ==========================================

tab1, tab2 = st.tabs(["📈 總資產看板 (彙整)", "📝 交易明細 (清單)"])

with tab1:
    st.subheader("💰 總持倉價值與損益")
    
    remaining_ammo = loan_total - total_invested
    total_pnl = df_summary["損益金額(U)"].sum()
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("總持倉價值 (USDT)", f"${current_total_value:,.2f}")
    c2.metric("總損益金額 (USDT)", f"${total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
    c3.metric("總損益率 (%)", f"{total_pnl_pct:.2f}%", delta=f"{total_pnl_pct:.2f}%")
    c4.metric("剩餘子彈 (USDT)", f"${remaining_ammo:,.2f}")

    st.markdown("---")
    
    st.caption(f"💡 台幣計算基準：1 USDT = {twd_rate} TWD")
    twd_val = current_total_value * twd_rate
    twd_pnl = total_pnl * twd_rate
    
    c5, c6 = st.columns(2)
    c5.metric("🇹🇼 總持倉價值 (台幣)", f"NT$ {twd_val:,.0f}")
    c6.metric("🇹🇼 總損益金額 (台幣)", f"NT$ {twd_pnl:,.0f}", delta=f"{twd_pnl:,.0f}")
    
    st.markdown("---")
    
    st.subheader("📊 各幣種持倉表現")
    
    display_df = df_summary[[
        "幣種", "目前幣價", "持有顆數", "平均成本(U)", 
        "投入金額(U)", "目前市值(U)", "損益金額(U)", "損益率(%)", "持倉佔比(%)"
    ]].copy()
    
    display_df = display_df.sort_values("目前市值(U)", ascending=False).reset_index(drop=True)
    display_df.index = display_df.index + 1

    # 這裡做了關鍵修改：使用 applymap 而不是 background_gradient
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
        }).applymap(color_pnl, subset=["損益率(%)", "損益金額(U)"]),
        use_container_width=True
    )

with tab2:
    st.subheader("🧾 購買清單與合計")
    st.info("💡 資料來源：Google 試算表。若數值異常，程式已自動過濾文字 (例如 '200u' -> 200)。")
    
    if "幣種" in df_tx.columns:
        all_coins = ["全部"] + sorted(df_tx["幣種"].astype(str).unique().tolist())
        selected_coin = st.selectbox("🔍 篩選幣種", all_coins)
        
        if selected_coin == "全部":
            filtered_tx = df_tx.copy()
        else:
            filtered_tx = df_tx[df_tx["幣種"] == selected_coin].copy()

        filtered_tx.index = filtered_tx.index + 1
        st.dataframe(
            filtered_tx.style.format({
                "投入金額(U)": "{:,.2f}",
                "持有顆數": "{:,.2f}",
                "購入單價": "{:.6f}"
            }),
            use_container_width=True
        )
        
        if selected_coin != "全部" and not df_summary.empty:
            if selected_coin in df_summary["幣種"].values:
                coin_sum = df_summary[df_summary["幣種"] == selected_coin].iloc[0]
                st.markdown(f"**👉 {selected_coin} 合計：**")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("總投入", f"${coin_sum['投入金額(U)']:,.2f}")
                col2.metric("總顆數", f"{coin_sum['持有顆數']:,.2f}")
                col3.metric("平均成本", f"${coin_sum['平均成本(U)']:,.6f}")
                col4.metric("目前損益", f"${coin_sum['損益金額(U)']:,.2f}", delta=f"{coin_sum['損益率(%)']:.2f}%")