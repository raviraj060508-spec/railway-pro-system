import streamlit as st
import sqlite3
import random
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

DB = "railway.db"

# -------- DATABASE --------
def connect():
    return sqlite3.connect(DB)

def init_db():
    conn = connect()
    c = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS tickets (pnr INTEGER, name TEXT, status TEXT, seat TEXT)")

    conn.commit()
    conn.close()

init_db()

# -------- SESSION --------
if "user" not in st.session_state:
    st.session_state.user = None

if "payment_done" not in st.session_state:
    st.session_state.payment_done = False

if "show_payment" not in st.session_state:
    st.session_state.show_payment = False

# -------- CORE LOGIC --------
def generate_pnr():
    return random.randint(100000, 999999)

def get_counts():
    conn = connect()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM tickets WHERE status='CONFIRMED'")
    confirmed = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM tickets WHERE status='RAC'")
    rac = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM tickets WHERE status='WAITING'")
    waiting = c.fetchone()[0]

    conn.close()
    return confirmed, rac, waiting


def book_ticket(name):
    conn = connect()
    c = conn.cursor()

    confirmed, rac, waiting = get_counts()
    pnr = generate_pnr()

    if confirmed < 3:
        status = "CONFIRMED"
        seat = f"S{confirmed+1}"
    elif rac < 2:
        status = "RAC"
        seat = "RAC"
    elif waiting < 3:
        status = "WAITING"
        seat = "WL"
    else:
        return None

    c.execute("INSERT INTO tickets VALUES (?, ?, ?, ?)", (pnr, name, status, seat))
    conn.commit()
    conn.close()

    return pnr


def cancel_ticket(pnr):
    conn = connect()
    c = conn.cursor()

    c.execute("SELECT status FROM tickets WHERE pnr=?", (pnr,))
    result = c.fetchone()

    if not result:
        return "PNR not found"

    status = result[0]
    c.execute("DELETE FROM tickets WHERE pnr=?", (pnr,))

    # -------- SMART SHIFT --------
    if status == "CONFIRMED":
        c.execute("SELECT pnr FROM tickets WHERE status='RAC' LIMIT 1")
        rac = c.fetchone()

        if rac:
            c.execute("UPDATE tickets SET status='CONFIRMED', seat='S1' WHERE pnr=?", (rac[0],))

            c.execute("SELECT pnr FROM tickets WHERE status='WAITING' LIMIT 1")
            wl = c.fetchone()

            if wl:
                c.execute("UPDATE tickets SET status='RAC' WHERE pnr=?", (wl[0],))

    elif status == "RAC":
        c.execute("SELECT pnr FROM tickets WHERE status='WAITING' LIMIT 1")
        wl = c.fetchone()

        if wl:
            c.execute("UPDATE tickets SET status='RAC' WHERE pnr=?", (wl[0],))

    conn.commit()
    conn.close()

    return "Cancelled + Auto Updated"


def search_ticket(pnr):
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT * FROM tickets WHERE pnr=?", (pnr,))
    data = c.fetchone()
    conn.close()
    return data


def get_all():
    conn = connect()
    c = conn.cursor()
    c.execute("SELECT * FROM tickets")
    data = c.fetchall()
    conn.close()
    return data

# -------- PDF --------
def create_pdf(ticket):
    file = f"{ticket[0]}.pdf"
    doc = SimpleDocTemplate(file)
    styles = getSampleStyleSheet()

    content = [
        Paragraph(f"PNR: {ticket[0]}", styles['Normal']),
        Paragraph(f"Name: {ticket[1]}", styles['Normal']),
        Paragraph(f"Status: {ticket[2]}", styles['Normal']),
        Paragraph(f"Seat: {ticket[3]}", styles['Normal']),
    ]

    doc.build(content)
    return file

# -------- PAYMENT --------
def payment():
    st.subheader("💳 Payment Gateway")

    card = st.text_input("Card Number")
    cvv = st.text_input("CVV", type="password")

    if st.button("Pay Now"):
        if card and cvv:
            st.session_state.payment_done = True
            st.success("✅ Payment Successful")
        else:
            st.error("Enter valid details")

# -------- UI --------
st.set_page_config(page_title="Railway Pro", layout="wide")

st.markdown("""
<style>
.stApp {
    background: linear-gradient(to right, #0f172a, #1e293b);
    color: white;
}
</style>
""", unsafe_allow_html=True)

st.title("🚆 Railway Reservation System (Pro)")

# -------- AUTH --------
if st.session_state.user is None:

    choice = st.selectbox("Login / Register", ["Login", "Register"])

    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")

    if choice == "Register":
        if st.button("Register"):
            conn = connect()
            c = conn.cursor()
            c.execute("INSERT INTO users VALUES (?,?)", (user, generate_password_hash(pwd)))
            conn.commit()
            conn.close()
            st.success("Registered!")

    elif choice == "Login":
        if st.button("Login"):
            conn = connect()
            c = conn.cursor()
            c.execute("SELECT password FROM users WHERE username=?", (user,))
            data = c.fetchone()
            conn.close()

            if data and check_password_hash(data[0], pwd):
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid Credentials")

# -------- MAIN APP --------
else:
    st.sidebar.write(f"👤 {st.session_state.user}")

    menu = st.sidebar.radio("Menu", [
        "Dashboard",
        "Book Ticket",
        "Cancel Ticket",
        "Search PNR",
        "Analytics"
    ])

    if menu == "Dashboard":
        c, r, w = get_counts()
        col1, col2, col3 = st.columns(3)
        col1.metric("Confirmed", c)
        col2.metric("RAC", r)
        col3.metric("Waiting", w)

    elif menu == "Book Ticket":
        name = st.text_input("Passenger Name")

        if not name:
            st.warning("Enter passenger name first")

        if st.button("Proceed to Payment"):
            st.session_state.show_payment = True

        if st.session_state.show_payment:
            payment()

        if st.session_state.payment_done:
            pnr = book_ticket(name)
            st.success(f"🎟️ Ticket Booked! PNR: {pnr}")

            # reset
            st.session_state.payment_done = False
            st.session_state.show_payment = False

    elif menu == "Cancel Ticket":
        pnr = st.number_input("PNR", step=1)
        if st.button("Cancel"):
            st.warning(cancel_ticket(int(pnr)))

    elif menu == "Search PNR":
        pnr = st.number_input("Enter PNR", step=1)
        if st.button("Search"):
            t = search_ticket(int(pnr))
            if t:
                st.success(t)
                pdf = create_pdf(t)
                with open(pdf, "rb") as f:
                    st.download_button("Download Ticket", f, file_name=pdf)
            else:
                st.error("Not Found")

    elif menu == "Analytics":
        c, r, w = get_counts()
        st.bar_chart({"Confirmed": c, "RAC": r, "Waiting": w})
        st.table(get_all())

    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()
