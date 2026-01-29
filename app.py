import streamlit as st
import pandas as pd
import requests
import time
import re
import altair as alt # 引入繪圖套件
from io import BytesIO

# --- 網頁設定 ---
st.set_page_config(page_title="Crypto 資金戰情室", layout="wide", page_icon="🏦")
st.title("🏦 Crypto 資金戰情室 (Pro Max)")

# ==========================================
# ⚠️ 請在此處填入你的 Google 試算表網址 ⚠️
# ==========================================
# 1. 交易紀錄分頁
TX_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# 2. 資金紀錄分頁
USDT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"

# ==========================================

# 1. 讀取資料函式
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
        df.columns = df.columns.str.strip() 
        
        def clean_number(value):
            if pd.isna(value): return 0
            val_str = str(value)
            clean_val = re.sub(r'[^\d.-]', '', val_str) 
            try:
                return float(clean_val)
            except:
                return 0

        if sheet_type == "usdt":
            required = ["投入台幣", "買入USDT"]
            if "TWD" in df.columns: df.rename(columns={"TWD": "投入台幣"}, inplace=True)
            if "USDT" in df.columns: df.rename(columns={"USDT": "買入USDT"}, inplace=True)
            for col in required:
                if col in df.columns:
                    df[col] = df[col].apply(clean_number)
                else:
                    df[col] = 0.0

        elif sheet_type == "tx":
            if "幣種" not in df.columns and "Coin" in df.columns: df.rename(columns={"Coin": "幣種"}, inplace=True)
            if "投入金額(U)" not in df.columns and "金額" in df.columns: df.rename(columns={"金額": "投入金額(U)"}, inplace=True)
            if "持有顆數" not in df.columns and "顆數" in df.columns: df.rename(columns={"顆數": "持有顆數"}, inplace=True)
            
            if "幣種" in df.columns:
                df["幣種"] = df["幣種"].astype(str).str.strip()
            
            for col in ["投入金額(U)", "持有顆數"]:
                if col in df.columns:
                    df[col] = df[col].apply(clean_number)
                else:
                    df[col] = 0.0
                    
        return df
    except Exception as e:
        return pd.DataFrame()

# 2. 自動搜尋 ID (快取 24 小時)
@st.cache_data(ttl=86400)
def find_coin_id(symbol):
    if not isinstance(symbol, str): return None
    clean_symbol = symbol.replace("$", "").strip().lower()
    search_url = f"https://api.coingecko.com/api/v3/search?query={clean_symbol}"
    headers = {"User-Agent": "Mozilla/5.0"} 
    try:
        time.sleep(1)
        res = requests.get(search_url, headers=headers, timeout=5).json()
        if "coins" in res and len(res["coins"]) > 0:
            return res["coins"][0]["id"]
        return None
    except:
        return None

# 3. 抓取幣價 (快取 10 分鐘)
@st.cache_data(ttl=600)
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
    
    for s in unknown_symbols:
        fid = find_coin_id(s)
        if fid: final_ids[s] = fid

    ids_list = list(set(final_ids.values()))
    if not ids_list: return {}

    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids_list)}&vs_currencies=usd"
    headers = {"User-Agent": "Mozilla/5.0"} 
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            prices = {}
            for sym, cid in final_ids.items():
                if cid in data:
                    prices[sym] = data[cid]['usd']
            return prices
        else:
            return {}
    except Exception:
        return {}

# ==========================================
# 主程式邏輯
# ==========================================

df_usdt = load_google_sheet(USDT_SHEET_URL, sheet_type="usdt")
df_tx = load_google_sheet(TX_SHEET_URL, sheet_type="tx")

if df_usdt.empty or df_tx.empty:
    st.warning("⚠️ 等待資料讀取中... 請確認兩個分頁的網址都已填入。")
    st.stop()

# 計算匯率
total_twd_in = df_usdt["投入台幣"].sum()
total_usdt_got = df_usdt["買入USDT"].sum()

if total_usdt_got > 0:
    avg_exchange_rate = total_twd_in / total_usdt_got
else:
    avg_exchange_rate = 32.5

# 處理交易資料
if not all(col in df_tx.columns for col in ["幣種", "投入金額(U)", "持有顆數"]):
    st.error("❌ 交易表缺少必要欄位 (幣種, 投入金額(U), 持有顆數)")
    st.stop()

