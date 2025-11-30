import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import date, datetime, timedelta

# ==========================================
# 1. SYSTEM CONFIGURATION
# ==========================================
st.set_page_config(page_title="S-MART OS Pro", page_icon="🏢", layout="wide")

# Database Setup
if not os.path.exists('data'): os.makedirs('data')
DB_NAME = 'data/smart_library.db'

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. ADMINS
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute("INSERT OR IGNORE INTO admins VALUES ('admin', 'admin123', 'Super')")
    
    # 2. SEATS (The Inventory)
    c.execute('''CREATE TABLE IF NOT EXISTS seats (
        seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seat_label TEXT UNIQUE, 
        has_locker INTEGER, 
        status TEXT DEFAULT 'Available' -- Available, Occupied, Reserved, Mercy
    )''')
    
    # 3. STUDENTS (The People)
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, password TEXT, exam TEXT,
        joining_date DATE, due_date DATE,
        is_profile_approved INTEGER DEFAULT 0,
        is_seat_approved INTEGER DEFAULT 0,
        assigned_seat_id INTEGER,
        mercy_days INTEGER DEFAULT 0,
        photo_url TEXT
    )''')
    
    # Auto-generate 100 Seats if empty
    c.execute('SELECT count(*) FROM seats')
    if c.fetchone()[0] == 0:
        seats = [(f"A-{i}", 1 if i%5==0 else 0, 'Available') for i in range(1, 101)]
        c.executemany('INSERT INTO seats (seat_label, has_locker, status) VALUES (?,?,?)', seats)
        
    conn.commit()
    conn.close()

# Initialize on load
if not os.path.exists(DB_NAME): init_db()

# ==========================================
# 2. LOGIC ENGINES (The Brains)
# ==========================================

def admin_approve_profile(student_id):
    conn = get_db()
    conn.execute("UPDATE students SET is_profile_approved=1 WHERE student_id=?", (student_id,))
    conn.commit()
    conn.close()

def admin_assign_seat(student_id, seat_label):
    conn = get_db()
    # 1. Find Seat ID
    seat = pd.read_sql(f"SELECT seat_id FROM seats WHERE seat_label='{seat_label}'", conn)
    if not seat.empty:
        s_id = seat.iloc[0]['seat_id']
        # 2. Update Seat Status
        conn.execute("UPDATE seats SET status='Occupied' WHERE seat_id=?", (s_id,))
        # 3. Update Student
        conn.execute("UPDATE students SET assigned_seat_id=?, is_seat_approved=1 WHERE student_id=?", (s_id, student_id))
        conn.commit()
        return True
    conn.close()
    return False

def toggle_mercy(seat_id, enable):
    conn = get_db()
    status = 'Mercy' if enable else 'Occupied'
    conn.execute("UPDATE seats SET status=? WHERE seat_id=?", (status, seat_id))
    conn.commit()
    conn.close()

# ==========================================
# 3. VISUAL INTERFACE (The Face)
# ==========================================

def show_guest_mode():
    st.image("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=1200", use_column_width=True)
    st.title("🏢 S-MART Library: The Gold Standard")
    
    # The "Lead Trap"
    with st.expander("🗺️ Check Live Seat Availability (Click Here)"):
        st.info("🔒 Security Check: Enter details to view the Map.")
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        phone = c2.text_input("Mobile Number")
        
        if st.button("Verify & Show Map"):
            if len(phone) >= 10:
                st.success(f"Verified {name}. Loading Map...")
                st.session_state['lead_verified'] = True
            else:
                st.error("Invalid Phone Number")

    if st.session_state.get('lead_verified'):
        st.write("### 🟢 Live Seat Status")
        conn = get_db()
        seats = pd.read_sql("SELECT seat_label, status FROM seats", conn)
        conn.close()
        
        # Grid View
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    color = "primary" if s['status'] == 'Occupied' else "secondary"
                    cols[i].button(s['seat_label'], key=f"lead_{i}", type=color, disabled=True)

def show_admin_dashboard():
    st.sidebar.markdown("---")
    st.sidebar.header("👮 Admin Controls")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Command Map", "🚦 3-Gate Approvals", "💰 Mercy & Fees", "👥 Student List"])
    
    conn = get_db()
    
    # --- TAB 1: THE COMMAND MAP ---
    with tab1:
        st.subheader("Real-Time Seat Operations")
        st.caption("🔴 Occupied | 🟢 Available | 🟡 Mercy Mode")
        
        seats = pd.read_sql("SELECT * FROM seats", conn)
        students = pd.read_sql("SELECT student_id, name, phone, assigned_seat_id FROM students WHERE assigned_seat_id IS NOT NULL", conn)
        
        # Map Student to Seat
        seat_map = {row['assigned_seat_id']: row for _, row in students.iterrows()}
        
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    sid = s['seat_id']
                    label = s['seat_label']
                    status = s['status']
                    
                    # Logic: If Mercy, we want visual indication (Streamlit buttons limited, using Emoji)
                    display_label = label
                    if status == 'Mercy': display_label = f"⚠️ {label}"
                    
                    btn_type = "primary" if status in ['Occupied', 'Mercy'] else "secondary"
                    
                    if cols[i].button(display_label, key=f"adm_{sid}", type=btn_type):
                        # Tooltip / Info on Click
                        if sid in seat_map:
                            stu = seat_map[sid]
                            st.toast(f"Occupied by: {stu['name']} ({stu['phone']})")
                        else:
                            st.toast(f"Seat {label} is Empty")

    # --- TAB 2: 3-GATE APPROVALS ---
    with tab2:
        st.subheader("Gate 1: Profile Approvals")
        pending_profiles = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        
        for _, p in pending_profiles.iterrows():
            c1, c2, c3 = st.columns([3, 2, 2])
            c1.write(f"**{p['name']}** ({p['phone']})")
            c2.write(f"Target: {p['exam']}")
            if c3.button("✅ Approve Profile", key=f"ap_{p['student_id']}"):
                admin_approve_profile(p['student_id'])
                st.success("Profile Approved!")
                st.rerun()
        
        st.divider()
        st.subheader("Gate 2: Seat Allocation")
        # Find students who are approved but have no seat
        seatless = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=1 AND is_seat_approved=0", conn)
        
        for _, s in seatless.iterrows():
            c1, c2 = st.columns(2)
            c1.write(f"Assign Seat for: **{s['name']}**")
            # Dropdown of empty seats
            empty_seats = pd.read_sql("SELECT seat_label FROM seats WHERE status='Available'", conn)
            selected_seat = c2.selectbox("Choose Seat", empty_seats['seat_label'], key=f"ss_{s['student_id']}")
            
            if c2.button("💺 Assign Seat", key=f"as_{s['student_id']}"):
                if admin_assign_seat(s['student_id'], selected_seat):
                    st.success(f"Assigned {selected_seat} to {s['name']}")
                    st.rerun()

    # --- TAB 3: MERCY & FEES ---
    with tab3:
        st.subheader("Mercy Mode (Grace Period)")
        # List occupied seats
        occupied = pd.read_sql("SELECT * FROM seats WHERE status IN ('Occupied', 'Mercy')", conn)
        
        seat_to_mercy = st.selectbox("Select Seat to Grant Mercy", occupied['seat_label'])
        
        c1, c2 = st.columns(2)
        if c1.button("⚠️ Enable Mercy (Yellow)"):
            sid = occupied[occupied['seat_label']==seat_to_mercy]['seat_id'].values[0]
            toggle_mercy(sid, True)
            st.rerun()
            
        if c2.button("🟢 Revoke Mercy (Green)"):
            sid = occupied[occupied['seat_label']==seat_to_mercy]['seat_id'].values[0]
            toggle_mercy(sid, False)
            st.rerun()

    # --- TAB 4: STUDENT LIST + WHATSAPP ---
    with tab4:
        st.subheader("Active Students")
        all_students = pd.read_sql("SELECT * FROM students", conn)
        
        for _, s in all_students.iterrows():
            with st.expander(f"{s['name']} (Seat: A-{s['assigned_seat_id'] if s['assigned_seat_id'] else 'None'})"):
                c1, c2 = st.columns(2)
                c1.write(f"Phone: {s['phone']}")
                c1.write(f"Exam: {s['exam']}")
                
                # WHATSAPP BUTTON
                msg = f"Hello {s['name']}, this is S-MART Library Admin."
                wa_link = f"https://wa.me/91{s['phone']}?text={msg}"
                c2.link_button("💬 Chat on WhatsApp", wa_link)

def show_student_dashboard(user):
    st.image("https://images.unsplash.com/photo-1555421689-491a97ff2040?q=80&w=1000", height=150, use_column_width=True)
    st.title(f"🎓 Welcome, {user[1]}")
    
    # VIRTUAL ID CARD
    st.markdown("""
    <style>
    .id-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="id-card">
        <h3>🆔 S-MART DIGITAL ID</h3>
        <p><b>Name:</b> {user[1]}</p>
        <p><b>ID No:</b> {user[0]}</p>
        <p><b>Exam Goal:</b> {user[4]}</p>
        <p><b>Status:</b> <span style="color:green">Active Member</span></p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    c1, c2 = st.columns(2)
    c1.info("📢 **Notice:** Library closed on Sunday.")
    
    # SUPPORT BUTTON
    msg = f"Hi Admin, I am {user[1]} (ID {user[0]}). I need help."
    c2.link_button("🆘 Contact Admin", f"https://wa.me/919999999999?text={msg}")

# ==========================================
# 4. MAIN NAVIGATION
# ==========================================
def main():
    if 'user' not in st.session_state: st.session_state['user'] = None

    if st.session_state['user']:
        # LOGGED IN VIEW
        user = st.session_state['user']
        role = st.session_state['role']
        
        st.sidebar.success(f"Logged in as: {user[1] if role=='Student' else user[0]}")
        if st.sidebar.button("Logout"):
            st.session_state['user'] = None
            st.rerun()
            
        if role == 'Super': show_admin_dashboard()
        else: show_student_dashboard(user)
        
    else:
        # PUBLIC VIEW
        menu = st.sidebar.radio("Menu", ["🏠 Home", "📝 Join S-MART", "🔐 Login"])
        
        if menu == "🏠 Home":
            show_guest_mode()
            
        elif menu == "📝 Join S-MART":
            st.header("📝 New Admission")
            with st.form("reg"):
                name = st.text_input("Full Name")
                phone = st.text_input("Phone (10 digits)")
                pw = st.text_input("Create Password", type="password")
                exam = st.selectbox("Exam", ["UPSC", "JEE/NEET", "Other"])
                if st.form_submit_button("Submit Application"):
                    conn = get_db()
                    try:
                        conn.execute("INSERT INTO students (name, phone, password, exam, joining_date) VALUES (?,?,?,?,?)", 
                                     (name, phone, pw, exam, date.today()))
                        conn.commit()
                        st.success("✅ Application Sent! Please wait for Admin approval.")
                    except:
                        st.error("Phone number already registered.")
                    conn.close()
                    
        elif menu == "🔐 Login":
            st.header("Login")
            role = st.selectbox("Role", ["Student", "Admin"])
            u = st.text_input("Username / Phone")
            p = st.text_input("Password", type="password")
            if st.button("Enter"):
                conn = get_db()
                if role == 'Admin':
                    user = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", (u,p)).fetchone()
                    if user:
                        st.session_state['user'] = user
                        st.session_state['role'] = 'Super'
                        st.rerun()
                    else: st.error("Wrong Admin Pass")
                else:
                    user = conn.execute("SELECT * FROM students WHERE phone=? AND password=?", (u,p)).fetchone()
                    if user:
                        if user[6] == 0: st.warning("⏳ Profile Pending Approval by Admin")
                        else:
                            st.session_state['user'] = user
                            st.session_state['role'] = 'Student'
                            st.rerun()
                    else: st.error("User not found")
                conn.close()

if __name__ == "__main__":
    main()
