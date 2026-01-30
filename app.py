import streamlit as st
import pandas as pd
import requests
import time
import re
import altair as alt
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

# 4. 抓取 USDT/TWD 匯率 (改用 BitoPro API)
@st.cache_data(ttl=600)
def get_usdt_twd_rate():
    # 來源：BitoPro 台灣幣託交易所 (公開 API，穩定且準確)
    url = "https://api.bitopro.com/v3/tickers/usdt_twd"
    headers = {"User-Agent": "Mozilla/5.0"} 
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            # BitoPro 回傳格式: {'data': {'lastPrice': '32.45', ...}}
            return float(data.get("data", {}).get("lastPrice", 0))
    except:
        pass
    return None

# ==========================================
# 主程式邏輯
# ==========================================

# 1. 讀取資料
df_usdt = load_google_sheet(USDT_SHEET_URL, sheet_type="usdt")
df_tx = load_google_sheet(TX_SHEET_URL, sheet_type="tx")

# 2. 預先初始化變數 (防止 NameError)
avg_exchange_rate = 32.5
total_twd_in = 0
total_usdt_got = 0

# 3. 檢查資料並計算匯率
if not df_usdt.empty:
    try:
        total_twd_in = df_usdt["投入台幣"].sum()
        total_usdt_got = df_usdt["買入USDT"].sum()
        
        if total_usdt_got > 0:
            avg_exchange_rate = total_twd_in / total_usdt_got
    except Exception:
        pass

if df_usdt.empty and df_tx.empty:
    st.warning("⚠️ 等待資料讀取中... 請確認兩個分頁的網址都已填入。")
    st.stop()

# 4. 檢查交易表欄位
if not df_tx.empty:
    if not all(col in df_tx.columns for col in ["幣種", "投入金額(U)", "持有顆數"]):
        st.error("❌ 交易表缺少必要欄位 (幣種, 投入金額(U), 持有顆數)")
        st.stop()

# --- 側邊欄控制台 ---
with st.sidebar:
    st.header("⚙️ 控制台")
    
    # --- 匯率設定 ---
    st.subheader("💱 匯率設定")
    fx_mode = st.radio(
        "選擇台幣換算匯率來源",
        ["自動 (BitoPro)", "手動輸入", "使用平均成本匯率"], 
        index=0,
        help="自動模式將從台灣 BitoPro 交易所抓取即時 USDT/TWD 價格"
    )
    
    current_fx_rate = avg_exchange_rate # 預設值
    
    if fx_mode == "自動 (BitoPro)":
        fetched_rate = get_usdt_twd_rate()
        if fetched_rate and fetched_rate > 0:
            current_fx_rate = fetched_rate
            st.success(f"BitoPro: {current_fx_rate:.2f}")
        else:
            st.warning("BitoPro 連線失敗，暫用平均成本匯率")
            
    elif fx_mode == "手動輸入":
        current_fx_rate = st.number_input("請輸入 USDT/TWD 匯率", value=32.50, step=0.01, format="%.2f")
    
    elif fx_mode == "使用平均成本匯率":
        current_fx_rate = avg_exchange_rate
        st.info(f"成本匯率: {current_fx_rate:.2f}")

    st.markdown("---")
    
    # --- 幣價設定 ---
    st.subheader("🪙 幣價設定")
    manual_mode = st.toggle("🛠️ 啟用手動輸入幣價", value=False)
    
    unique_coins = []
    if not df_tx.empty:
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
            get_usdt_twd_rate.clear()
            st.cache_data.clear()
            st.rerun()
            
        current_prices = get_live_prices_auto(unique_coins)
        if not current_prices:
            st.warning("⚠️ API 忙線中，價格顯示為 0。可切換上方開關改為手動輸入。")
        else:
            st.success("✅ API 連線正常")
        st.caption(f"上次更新: {time.strftime('%H:%M:%S')}")

# --- 核心計算 ---
if not df_tx.empty:
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
else:
    df_summary = pd.DataFrame()
    total_invested_in_coins = 0
    total_portfolio_value = 0