# --- 側邊欄控制台 ---
with st.sidebar:
    st.header("⚙️ 控制台")
    manual_mode = st.toggle("🛠️ 啟用手動輸入幣價", value=False, help="當 API 無法抓到價格時，開啟此選項自行輸入價格")
    
    unique_coins = df_tx["幣種"].unique().tolist()
    unique_coins = [x for x in unique_coins if x != "nan" and x != "0"]
    
    current_prices = {}

    if manual_mode:
        st.info("💡 請在下方表格輸入目前幣價 (USDT)")
        api_prices = get_live_prices_auto(unique_coins)
        edit_data = []
        for coin in unique_coins:
            default_price = api_prices.get(coin, 0.0)
            edit_data.append({"幣種": coin, "自訂價格": default_price})
        edit_df = pd.DataFrame(edit_data)
        edited_df = st.data_editor(
            edit_df,
            hide_index=True,
            column_config={
                "幣種": st.column_config.TextColumn("幣種", disabled=True),
                "自訂價格": st.column_config.NumberColumn("價格 (U)", format="%.6f", min_value=0.0)
            }
        )
        current_prices = dict(zip(edited_df["幣種"], edited_df["自訂價格"]))
    else:
        if st.button("🔄 強制刷新 API 價格"):
            find_coin_id.clear()
            get_live_prices_auto.clear() 
            st.cache_data.clear()
            st.rerun()
            
        current_prices = get_live_prices_auto(unique_coins)
        if not current_prices:
            st.warning("⚠️ API 忙線中，價格顯示為 0。可切換上方開關改為手動輸入。")
        else:
            st.success("✅ API 連線正常")
        st.caption(f"上次更新: {time.strftime('%H:%M:%S')}")

# --- 核心計算 ---
clean_tx = df_tx[df_tx["幣種"].isin(unique_coins)].copy()
df_summary = clean_tx.groupby("幣種").agg({
    "投入金額(U)": "sum",
    "持有顆數": "sum"
}).reset_index()

df_summary["平均成本(U)"] = df_summary.apply(lambda x: x["投入金額(U)"] / x["持有顆數"] if x["持有顆數"] > 0 else 0, axis=1)
df_summary["目前幣價"] = df_summary["幣種"].map(current_prices).fillna(0)
df_summary["目前市值(U)"] = df_summary["持有顆數"] * df_summary["目前幣價"]
df_summary["損益金額(U)"] = df_summary["目前市值(U)"] - df_summary["投入金額(U)"]
df_summary["損益率"] = df_summary.apply(lambda x: (x["損益金額(U)"] / x["投入金額(U)"] * 100) if x["投入金額(U)"] > 0 else 0, axis=1)

total_invested_in_coins = df_summary["投入金額(U)"].sum()
total_portfolio_value = df_summary["目前市值(U)"].sum()

df_summary["投入佔比"] = df_summary.apply(lambda x: (x["投入金額(U)"] / total_invested_in_coins * 100) if total_invested_in_coins > 0 else 0, axis=1)
df_summary["市值佔比"] = df_summary.apply(lambda x: (x["目前市值(U)"] / total_portfolio_value * 100) if total_portfolio_value > 0 else 0, axis=1)

# ==========================================
# 視覺化顯示
# ==========================================

# --- 第一區：資金池 ---
st.subheader("💰 資金池與動態匯率")
col_a, col_b, col_c = st.columns(3)
col_a.metric("🇹🇼 總投入台幣本金", f"${total_twd_in:,.0f}")
col_b.metric("🇺🇸 總買入 USDT", f"${total_usdt_got:,.2f}")
col_c.metric("💱 真實平均匯率", f"{avg_exchange_rate:.2f} TWD/U")

st.markdown("---")

# --- 第二區：總持倉績效 ---
st.subheader("📈 總持倉績效")
total_pnl = df_summary["損益金額(U)"].sum()
total_roi = (total_pnl / total_invested_in_coins * 100) if total_invested_in_coins > 0 else 0
twd_pnl = total_pnl * avg_exchange_rate
twd_val = total_portfolio_value * avg_exchange_rate

m1, m2, m3 = st.columns(3)
m1.metric("總市值估算", f"${total_portfolio_value:,.2f} U", delta=f"≈ {twd_val:,.0f} TWD")
m2.metric("總損益金額", f"${total_pnl:,.2f} U", delta=f"≈ {twd_pnl:,.0f} TWD")
m3.metric("總損益率 (ROI)", f"{total_roi:.2f}%")

st.markdown("---")

# --- 第三區：圖表分析 (新增功能) ---
st.subheader("📊 資產分佈與損益分析")

# 準備圓餅圖數據
pie_data = df_summary[df_summary["投入金額(U)"] > 0].copy()

