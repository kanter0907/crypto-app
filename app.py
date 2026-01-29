import streamlit as st
import pandas as pd
import requests
import time
import re
from io import BytesIO

# --- 網頁設定 ---
st.set_page_config(page_title="Crypto 資金戰情室", layout="wide", page_icon="🏦")
st.title("🏦 Crypto 資金戰情室 (動態匯率版)")

# ==========================================
# ⚠️ 請在此處填入你的 Google 試算表網址 ⚠️
# ==========================================
# 1. 交易紀錄分頁 (紀錄買了什麼幣)
TX_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=0#gid=0"

# 2. 資金紀錄分頁 (紀錄台幣買USDT) -> 這是新增的！
USDT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PoE-eQHnp1m5EwG7eVc14fvrSNSXdwNxdB8LEnhsQoE/edit?gid=608628357#gid=608628357"

# ==========================================

# 1. 讀取資料函式 (通用型)
def load_google_sheet(url, sheet_type="tx"):
    try:
        # 網址處理
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
        
        # --- 資料清洗與型別轉換 ---
        def clean_number(value):
            if pd.isna(value): return 0
            val_str = str(value)
            clean_val = re.sub(r'[^\d.-]', '', val_str) 
            try:
                return float(clean_val)
            except:
                return 0

        # A. 針對「資金紀錄 (USDT Log)」的處理
        if sheet_type == "usdt":
            required = ["投入台幣", "買入USDT"]
            # 簡單欄位對應
            if "TWD" in df.columns: df.rename(columns={"TWD": "投入台幣"}, inplace=True)
            if "USDT" in df.columns: df.rename(columns={"USDT": "買入USDT"}, inplace=True)
            
            for col in required:
                if col in df.columns:
                    df[col] = df[col].apply(clean_number)
                else:
                    df[col] = 0.0

        # B. 針對「交易紀錄 (TX)」的處理
        elif sheet_type == "tx":
            # 欄位對應
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
        st.error(f"❌ {sheet_type} 表讀取失敗: {e}")
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

# ==========================================
# 主程式邏輯
# ==========================================

# 1. 讀取兩張表
df_usdt = load_google_sheet(USDT_SHEET_URL, sheet_type="usdt")
df_tx = load_google_sheet(TX_SHEET_URL, sheet_type="tx")

if df_usdt.empty or df_tx.empty:
    st.warning("⚠️ 等待資料讀取中... 請確認兩個分頁的網址都已填入。")
    st.stop()

# 2. 計算資金池與匯率 (Requirement 1)
total_twd_in = df_usdt["投入台幣"].sum()
total_usdt_got = df_usdt["買入USDT"].sum()

# 避免除以零
if total_usdt_got > 0:
    avg_exchange_rate = total_twd_in / total_usdt_got
else:
    avg_exchange_rate = 32.5 # 預設值

# 3. 處理交易資料
if not all(col in df_tx.columns for col in ["幣種", "投入金額(U)", "持有顆數"]):
    st.error("❌ 交易表缺少必要欄位 (幣種, 投入金額(U), 持有顆數)")
    st.stop()

# 抓價格
with st.sidebar:
    st.header("⚙️ 控制台")
    if st.button("🔄 刷新數據"):
        find_coin_id.clear()
        st.cache_data.clear()
        st.rerun()
        
    unique_coins = df_tx["幣種"].unique().tolist()
    # 移除空值
    unique_coins = [x for x in unique_coins if x != "nan" and x != "0"]
    current_prices = get_live_prices_auto(unique_coins)

# --- 核心計算 (Aggregation) ---
clean_tx = df_tx[df_tx["幣種"].isin(unique_coins)].copy()

# 依照幣種彙整
df_summary = clean_tx.groupby("幣種").agg({
    "投入金額(U)": "sum",
    "持有顆數": "sum"
}).reset_index()

# 計算詳細指標
df_summary["平均成本(U)"] = df_summary.apply(lambda x: x["投入金額(U)"] / x["持有顆數"] if x["持有顆數"] > 0 else 0, axis=1)
df_summary["目前幣價"] = df_summary["幣種"].map(current_prices).fillna(0)
df_summary["目前市值(U)"] = df_summary["持有顆數"] * df_summary["目前幣價"]
df_summary["損益金額(U)"] = df_summary["目前市值(U)"] - df_summary["投入金額(U)"]
df_summary["損益率"] = df_summary.apply(lambda x: (x["損益金額(U)"] / x["投入金額(U)"]) if x["投入金額(U)"] > 0 else 0, axis=1) # 這裡保持小數 (例如 0.05 代表 5%)

# 總體指標
total_invested_in_coins = df_summary["投入金額(U)"].sum() # 實際買幣花掉的錢
total_portfolio_value = df_summary["目前市值(U)"].sum()
remaining_ammo = total_usdt_got - total_invested_in_coins # 剩餘子彈