# ==========================================
# 視覺化顯示
# ==========================================

# --- 第一區：資金池 ---
st.subheader("💰 資金池與動態匯率")
col_a, col_b, col_c = st.columns(3)
col_a.metric("🇹🇼 總投入台幣本金", f"${total_twd_in:,.0f}")
col_b.metric("🇺🇸 總買入 USDT", f"${total_usdt_got:,.2f}")
col_c.metric("💱 平均買入成本匯率", f"{avg_exchange_rate:.2f} TWD/U", help="這是您投入資金的歷史平均匯率")

st.markdown("---")

# --- 第二區：總持倉績效 ---
st.subheader("📈 總持倉績效")

total_pnl_usdt = 0
total_roi = 0
if not df_summary.empty:
    total_pnl_usdt = df_summary["損益金額(U)"].sum()
    total_roi = (total_pnl_usdt / total_invested_in_coins * 100) if total_invested_in_coins > 0 else 0

# 計算台幣實際損益 (市值*目前匯率 - 總投入本金)
current_twd_value = total_portfolio_value * current_fx_rate
net_twd_pnl = current_twd_value - total_twd_in 

# 顯示用 (USDT損益換算)
twd_pnl_display = total_pnl_usdt * current_fx_rate

m1, m2, m3 = st.columns(3)

# 指標 1: 總市值估算
m1.metric(
    "總市值估算", 
    f"${total_portfolio_value:,.2f} U", 
    delta=f"{net_twd_pnl:,.0f} TWD (實際損益)",
    help=f"台幣估值使用匯率: {current_fx_rate:.2f}"
)

# 指標 2: 總損益金額
m2.metric(
    "總損益金額 (U)", 
    f"${total_pnl_usdt:,.2f} U", 
    delta=f"{twd_pnl_display:,.0f} TWD (估算)",
    help="USDT 損益換算台幣"
)

# 指標 3: ROI
m3.metric("總損益率 (ROI)", f"{total_roi:.2f}%")

st.markdown("---")

# --- 第三區：圖表分析 (Altair) ---
st.subheader("📊 資產分佈與損益分析")

