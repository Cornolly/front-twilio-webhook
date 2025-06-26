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

# Template-to-ContentSid mapping
TEMPLATE_CONTENT_MAP = {
    "payment_released": "HX6b4482f404e6b063984df49dc3b3e69c",
    "settlement_received": "HX706c585bc08250b45418ae5c6da063a9" 
}

@app.route("/", methods=["GET"])
def home():
    return "Webhook server is running", 200

@app.route("/front-webhook", methods=["GET"])
def verify_webhook():
    return jsonify({"status": "ok"}), 200


@app.route("/pd-webhook", methods=["POST"])
def handle_pipedrive_webhook():
    try:
        data = request.get_json()
        print("Received PD webhook:", data)

        # Safety checks
        if not data or "current" not in data or "meta" not in data:
            return jsonify({"status": "noop"}), 200

        current = data["current"]
        person_id = data["meta"].get("id")

        custom_field_value = (
            data.get("current", {}).get("custom_fields", {})
            .get("cd83bf5536c29ee8f207e865c81fbad299472bfc", {})
            .get("value")
        )

        # If empty, check if we are dealing with a field *being cleared* (and grab the old value)
        if not custom_field_value:
            custom_field_value = (
                data.get("previous", {}).get("custom_fields", {})
                .get("cd83bf5536c29ee8f207e865c81fbad299472bfc", {})
                .get("value")
            )

        if not person_id:
            return jsonify({"status": "noop", "error": "Missing person_id"}), 200

        if not custom_field_value:
            return jsonify({"status": "noop", "error": "No value in trigger field"}), 200

        print(f"Raw custom field value: '{custom_field_value}'")

        # Split the field into template and variable
        parts = custom_field_value.strip().split(" ", 1)
        if len(parts) != 2:
            print(f"Invalid format after split: {parts}")
            return jsonify({"status": "noop", "error": "Invalid format"}), 200

        template_name, variable_text = parts

        # Get phone number for this person
        person_url = f"https://api.pipedrive.com/v1/persons/{person_id}?api_token={os.getenv('PIPEDRIVE_API_KEY')}"
        resp = requests.get(person_url)
        person_data = resp.json()

        if not person_data.get("data"):
            return jsonify({"status": "noop", "error": "Person not found"}), 200

        phone = person_data["data"].get("phone", [{}])[0].get("value", "")
        if not phone:
            return jsonify({"status": "noop", "error": "No phone number"}), 200

        # Look up template content SID
        content_sid = TEMPLATE_CONTENT_MAP.get(template_name)
        if not content_sid:
            print(f"Unknown template: {template_name}")
            return jsonify({"status": "noop", "error": "Unknown template"}), 200

        print("=== WhatsApp Send Debug ===")
        print(f"Person ID: {person_id}")
        print(f"Phone: {phone}")
        print(f"Template Name: {template_name}")
        print(f"Variable Text: {variable_text}")
        print(f"Content SID: {content_sid}")
        print("===========================")

        send_status = send_whatsapp_template(phone, content_sid, {"1": variable_text})
        print("Send status:", send_status)

        # ✅ Clear the field to prevent repeat sending
        if send_status.get("status") == "success":
            update_url = f"https://api.pipedrive.com/v1/persons/{person_id}?api_token={os.getenv('PIPEDRIVE_API_KEY')}"
            requests.put(update_url, json={ "cd83bf5536c29ee8f207e865c81fbad299472bfc": "" })

        return jsonify(send_status), 200

    except Exception as e:
        print("Exception in Pipedrive webhook:", str(e))
        return jsonify({"status": "noop", "error": str(e)}), 200



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

        send_status = send_whatsapp_template(recipient, content_sid, {"1": variable_text})
        return jsonify(send_status), 200

    except Exception as e:
        print("Exception in webhook:", str(e))
        return jsonify({"status": "noop", "error": str(e)}), 200

def send_whatsapp_template(to_number, content_sid, variables):
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

if __name__ == "__main__":
    app.run(debug=True)