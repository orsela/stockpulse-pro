import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests
import time

# ---- סודות ----
SHEET_ID = st.secrets["SHEET_ID"]
WHATSAPP_PHONE = st.secrets.get("WHATSAPP_PHONE", "")
WHATSAPP_API_KEY = st.secrets.get("WHATSAPP_API_KEY", "")

# ---- חיבור לגיליון ----
@st.cache_resource(ttl=1800)
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet("Rules")

# ---- טעינת התראות ----
def load_alerts(email):
    try:
        data = get_sheet().get_all_records()
        df = pd.DataFrame(data)
        df = df[df["user_email"] == email]
        df["min_price"] = pd.to_numeric(df["min_price"], errors="coerce").fillna(0)
        df["max_price"] = pd.to_numeric(df["max_price"], errors="coerce").fillna(0)
        df["min_vol"] = pd.to_numeric(df["min_vol"], errors="coerce").fillna(0)
        df["alert_type"] = df["alert_type"].fillna("מעל").str.strip()
        return df[df["status"] == "Active"]
    except Exception as e:
        st.error(f"שגיאה בחיבור לגיליון: {e}")
        return pd.DataFrame()

# ---- נתוני מניה ----
@st.cache_data(ttl=20)
def get_price(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        price = round(hist["Close"].iloc[-1], 2)
        change = round((price - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100, 2)
        volume = int(hist["Volume"].iloc[-1])
        return price, change, volume
    except:
        return None, None, None

# ---- עיצוב ----
st.set_page_config(page_title="StockPulse Pro", page_icon="Chart Increasing", layout="centered")
st.markdown("<h1 style='text-align: center; color: #00ff88;'>StockPulse Pro</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>התראות חכמות בזמן אמת • עיצוב נקי ופשוט</p>", unsafe_allow_html=True)

email = st.text_input("הכנס את המייל שלך מהגיליון", placeholder="orsela@gmail.cc")

if not email:
    st.stop()

alerts = load_alerts(email)

if alerts.empty:
    st.info("אין התראות פעילות כרגע – הוסף בגיליון או תכתוב לי ואוסיף לך אחת")
    st.stop()

for _, row in alerts.iterrows():
    price, change, volume = get_price(row["symb"])
    if price is None:
        st.error(f"לא נמצאו נתונים ל-{row['symb']}")
        continue

    # בדיקת טריגר
    triggered = False
    typ = row["alert_type"]
    if typ == "מעל" and price >= row["max_price"] and volume >= row["min_vol"]:
        triggered = True
    elif typ == "מתחת" and price <= row["min_price"] and volume >= row["min_vol"]:
        triggered = True
    elif typ == "range" and row["min_price"] <= price <= row["max_price"] and volume >= row["min_vol"]:
        triggered = True

    # חישוב מרחק
    target = row["max_price"] if typ in ["מעל", "range"] else row["min_price"]
    distance = round((price - target) / target * 100, 1)

    # כרטיס
    color = "#ffebee" if triggered else "#f0f8ff"
    border = "4px solid #f44336" if triggered else "2px solid #00ff88"
    st.markdown(f"""
    <div style="background:{color}; padding:20px; border-radius:15px; border-left:{border}; margin:15px 0; text-align:right; direction:rtl;">
        <h2>{row['symb']} • {price}$</h2>
        <p style="font-size:1.4em; color:{'green' if change>=0 else 'red'};">{change:+.2f}% היום</p>
        <p>יעד: {target}$ • מרחק: {distance}%</p>
        <p>ווליום: {volume//1_000_000}M (מינ׳ {int(row['min_vol'])//1_000_000}M)</p>
        {f'<h3 style="color:red;">התראה הופעלה!</h3>' if triggered else ''}
    </div>
    """, unsafe_allow_html=True)

    # שליחת ווטסאפ (רק פעם אחת)
    if triggered and WHATSAPP_API_KEY != "123456":
        msg = f"StockPulse: {row['symb']} הגיע ליעד! מחיר: {price}$ ({change:+.2f}%)"
        url = f"https://api.callmebot.com/whatsapp.php?phone={WHATSAPP_PHONE}&text={requests.utils.quote(msg)}&apikey={WHATSAPP_API_KEY}"
        try:
            requests.get(url, timeout=5)
        except:
            pass

# רענון אוטומטי
time.sleep(1)
st.rerun()
