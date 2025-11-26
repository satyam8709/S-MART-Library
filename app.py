import streamlit as st
import sqlite3
import pandas as pd
import os
import time
from datetime import date, datetime, timedelta

# ==========================================
# 1. CONFIGURATION & DATABASE SETUP
# ==========================================
st.set_page_config(page_title="S-MART Library OS", page_icon="🏢", layout="wide")

# Check if we are on Cloud or Local
if not os.path.exists('data'):
    os.makedirs('data')
    
DB_NAME = 'data/smart_library.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Create Tables
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT, role TEXT, full_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone_number TEXT UNIQUE, password TEXT, target_exam TEXT,
        joining_date DATE, due_date DATE,
        is_profile_approved INTEGER DEFAULT 0,
        is_seat_approved INTEGER DEFAULT 0,
        assigned_seat_id INTEGER,
        status TEXT DEFAULT 'Pending' 
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS seats (
        seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seat_label TEXT UNIQUE, has_locker INTEGER, status TEXT DEFAULT 'Available'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER, amount INTEGER, date DATE, status TEXT
    )''')

    # Default Data: Admin
    c.execute("INSERT OR IGNORE INTO admins VALUES ('admin', 'admin123', 'Super', 'Satyam Owner')")
    
    # Default Data: 100 Seats
    c.execute('SELECT count(*) FROM seats')
    if c.fetchone()[0] == 0:
        seats_data = []
        for i in range(1, 101):
            label = f"A-{i}"
            locker = 1 if i % 5 == 0 else 0 
            seats_data.append((label, locker, 'Available'))
        c.executemany('INSERT INTO seats (seat_label, has_locker, status) VALUES (?,?,?)', seats_data)
        
    conn.commit()
    conn.close()

# Initialize DB on first run
if not os.path.exists(DB_NAME):
    init_db()

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def login_user(username, password, role):
    conn = get_db_connection()
    c = conn.cursor()
    user = None
    msg = ""
    
    if role == "Admin":
        c.execute("SELECT * FROM admins WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        if user: msg = "Success"
        else: msg = "Invalid Admin Credentials"
    else:
        c.execute("SELECT * FROM students WHERE phone_number=? AND password=?", (username, password))
        user = c.fetchone()
        if user:
            # Check Status
            if user[6] == 0: msg = "Profile Pending Approval" # is_profile_approved
            else: msg = "Success"
        else:
            msg = "Invalid Student Credentials"
            
    conn.close()
    return user, msg

# ==========================================
# 3. INTERFACE SECTIONS
# ==========================================

def show_landing_page():
    st.image("https://images.unsplash.com/photo-1507842217121-9e93c8aaf27c?q=80&w=1000", height=300, use_container_width=True)
    st.title("🏢 S-MART Library & Study Centre")
    st.info("📍 Gopalganj, Bihar | 📞 +91 99999 99999")
    
    c1, c2, c3 = st.columns(3)
    c1.success("❄️ Full AC & WiFi")
    c2.warning("🔋 Charging & Lights")
    c3.error("🔒 Personal Lockers")
    
    st.divider()
    st.subheader("Check Seat Availability")
    
    # LEAD TRAP
    with st.expander("Click to View Live Map"):
        name = st.text_input("Enter Name")
        phone = st.text_input("Enter Phone")
        if st.button("Check Map"):
            if len(phone) == 10:
                st.success("Verified! Loading Map...")
                show_public_map()
            else:
                st.error("Please enter valid 10-digit phone number")

def show_public_map():
    conn = get_db_connection()
    seats = pd.read_sql("SELECT seat_label, status FROM seats", conn)
    conn.close()
    
    st.write("🔴 Occupied | 🟢 Available")
    
    # 10x10 Grid
    for r in range(0, 100, 10):
        cols = st.columns(10)
        for i in range(10):
            if r+i < len(seats):
                s = seats.iloc[r+i]
                label = s['seat_label']
                color = "primary" if s['status'] == 'Occupied' else "secondary"
                cols[i].button(label, key=f"pub_{label}", type=color, disabled=True)

def show_admin_dashboard():
    st.title("👔 Admin Command Center")
    
    tab1, tab2, tab3 = st.tabs(["🗺️ Seat Map", "⏳ Approvals", "👥 Students"])
    
    conn = get_db_connection()
    
    with tab1:
        st.subheader("Live Floor Plan")
        seats = pd.read_sql("SELECT * FROM seats", conn)
        # 10x10 Grid
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    label = s['seat_label']
                    status = s['status']
                    
                    # Logic for color
                    btn_type = "primary" if status == 'Occupied' else "secondary"
                    if status == 'Mercy': btn_type = "primary" # Would be yellow in custom css
                    
                    if cols[i].button(f"{label}", key=f"adm_{label}", type=btn_type):
                        st.toast(f"Seat {label}: {status}")

    with tab2:
        st.subheader("Pending Approvals")
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        if not pending.empty:
            for _, row in pending.iterrows():
                c1, c2 = st.columns([3,1])
                c1.write(f"**{row['name']}** ({row['phone_number']}) - {row['target_exam']}")
                if c2.button("Approve", key=f"app_{row['student_id']}"):
                    c = conn.cursor()
                    c.execute("UPDATE students SET is_profile_approved=1, status='Active' WHERE student_id=?", (row['student_id'],))
                    conn.commit()
                    st.rerun()
        else:
            st.info("No pending requests.")
            
    with tab3:
        st.dataframe(pd.read_sql("SELECT name, phone_number, status, due_date FROM students", conn))
    
    conn.close()

def show_student_dashboard(user):
    st.title(f"🎓 Welcome, {user[1]}")
    st.success("You are inside the S-MART App.")
    
    c1, c2 = st.columns(2)
    c1.metric("My Seat", "Pending" if user[8] is None else f"A-{user[8]}")
    c2.metric("Fee Status", user[10]) # Status
    
    st.info("📢 Notice: Library will remain closed on Sunday for maintenance.")
    
    st.divider()
    st.write("Use the sidebar to request seat changes or contact admin.")

# ==========================================
# 4. MAIN APP ROUTER
# ==========================================
def main():
    if 'user' not in st.session_state:
        st.session_state['user'] = None
        
    st.sidebar.title("🔐 S-MART Access")
    
    if st.session_state['user']:
        if st.sidebar.button("Logout"):
            st.session_state['user'] = None
            st.rerun()
        
        # Router
        if st.session_state['role'] == 'Admin':
            show_admin_dashboard()
        else:
            show_student_dashboard(st.session_state['user'])
            
    else:
        menu = st.sidebar.radio("Menu", ["Home", "Register", "Login"])
        
        if menu == "Home":
            show_landing_page()
            
        elif menu == "Register":
            st.header("📝 New Student Registration")
            with st.form("reg"):
                name = st.text_input("Full Name")
                phone = st.text_input("Phone (10 digits)")
                pw = st.text_input("Password", type="password")
                exam = st.selectbox("Exam", ["UPSC", "JEE/NEET", "Other"])
                if st.form_submit_button("Submit"):
                    conn = get_db_connection()
                    try:
                        conn.execute("INSERT INTO students (name, phone_number, password, target_exam, joining_date) VALUES (?,?,?,?,?)", 
                                     (name, phone, pw, exam, date.today()))
                        conn.commit()
                        st.success("Registered! Wait for Admin Approval.")
                    except:
                        st.error("Phone number already exists.")
                    conn.close()
                    
        elif menu == "Login":
            st.header("Login")
            role = st.selectbox("Role", ["Student", "Admin"])
            u = st.text_input("Phone / Username")
            p = st.text_input("Password", type="password")
            if st.button("Login"):
                user, msg = login_user(u, p, role)
                if user:
                    st.session_state['user'] = user
                    st.session_state['role'] = role
                    st.rerun()
                else:
                    st.error(msg)

if __name__ == "__main__":
    init_db()
    main()
