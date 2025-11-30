import streamlit as st
import sqlite3
import pandas as pd
import os
import random
from datetime import date, datetime, timedelta

# ==========================================
# 1. CONFIGURATION
# ==========================================
st.set_page_config(page_title="S-MART COMMANDER", page_icon="🏢", layout="wide")

# Database Path
if not os.path.exists('data'): os.makedirs('data')
if not os.path.exists('student_documents'): os.makedirs('student_documents')

DB_NAME = 'data/smart_library_v5.db'

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. ADMINS
    c.execute('''CREATE TABLE IF NOT EXISTS admins (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute("INSERT OR IGNORE INTO admins VALUES ('admin', 'admin123', 'Super')")
    
    # 2. SEATS
    c.execute('''CREATE TABLE IF NOT EXISTS seats (
        seat_id INTEGER PRIMARY KEY AUTOINCREMENT,
        seat_label TEXT UNIQUE, has_locker INTEGER, status TEXT DEFAULT 'Available'
    )''')
    
    # 3. STUDENTS (Full Profile)
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, password TEXT, exam TEXT,
        email TEXT, father_name TEXT, guardian_phone TEXT, address TEXT,
        photo_path TEXT, govt_id_path TEXT,
        joining_date DATE, due_date DATE,
        is_profile_approved INTEGER DEFAULT 0,
        is_seat_approved INTEGER DEFAULT 0,
        assigned_seat_id INTEGER,
        mercy_days INTEGER DEFAULT 0,
        status TEXT DEFAULT 'Pending'
    )''')
    
    # 4. EXTRAS
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, amount INTEGER, date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS seat_requests (req_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, current_seat TEXT, requested_seat TEXT, reason TEXT, status TEXT)''')

    # Generate 100 Seats
    c.execute('SELECT count(*) FROM seats')
    if c.fetchone()[0] == 0:
        seats = [(f"A-{i}", 1 if i%5==0 else 0, 'Available') for i in range(1, 101)]
        c.executemany('INSERT INTO seats (seat_label, has_locker, status) VALUES (?,?,?)', seats)
        
    conn.commit()
    conn.close()

if not os.path.exists(DB_NAME): init_db()

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def save_uploaded_file(uploaded_file, prefix):
    if uploaded_file is not None:
        file_path = f"student_documents/{prefix}_{uploaded_file.name}"
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def check_lockout(student_id):
    conn = get_db()
    try:
        df = pd.read_sql(f"SELECT * FROM students WHERE student_id={student_id}", conn)
        conn.close()
        if df.empty: return False, "Error"
        s = df.iloc[0]
        
        mercy = s['mercy_days'] if s['mercy_days'] else 0
        
        if s['status'] == 'Active':
            today = date.today()
            try: due = datetime.strptime(str(s['due_date']), '%Y-%m-%d').date()
            except: due = today
            limit = due + timedelta(days=5 + int(mercy))
            
            if today > limit:
                conn = get_db()
                conn.execute("UPDATE students SET status='Locked' WHERE student_id=?", (student_id,))
                conn.commit()
                conn.close()
                return True, "⛔ ACCOUNT LOCKED"
            elif today > due:
                return False, f"⚠️ WARNING: Fees Overdue"
        elif s['status'] == 'Locked': return True, "⛔ ACCOUNT LOCKED"
             
        return False, "Welcome"
    except: return False, "System Error"

# ==========================================
# 3. REGISTRATION (OTP + KYC)
# ==========================================
def show_registration_page():
    st.header("📝 S-MART Admission Form")
    if 'reg_verified' not in st.session_state: st.session_state['reg_verified'] = False
    
    if not st.session_state['reg_verified']:
        st.info("Step 1: Verify Mobile Number")
        phone_input = st.text_input("Enter Mobile Number (10 Digits)")
        if st.button("Send OTP"):
            if len(phone_input) == 10:
                otp = random.randint(1000, 9999)
                st.session_state['generated_otp'] = str(otp)
                st.session_state['reg_phone'] = phone_input
                st.success(f"OTP Sent! (Simulation Code: {otp})")
            else: st.error("Invalid Number")
                
        if 'generated_otp' in st.session_state:
            otp_check = st.text_input("Enter OTP")
            if st.button("Verify OTP"):
                if otp_check == st.session_state['generated_otp']:
                    st.session_state['reg_verified'] = True
                    st.rerun()
                else: st.error("Wrong OTP")
    
    else:
        st.success(f"✅ Phone Verified: {st.session_state['reg_phone']}")
        with st.form("kyc_form"):
            st.subheader("Basic Details")
            c1, c2 = st.columns(2)
            name = c1.text_input("Full Student Name")
            father = c2.text_input("Father/Guardian Name")
            c3, c4 = st.columns(2)
            g_phone = c3.text_input("Guardian Phone Number")
            email = c4.text_input("Email ID")
            address = st.text_area("Permanent Address")
            exam = st.selectbox("Preparing For", ["UPSC", "BPSC", "JEE", "NEET", "CA/CS", "General"])
            password = st.text_input("Set Login Password", type="password")
            
            st.subheader("Upload Documents")
            c5, c6 = st.columns(2)
            photo = c5.file_uploader("Passport Size Photo", type=['jpg', 'png'])
            govt_id = c6.file_uploader("Govt ID (Aadhar/PAN)", type=['jpg', 'png', 'pdf'])
            
            if st.form_submit_button("Submit Application"):
                if photo and govt_id:
                    p_path = save_uploaded_file(photo, st.session_state['reg_phone'])
                    id_path = save_uploaded_file(govt_id, st.session_state['reg_phone'])
                    conn = get_db()
                    try:
                        conn.execute("""INSERT INTO students (name, phone, password, exam, email, father_name, guardian_phone, address, photo_path, govt_id_path, joining_date, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                     (name, st.session_state['reg_phone'], password, exam, email, father, g_phone, address, p_path, id_path, date.today(), 'Pending'))
                        conn.commit()
                        st.balloons()
                        st.success("🎉 Registration Successful! Wait for Admin Approval.")
                    except: st.error("Phone already registered.")
                    conn.close()
                else: st.warning("Upload Photo & ID")

# ==========================================
# 4. ADMIN DASHBOARD (COMMANDER EDITION)
# ==========================================
def show_admin_dashboard():
    st.sidebar.markdown("---")
    st.sidebar.header("👮 Admin")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Student Directory", "🗺️ X-Ray Map", "🚦 Approvals", "⚙️ Operations"])
    
    conn = get_db()
    
    # --- TAB 1: MASTER DIRECTORY (THE NEW MAGIC) ---
    with tab1:
        st.subheader("📂 Master Student Directory")
        
        # Search Bar
        all_students = pd.read_sql("SELECT student_id, name, phone, exam FROM students WHERE status != 'Pending'", conn)
        
        if not all_students.empty:
            search_list = [f"{row['name']} ({row['phone']})" for index, row in all_students.iterrows()]
            selected_student_str = st.selectbox("🔍 Search Student", ["Select..."] + search_list)
            
            if selected_student_str != "Select...":
                # Parse Name/Phone
                sel_phone = selected_student_str.split('(')[1].replace(')', '')
                profile = pd.read_sql(f"SELECT * FROM students WHERE phone='{sel_phone}'", conn).iloc[0]
                
                st.divider()
                
                # --- THE 360 PROFILE CARD ---
                col_left, col_mid, col_right = st.columns([1, 2, 1])
                
                with col_left:
                    if profile['photo_path']: st.image(profile['photo_path'], width=180, caption="Student Photo")
                    else: st.write("No Photo")
                    
                    if profile['govt_id_path']:
                        with open(profile['govt_id_path'], "rb") as f:
                            st.download_button("🆔 Download ID Proof", f, file_name=f"{profile['name']}_ID.png")

                with col_mid:
                    st.markdown(f"### 👤 {profile['name']}")
                    st.write(f"**📞 Phone:** {profile['phone']}")
                    st.write(f"**👨 Father:** {profile['father_name']}")
                    st.write(f"**🏠 Address:** {profile['address']}")
                    st.write(f"**🎓 Exam:** {profile['exam']}")
                    st.write(f"**💺 Seat:** {f'A-{profile["assigned_seat_id"]}' if profile['assigned_seat_id'] else 'None'}")
                    st.write(f"**📅 Due Date:** {profile['due_date']}")
                    
                    status_color = "green" if profile['status'] == 'Active' else "red"
                    st.markdown(f"**Status:** <span style='color:{status_color};font-weight:bold'>{profile['status']}</span>", unsafe_allow_html=True)

                with col_right:
                    st.write("#### ⚡ Actions")
                    
                    # WhatsApp General
                    msg = f"Hello {profile['name']}, Message from S-MART."
                    st.link_button("🟢 Chat (Student)", f"https://wa.me/91{profile['phone']}?text={msg}", use_container_width=True)
                    
                    # WhatsApp Guardian
                    if profile['guardian_phone']:
                        g_msg = f"Hello, we need to discuss about {profile['name']}."
                        st.link_button("👨 Chat (Guardian)", f"https://wa.me/91{profile['guardian_phone']}?text={g_msg}", use_container_width=True)
                    
                    # Fee Reminder
                    rem_msg = f"Dear Guardian/Student, Fees for {profile['name']} is due. Please pay immediately to avoid lockout."
                    st.link_button("🔴 Send Fee Reminder", f"https://wa.me/91{profile['phone']}?text={rem_msg}", use_container_width=True)
                    
                    # Lockout Button
                    if st.button("⛔ Lock Account"):
                        conn.execute("UPDATE students SET status='Locked' WHERE student_id=?", (profile['student_id'],))
                        conn.commit()
                        st.error("Account Locked!")
                        st.rerun()

        else:
            st.info("No Active Students found. Go to Approvals tab.")

    # --- TAB 2: X-RAY MAP ---
    with tab2:
        st.subheader("Live Floor Plan")
        seats = pd.read_sql("SELECT * FROM seats", conn)
        active_s = pd.read_sql("SELECT assigned_seat_id, name, father_name, phone FROM students WHERE assigned_seat_id IS NOT NULL", conn)
        s_map = {row['assigned_seat_id']: row for _, row in active_s.iterrows()}
        
        for r in range(0, 100, 10):
            cols = st.columns(10)
            for i in range(10):
                if r+i < len(seats):
                    s = seats.iloc[r+i]
                    sid = s['seat_id']
                    btn_type = "primary" if s['status'] != 'Available' else "secondary"
                    
                    if cols[i].button(s['seat_label'], key=f"seat_{sid}", type=btn_type):
                        if sid in s_map:
                            stu = s_map[sid]
                            st.toast(f"👤 {stu['name']} | 👨 {stu['father_name']} | 📞 {stu['phone']}")
                        else: st.toast("Empty Seat")

    # --- TAB 3: APPROVALS ---
    with tab3:
        st.subheader("Pending Approvals")
        pending = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=0", conn)
        for _, p in pending.iterrows():
            with st.expander(f"{p['name']} ({p['phone']})"):
                c1, c2 = st.columns(2)
                c1.write(f"**Father:** {p['father_name']}")
                c1.write(f"**Address:** {p['address']}")
                if p['photo_path']: c2.image(p['photo_path'], width=100)
                if st.button("✅ Approve", key=f"ap_{p['student_id']}"):
                     conn.execute("UPDATE students SET is_profile_approved=1, status='Active', due_date=? WHERE student_id=?", 
                                 (date.today() + timedelta(days=30), p['student_id']))
                     conn.commit()
                     st.rerun()

        st.divider()
        st.subheader("Assign Seats")
        seatless = pd.read_sql("SELECT * FROM students WHERE is_profile_approved=1 AND is_seat_approved=0", conn)
        for _, s in seatless.iterrows():
            c1, c2, c3 = st.columns([2,2,1])
            c1.write(f"**{s['name']}**")
            avail = pd.read_sql("SELECT seat_label FROM seats WHERE status='Available'", conn)
            sel_seat = c2.selectbox("Seat", avail['seat_label'], key=f"ss_{s['student_id']}")
            if c3.button("Assign", key=f"assign_{s['student_id']}"):
                sid = conn.execute(f"SELECT seat_id FROM seats WHERE seat_label='{sel_seat}'").fetchone()[0]
                conn.execute("UPDATE seats SET status='Occupied' WHERE seat_id=?", (sid,))
                conn.execute("UPDATE students SET assigned_seat_id=?, is_seat_approved=1 WHERE student_id=?", (sid, s['student_id']))
                conn.commit()
                st.success("Assigned!")
                st.rerun()

    # --- TAB 4: OPERATIONS ---
    with tab4:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Expense")
            with st.form("exp"):
                cat = st.selectbox("Type", ["Electricity", "Rent", "Staff"])
                amt = st.number_input("Amount")
                if st.form_submit_button("Save"):
                    conn.execute("INSERT INTO expenses (category, amount, date) VALUES (?,?,?)", (cat, amt, date.today()))
                    conn.commit()
                    st.success("Saved")
        with c2:
            st.subheader("Post Notice")
            txt = st.text_input("Message")
            if st.button("Post"):
                conn.execute("INSERT INTO notices (message, type) VALUES (?,?)", (txt, 'General'))
                conn.commit()
                st.success("Posted")
    
    conn.close()

# ==========================================
# 5. STUDENT DASHBOARD
# ==========================================
def show_student_dashboard(user):
    is_locked, msg = check_lockout(user[0])
    if is_locked:
        st.error(msg)
        st.stop()

    st.title(f"🎓 Dashboard")
    c1, c2 = st.columns([1, 2])
    with c1:
        if user[9]: st.image(user[9], width=150)
        st.write(f"**Name:** {user[1]}")
        st.write(f"**Seat:** A-{user[15]}")
        
    with c2:
        st.info("📢 Notices: Library is Open 24/7.")
        st.success("✅ Fees Paid")

# ==========================================
# 6. MAIN ROUTER
# ==========================================
def main():
    if 'user' not in st.session_state: st.session_state['user'] = None
    
    if st.session_state['user']:
        if st.sidebar.button("Logout"):
            st.session_state['user'] = None
            st.rerun()
        if st.session_state['role'] == 'Super': show_admin_dashboard()
        else: show_student_dashboard(st.session_state['user'])
    else:
        menu = st.sidebar.radio("Menu", ["🏠 Home", "📝 Join (OTP)", "🔐 Login"])
        if menu == "🏠 Home":
            st.title("S-MART Library")
            st.image("https://images.unsplash.com/photo-1497366216548-37526070297c?q=80&w=1200")
        elif menu == "📝 Join (OTP)": show_registration_page()
        elif menu == "🔐 Login":
            st.header("Login")
            role = st.selectbox("Role", ["Student", "Admin"])
            u = st.text_input("User/Phone")
            p = st.text_input("Password", type="password")
            if st.button("Enter"):
                conn = get_db()
                if role == 'Admin':
                    user = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", (u,p)).fetchone()
                    if user:
                        st.session_state['user'] = user
                        st.session_state['role'] = 'Super'
                        st.rerun()
                    else: st.error("Bad Admin Pass")
                else:
                    user = conn.execute("SELECT * FROM students WHERE phone=? AND password=?", (u,p)).fetchone()
                    if user:
                        if user[13] == 0: st.warning("Pending Approval")
                        else:
                            st.session_state['user'] = user
                            st.session_state['role'] = 'Student'
                            st.rerun()
                    else: st.error("User not found")
                conn.close()

if __name__ == "__main__":
    main()