# 圓餅圖 1：投入資金佔比
pie_cost = alt.Chart(pie_data).mark_arc(innerRadius=50, outerRadius=120).encode(
    theta=alt.Theta("投入金額(U)", stack=True),
    color=alt.Color("幣種", legend=alt.Legend(title="幣種")),
    order=alt.Order("投入金額(U)", sort="descending"),
    tooltip=["幣種", alt.Tooltip("投入金額(U)", format=",.2f"), alt.Tooltip("投入佔比", format=".1f", title="佔比(%)")]
).properties(title="🟠 總投入資金佔比 (Cost)")

# 圓餅圖 2：目前市值佔比
pie_market = alt.Chart(pie_data).mark_arc(innerRadius=50, outerRadius=120).encode(
    theta=alt.Theta("目前市值(U)", stack=True),
    color=alt.Color("幣種", legend=alt.Legend(title="幣種")),
    order=alt.Order("目前市值(U)", sort="descending"),
    tooltip=["幣種", alt.Tooltip("目前市值(U)", format=",.2f"), alt.Tooltip("市值佔比", format=".1f", title="佔比(%)")]
).properties(title="🔵 目前市值持倉佔比 (Market)")

# 顯示圓餅圖
col_pie1, col_pie2 = st.columns(2)
with col_pie1:
    st.altair_chart(pie_cost, use_container_width=True)
with col_pie2:
    st.altair_chart(pie_market, use_container_width=True)

# 直方圖：損益分析
st.markdown("#### 🔻 損益分析 (PnL)")
bar_data = df_summary.copy()

# 直方圖 1：損益金額
bar_amt = alt.Chart(bar_data).mark_bar().encode(
    x=alt.X("幣種", sort="-y"),
    y=alt.Y("損益金額(U)", title="損益金額 (U)"),
    color=alt.condition(
        alt.datum['損益金額(U)'] > 0,
        alt.value("#28a745"),  # 綠色
        alt.value("#dc3545")   # 紅色
    ),
    tooltip=["幣種", alt.Tooltip("損益金額(U)", format=",.2f")]
).properties(title="💵 各幣種損益金額 (Amount)")

# 直方圖 2：損益率
bar_pct = alt.Chart(bar_data).mark_bar().encode(
    x=alt.X("幣種", sort="-y"),
    y=alt.Y("損益率", title="損益率 (%)"),
    color=alt.condition(
        alt.datum['損益率'] > 0,
        alt.value("#28a745"),  # 綠色
        alt.value("#dc3545")   # 紅色
    ),
    tooltip=["幣種", alt.Tooltip("損益率", format=".2f", title="損益率(%)")]
).properties(title="📈 各幣種損益率 (ROI %)")

# 顯示直方圖
col_bar1, col_bar2 = st.columns(2)
with col_bar1:
    st.altair_chart(bar_amt, use_container_width=True)
with col_bar2:
    st.altair_chart(bar_pct, use_container_width=True)

st.markdown("---")

# --- 第四區：幣種詳細分析表格 ---
st.subheader("📋 詳細數據清單")

display_df = df_summary[[
    "幣種", 
    "投入金額(U)", "平均成本(U)", "持有顆數", "投入佔比", 
    "目前市值(U)", "目前幣價", "市值佔比", 
    "損益率", "損益金額(U)"
]].copy()

display_df = display_df.sort_values("目前市值(U)", ascending=False).reset_index(drop=True)
display_df.index = display_df.index + 1

st.dataframe(
    display_df,
    use_container_width=True,
    column_config={
        "幣種": st.column_config.TextColumn("幣種", width="small"),
        
        "投入金額(U)": st.column_config.NumberColumn("總投入資金 (U)", format="$%.2f"),
        "平均成本(U)": st.column_config.NumberColumn("投入均價", format="%.6f"),
        "持有顆數": st.column_config.NumberColumn("持有顆數", format="%.2f"),
        
        "投入佔比": st.column_config.ProgressColumn(
            "資金佔比",
            format="%.1f%%", 
            min_value=0, max_value=100,
        ),

        "目前市值(U)": st.column_config.NumberColumn("目前市值 (U)", format="$%.2f"),
        "目前幣價": st.column_config.NumberColumn("現價", format="%.6f"),
        
        "市值佔比": st.column_config.ProgressColumn(
            "持倉佔比", 
            format="%.1f%%", 
            min_value=0, max_value=100,
        ),
        
        "損益率": st.column_config.NumberColumn(
            "損益率 (%)", 
            format="%.2f%%"
        ),
        "損益金額(U)": st.column_config.NumberColumn("損益金額 (U)", format="$%.2f")
    }
)