if not df_summary.empty and total_invested_in_coins > 0:
    pie_data = df_summary[df_summary["投入金額(U)"] > 0].copy()

    # 1. 圓餅圖：投入資金佔比 (數值在內部)
    base_pie = alt.Chart(pie_data).encode(theta=alt.Theta("投入金額(U)", stack=True))
    pie_cost_arc = base_pie.mark_arc(innerRadius=40, outerRadius=120).encode(
        color=alt.Color("幣種", scale=alt.Scale(scheme='category10'), legend=alt.Legend(title="幣種")),
        order=alt.Order("投入金額(U)", sort="descending"),
        tooltip=["幣種", alt.Tooltip("投入金額(U)", format=",.2f"), alt.Tooltip("投入佔比", format=".1f", title="佔比(%)")]
    )
    pie_cost_text = base_pie.mark_text(radius=80).encode(
        text=alt.Text("投入佔比", format=".1f"),
        order=alt.Order("投入金額(U)", sort="descending"),
        color=alt.value("white") 
    )
    chart_cost = (pie_cost_arc + pie_cost_text).properties(title="🟠 投入資金佔比 (Cost %)")

    # 2. 圓餅圖：市值佔比 (數值在內部)
    base_pie_mkt = alt.Chart(pie_data).encode(theta=alt.Theta("目前市值(U)", stack=True))
    pie_mkt_arc = base_pie_mkt.mark_arc(innerRadius=40, outerRadius=120).encode(
        color=alt.Color("幣種", scale=alt.Scale(scheme='category10'), legend=None),
        order=alt.Order("目前市值(U)", sort="descending"),
        tooltip=["幣種", alt.Tooltip("目前市值(U)", format=",.2f"), alt.Tooltip("市值佔比", format=".1f", title="佔比(%)")]
    )
    pie_mkt_text = base_pie_mkt.mark_text(radius=80).encode(
        text=alt.Text("市值佔比", format=".1f"),
        order=alt.Order("目前市值(U)", sort="descending"),
        color=alt.value("white")
    )
    chart_mkt = (pie_mkt_arc + pie_mkt_text).properties(title="🔵 市值持倉佔比 (Market %)")

    col_pie1, col_pie2 = st.columns(2)
    with col_pie1:
        st.altair_chart(chart_cost, use_container_width=True)
    with col_pie2:
        st.altair_chart(chart_mkt, use_container_width=True)

    # 3. 直方圖 (拆分標籤)
    st.markdown("#### 🔻 損益分析 (PnL)")
    bar_data = df_summary.copy()

    # A. 損益金額
    base_bar_amt = alt.Chart(bar_data).encode(x=alt.X("幣種", sort="-y"))
    bar_amt = base_bar_amt.mark_bar().encode(
        y=alt.Y("損益金額(U)", title="損益金額 (U)"),
        color=alt.condition(alt.datum['損益金額(U)'] > 0, alt.value("#28a745"), alt.value("#dc3545")),
        tooltip=["幣種", alt.Tooltip("損益金額(U)", format=",.2f")]
    )
    text_amt_pos = base_bar_amt.mark_text(align='center', baseline='top', dy=5).encode(
        y="損益金額(U)", text=alt.Text("損益金額(U)", format=",.0f"), color=alt.value("white")
    ).transform_filter(alt.datum['損益金額(U)'] >= 0)
    text_amt_neg = base_bar_amt.mark_text(align='center', baseline='bottom', dy=-5).encode(
        y="損益金額(U)", text=alt.Text("損益金額(U)", format=",.0f"), color=alt.value("white")
    ).transform_filter(alt.datum['損益金額(U)'] < 0)
    chart_amt = (bar_amt + text_amt_pos + text_amt_neg).properties(title="💵 各幣種損益金額 (Amount)")

    # B. 損益率
    base_bar_pct = alt.Chart(bar_data).encode(x=alt.X("幣種", sort="-y"))
    bar_pct = base_bar_pct.mark_bar().encode(
        y=alt.Y("損益率", title="損益率 (%)"),
        color=alt.condition(alt.datum['損益率'] > 0, alt.value("#28a745"), alt.value("#dc3545")),
        tooltip=["幣種", alt.Tooltip("損益率", format=".2f", title="損益率(%)")]
    )
    text_pct_pos = base_bar_pct.mark_text(align='center', baseline='top', dy=5).encode(
        y="損益率", text=alt.Text("損益率", format=".1f"), color=alt.value("white")
    ).transform_filter(alt.datum['損益率'] >= 0)
    text_pct_neg = base_bar_pct.mark_text(align='center', baseline='bottom', dy=-5).encode(
        y="損益率", text=alt.Text("損益率", format=".1f"), color=alt.value("white")
    ).transform_filter(alt.datum['損益率'] < 0)
    chart_pct = (bar_pct + text_pct_pos + text_pct_neg).properties(title="📈 各幣種損益率 (ROI %)")

    col_bar1, col_bar2 = st.columns(2)
    with col_bar1:
        st.altair_chart(chart_amt, use_container_width=True)
    with col_bar2:
        st.altair_chart(chart_pct, use_container_width=True)
else:
    st.info("尚無交易資料，無法顯示圖表。")

st.markdown("---")

# --- 第四區：幣種詳細分析表格 ---
st.subheader("📋 詳細數據清單")

if not df_summary.empty:
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
            "投入佔比": st.column_config.ProgressColumn("資金佔比", format="%.1f%%", min_value=0, max_value=100),
            "目前市值(U)": st.column_config.NumberColumn("目前市值 (U)", format="$%.2f"),
            "目前幣價": st.column_config.NumberColumn("現價", format="%.6f"),
            "市值佔比": st.column_config.ProgressColumn("持倉佔比", format="%.1f%%", min_value=0, max_value=100),
            "損益率": st.column_config.NumberColumn("損益率 (%)", format="%.2f%%"),
            "損益金額(U)": st.column_config.NumberColumn("損益金額 (U)", format="$%.2f")
        }
    )