# 計算佔比 (Requirement 2 & 3)
# 投入佔比 = 個別投入 / 總投入
df_summary["投入佔比"] = df_summary.apply(lambda x: x["投入金額(U)"] / total_invested_in_coins if total_invested_in_coins > 0 else 0, axis=1)
# 市值佔比 = 個別市值 / 總市值
df_summary["市值佔比"] = df_summary.apply(lambda x: x["目前市值(U)"] / total_portfolio_value if total_portfolio_value > 0 else 0, axis=1)

# ==========================================
# 視覺化顯示 (Dashboard)
# ==========================================

# --- 第一區：資金池與匯率 (Req 1) ---
st.subheader("💰 資金池與動態匯率")

col_a, col_b, col_c, col_d = st.columns(4)

col_a.metric("🇹🇼 總投入台幣本金", f"${total_twd_in:,.0f}")
col_b.metric("🇺🇸 總買入 USDT", f"${total_usdt_got:,.2f}")
col_c.metric("💱 真實平均匯率", f"{avg_exchange_rate:.4f} TWD/U", 
             delta="動態計算" if total_usdt_got > 0 else "無資料", delta_color="off")
col_d.metric("🔫 剩餘子彈 (USDT)", f"${remaining_ammo:,.2f}", 
             delta=f"{remaining_ammo*avg_exchange_rate:,.0f} TWD")

st.markdown("---")

# --- 第二區：總持倉績效 ---
st.subheader("📈 總持倉績效")

total_pnl = df_summary["損益金額(U)"].sum()
total_roi = (total_pnl / total_invested_in_coins) if total_invested_in_coins > 0 else 0

# 台幣估值 (使用真實匯率計算)
twd_pnl = total_pnl * avg_exchange_rate
twd_val = total_portfolio_value * avg_exchange_rate

m1, m2, m3 = st.columns(3)
m1.metric("總市值估算", f"${total_portfolio_value:,.2f} U", 
          delta=f"≈ {twd_val:,.0f} TWD")
m2.metric("總損益金額", f"${total_pnl:,.2f} U", 
          delta=f"≈ {twd_pnl:,.0f} TWD")
m3.metric("總損益率 (ROI)", f"{total_roi:.2%}")

st.markdown("---")

# --- 第三區：個別幣種儀表板 (Req 2 & 3) ---
st.subheader("📊 幣種詳細分析")

# 這裡使用 st.dataframe 的 column_config 來達成「儀表板化」的效果
# 我們將欄位整理成使用者要求的順序，並加上視覺化條圖

# 整理顯示資料
display_df = df_summary[[
    "幣種", 
    "投入金額(U)", "平均成本(U)", "持有顆數", "投入佔比", # 投入面
    "目前市值(U)", "目前幣價", "市值佔比", # 現值面
    "損益率", "損益金額(U)" # 損益面
]].copy()

# 依照市值排序
display_df = display_df.sort_values("目前市值(U)", ascending=False).reset_index(drop=True)
display_df.index = display_df.index + 1

st.dataframe(
    display_df,
    use_container_width=True,
    column_config={
        "幣種": st.column_config.TextColumn("幣種", width="small"),
        
        # --- 投入面 (Req 2) ---
        "投入金額(U)": st.column_config.NumberColumn(
            "總投入資金 (U)", format="$%.2f"
        ),
        "平均成本(U)": st.column_config.NumberColumn(
            "投入均價", format="%.6f"
        ),
        "持有顆數": st.column_config.NumberColumn(
            "持有顆數", format="%.2f"
        ),
        "投入佔比": st.column_config.ProgressColumn(
            "資金佔比 (Cost %)", 
            format="%.1f%%", 
            min_value=0, max_value=1,
            help="這個幣佔了你總投入本金的多少百分比"
        ),

        # --- 現值與損益面 (Req 3) ---
        "目前市值(U)": st.column_config.NumberColumn(
            "目前市值 (U)", format="$%.2f"
        ),
        "目前幣價": st.column_config.NumberColumn(
            "現價", format="%.6f"
        ),
        "市值佔比": st.column_config.ProgressColumn(
            "持倉佔比 (Market %)", 
            format="%.1f%%", 
            min_value=0, max_value=1,
            help="這個幣的市值佔你總資產的多少百分比"
        ),
        "損益率": st.column_config.NumberColumn(
            "損益率 (%)", 
            format="%.2f%%"
        ),
        "損益金額(U)": st.column_config.NumberColumn(
            "損益金額 (U)", format="$%.2f"
        )
    }
)

# 為了讓損益率有顏色，我們還是需要 style (但這次只針對 dataframe 的值做簡單處理，避免複雜圖表)
# 如果想要更進階的「紅綠燈條」，Streamlit 目前原生的 dataframe 支援度有限，
# 但上面的 ProgressColumn 已經很有儀表板的感覺了。