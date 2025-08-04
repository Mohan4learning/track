import streamlit as st
import pandas as pd
import os
import threading
import time
from datetime import datetime

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from streamlit_autorefresh import st_autorefresh

# --- Configuration ---
DATA_DIR    = "link_tracking_data"
LINKS_FILE  = os.path.join(DATA_DIR, "all_links.txt")
POLL_INTERVAL = 60  # seconds between polls
os.makedirs(DATA_DIR, exist_ok=True)

# Heartbeat: use a global file to persist info
HEARTBEAT_FILE = os.path.join(DATA_DIR, "heartbeat.txt")

st_autorefresh(interval=2000)

def write_heartbeat(count, last_poll):
    with open(HEARTBEAT_FILE, "w") as f:
        f.write(f"{count}\n{last_poll}\n")

def read_heartbeat():
    if not os.path.exists(HEARTBEAT_FILE):
        return 0, None
    with open(HEARTBEAT_FILE) as f:
        lines = f.readlines()
        try:
            count = int(lines[0])
            last_poll = lines[1].strip()
            return count, last_poll
        except Exception:
            return 0, None

def load_links():
    """Read links from file, or return defaults if missing."""
    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE) as f:
            return [l.strip() for l in f if l.strip()]
    return [
        "https://www.astroyogi.com/astrologer/expert/saalivaagana.aspx"
    ]

def append_log(url, call_vis, joinq_vis):
    """Append a single row to the CSV for `url`."""
    safe = url.replace("://", "_").replace("/", "_")
    path = os.path.join(DATA_DIR, f"{safe}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["datetime"])
    else:
        df = pd.DataFrame(columns=["datetime", "Available_For_Call", "On_Call"])
    new = pd.DataFrame([{
        "datetime": datetime.now(),
        "Available_For_Call": int(call_vis),
        "On_Call": int(joinq_vis)
    }])
    df = pd.concat([df, new], ignore_index=True)
    df.to_csv(path, index=False)

def track_once(url):
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    svc = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=svc, options=opts)
    found_call = False
    found_joinq = False
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//button[contains(@class, 'profile_green_btn')]"))
        )
        buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'profile_green_btn')]")
        for btn in buttons:
            txt = btn.text.strip().lower()
            if "call" in txt:
                found_call = True
            if "join q" in txt or "joinq" in txt:
                found_joinq = True
        return found_call, found_joinq
    except Exception as e:
        print(f"[ERROR] {url} - {e}")
        return None, None
    finally:
        driver.quit()

def background_tracker():
    count = 0
    while True:
        links = load_links()
        for url in links:
            call_vis, joinq_vis = track_once(url)
            if call_vis is not None:
                append_log(url, call_vis, joinq_vis)
            else:
                print(f"[WARN] Skipped logging for {url} due to error.")
        count += 1
        last_poll = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        write_heartbeat(count, last_poll)
        print(f"[TRACKER] Poll #{count} at {last_poll}")
        time.sleep(POLL_INTERVAL)

# Start background thread once (uses a lock file approach)
if "tracker_started" not in st.session_state:
    threading.Thread(target=background_tracker, daemon=True).start()
    st.session_state.tracker_started = True

# --- Streamlit UI ---
st.title("🔔 Real-Time Call & Join Q Tracker")

# Heartbeat display (reads from file, so always up-to-date)
poll_count, last_poll = read_heartbeat()
hb_col1, hb_col2 = st.columns(2)
hb_col1.metric("🕒 Last Poll", last_poll if last_poll else "Pending…")
hb_col2.metric("✅ Polls Completed", poll_count)

st.sidebar.header("Manage Links")
links = load_links()

# Add a new link
new = st.sidebar.text_input("Add new link (Enter then click ▶)")
if new and st.sidebar.button("▶"):
    if new not in links:
        with open(LINKS_FILE, "a") as f:
            f.write(new.strip() + "\n")
        st.sidebar.success("Link added! Picked up in next poll.")
    else:
        st.sidebar.info("Already exists.")
st.sidebar.markdown("---")

# Main: select link to view
sel = st.selectbox("Select a link to view live data", links)

if sel:
    safe = sel.replace("://", "_").replace("/", "_")
    path = os.path.join(DATA_DIR, f"{safe}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["datetime"])
        df["date"]    = df["datetime"].dt.date
        df["hour"]    = df["datetime"].dt.hour
        df["weekday"] = df["datetime"].dt.day_name()
        hourly = df.groupby("hour")[["Available_For_Call","On_Call"]].sum()
        daily  = df.groupby("date")[["Available_For_Call","On_Call"]].sum()
        worder = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        weekly = df.groupby("weekday")[["Available_For_Call","On_Call"]].sum().reindex(worder)
        st.subheader(f"📊 Live Data for {sel}")
        st.write("### Hourly summary");  st.bar_chart(hourly)
        st.write("### Weekly summary"); st.bar_chart(weekly)
        st.write("### Daily trend");    st.line_chart(daily)
    else:
        st.info("Waiting for first poll… check back in a minute.")
else:
    st.info("Select or add a link to begin.")
