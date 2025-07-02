from flask import Flask, request, jsonify, make_response
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Twilio config
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")

print("TWILIO_ACCOUNT_SID:", TWILIO_ACCOUNT_SID)
print("TWILIO_AUTH_TOKEN:", TWILIO_AUTH_TOKEN)
print("TWILIO_WHATSAPP_FROM:", TWILIO_WHATSAPP_FROM)

# Template-to-ContentSid mapping
TEMPLATE_CONTENT_MAP = {
    "payment_released": "HX6b4482f404e6b063984df49dc3b3e69c",
    "settlement_received": "HX706c585bc08250b45418ae5c6da063a9" 
}

# Maps template name to Pipedrive custom field ID
TEMPLATE_FIELD_MAP = {
    "payment_released": "cd83bf5536c29ee8f207e865c81fbad299472bfc",
    "settlement_received": "your_field_id_for_settlement_received"
}

@app.route("/", methods=["GET"])
def home():
    return "Webhook server is running", 200

@app.route("/front-webhook", methods=["GET"])
def verify_webhook():
    return jsonify({"status": "ok"}), 200




@app.route("/pipedrive-webhook", methods=["POST"])
def handle_pipedrive_webhook():
    try:
        data = request.get_json()
        print("📥 Received PD webhook:", json.dumps(data, indent=2))

        person_data_raw = data.get("data", {})
        person_id = (
            data.get("meta", {}).get("id") or
            data.get("current", {}).get("id")
        )

        if not person_id:
            print("⚠️ No person_id in webhook meta")
            return jsonify({"status": "noop", "error": "Missing person_id"}), 200

        # Get person phone number
        person_url = f"https://api.pipedrive.com/v1/persons/{person_id}?api_token={os.getenv('PIPEDRIVE_API_KEY')}"
        resp = requests.get(person_url)
        person_info = resp.json()

        if not person_info.get("data"):
            print("⚠️ Person not found in Pipedrive API")
            return jsonify({"status": "noop", "error": "Person not found"}), 200

        phone = person_info["data"].get("phone", [{}])[0].get("value")
        if not phone:
            print("⚠️ No phone number found for person")
            return jsonify({"status": "noop", "error": "No phone number"}), 200

        custom_fields = person_data_raw.get("custom_fields", {})
        previous_fields = data.get("previous", {}).get("custom_fields", {})
        results = []

        for template_name, field_id in TEMPLATE_FIELD_MAP.items():
            field_data = custom_fields.get(field_id)
            field_value = field_data.get("value") if isinstance(field_data, dict) else field_data

            # Use previous if needed (optional fallback)
            if not field_value:
                previous_data = previous_fields.get(field_id)
                field_value = previous_data.get("value") if isinstance(previous_data, dict) else previous_data

            if field_value:
                print(f"📤 Sending template '{template_name}' to {phone} with variable: {field_value}")
                content_sid = TEMPLATE_CONTENT_MAP.get(template_name)

                if not content_sid:
                    print(f"❌ No ContentSid found for template: {template_name}")
                    results.append({"template": template_name, "status": "error", "error": "Unknown ContentSid"})
                    continue

                # Send WhatsApp message
                send_status = send_whatsapp_template(phone, content_sid, {"1": field_value})
                print("📬 Send status:", send_status)
                results.append({"template": template_name, "status": send_status.get("status")})

                # Clear the field if sent successfully
                if send_status.get("status") == "success":
                    clear_url = f"https://api.pipedrive.com/v1/persons/{person_id}?api_token={os.getenv('PIPEDRIVE_API_KEY')}"
                    clear_payload = {field_id: ""}
                    clear_resp = requests.put(clear_url, json=clear_payload)
                    print(f"🧹 Cleared field {field_id}: {clear_resp.status_code}")

        if not results:
            return jsonify({"status": "noop", "message": "No relevant fields found"}), 200

        return jsonify({"status": "done", "results": results}), 200

    except Exception as e:
        print("❌ Exception in PD webhook:", str(e))
        return jsonify({"status": "error", "error": str(e)}), 200



@app.route("/webhook", methods=["POST"])
def handle_twilio_webhook():
    print("Received Twilio webhook!")
    data = request.json or request.form
    print("Twilio data:", data)
    return jsonify({"status": "received"}), 200


@app.route("/front-webhook", methods=["POST"])
def handle_front_webhook():
    try:
        # Accept non-JSON or ping requests
        if not request.is_json:
            print("Non-JSON request received.")
            return jsonify({"status": "noop"}), 200

        data = request.get_json(force=True, silent=True) or {}

        # If this is likely a test ping with no useful fields
        if "body" not in data or "recipient" not in data:
            print("Ping received:", data)
            return jsonify({"status": "noop"}), 200

        print("Valid event from Front:", data)

        comment_body = data.get("body", "")
        recipient = data.get("recipient", {}).get("handle")

        if not comment_body or not recipient:
            return jsonify({"status": "noop"}), 200

        parts = comment_body.strip().split(" ", 1)
        if len(parts) != 2:
            return jsonify({"status": "noop"}), 200

        template_name, variable_text = parts
        content_sid = TEMPLATE_CONTENT_MAP.get(template_name)

        if not content_sid:
            return jsonify({"status": "noop"}), 200

        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM]):
            print("Missing Twilio credentials. Skipping send.")
            return jsonify({"status": "noop"}), 200    

        print("📣 About to call send_whatsapp_template")
        send_status = send_whatsapp_template(recipient, content_sid, {"1": variable_text})
        return jsonify(send_status), 200

    except Exception as e:
        print("Exception in webhook:", str(e))
        return jsonify({"status": "noop", "error": str(e)}), 200

def send_whatsapp_template(to_number, content_sid, variables):
    print("➡️ send_whatsapp_template called")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "To": f"whatsapp:{to_number}",
        "From": f"whatsapp:{TWILIO_WHATSAPP_FROM}",
        "ContentSid": content_sid,
        "ContentVariables": json.dumps(variables)
    }

    print("Sending payload to Twilio:", payload)
    response = requests.post(
        url, headers=headers, data=payload, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    )

    print("Twilio response code:", response.status_code)
    print("Twilio response text:", response.text)

    if response.status_code == 201:
        return {"status": "success"}
    else:
        return {"status": "error", "details": response.text}

@app.route("/test-send", methods=["POST"])
def test_send():
    phone = request.json.get("phone")
    template_name = request.json.get("template")
    variable_text = request.json.get("variable")

    content_sid = TEMPLATE_CONTENT_MAP.get(template_name)
    if not content_sid:
        return jsonify({"status": "error", "msg": "Unknown template"}), 400

    result = send_whatsapp_template(phone, content_sid, {"1": variable_text})
    return jsonify(result), 200


if __name__ == "__main__":
    app.run(debug=True)