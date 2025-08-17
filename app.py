from flask import Flask, request, jsonify, make_response
import os
import requests
import json
from dotenv import load_dotenv
import re

DEBUG_MODE = os.getenv("DEBUG_LOGGING", "false").lower() == "true"

load_dotenv()

app = Flask(__name__)

# Twilio config
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
SEND_QUOTE_API_KEY = os.getenv("SEND_QUOTE_API_KEY")

print("TWILIO_ACCOUNT_SID:", TWILIO_ACCOUNT_SID)
print("TWILIO_AUTH_TOKEN:", TWILIO_AUTH_TOKEN)
print("TWILIO_WHATSAPP_FROM:", TWILIO_WHATSAPP_FROM)

# Template-to-ContentSid mapping
TEMPLATE_CONTENT_MAP = {
    "payment_released": "HX6b4482f404e6b063984df49dc3b3e69c",
    "settlement_received": "HX706c585bc08250b45418ae5c6da063a9",
    "24hrs": "HXbafe219694047b3d258a789df58da66d",
    "ftt_chase": "HX21c148fcfa188caf77143550a4063e27",
    "payment_account": "HX373b8d1366c112e7001acffe88f99056",
    "payment_which": "HX6434eec56092adba95513f65d82bc26d",
    "gb_sar": "HX046f744c9a57569d809d7c1954b867ef",
    "colleagues": "HXcf671083796da95467bb1b5b84b0def0",
    "activated": "HX3c3ffc8ee57ffaf52d5fc1b5333129d3",
    "sar_scio": "HX04e292959d0113b0860b44308a83e5d1",
    "head_of_trading": "HX1ea7ef8a998d1ede17f89b2bfdac384e",
    "quote_followup": "HX7783b35f18ce38d7c87c6aa34c5375e8",
    "market_update_ftt": "HX765872487eed72459937b3e85fd4d549",
    "quote_amount": "HX4e63c9c8e2d3234fd6b99d3ea1a14f45"
}

# Maps template name to Pipedrive custom field ID
TEMPLATE_FIELD_MAP = {
    "payment_released": "cd83bf5536c29ee8f207e865c81fbad299472bfc",
    "settlement_received": "7ea7e0624f14fc357ce115cd3a309741aabbb675",
    "24hrs": "981fcfd49cf65cc359f674004e399d89299b1dfd",
    "ftt_chase": "d589136563f5f59c2de084c96c44dd92c5890744",
    "payment_account": "ee1b54060e98b53bdd2e08a3248afe7e198c2227",
    "payment_which": "2fc9cb4ff0a04b9fec4aae5c55e4e4b39b63f7c2",
    "quote": "27ac627ce1339c99142bbe05d5ce4a11003c66c1",
    "gb_sar": "f193b896c739db7c7f99788dd9acf66beba21122",
    "colleagues": "afda66ec61e5a2032bf3869d7acb24ff32655fda",
    "activated": "d7fee5e8a8c5d835ff176ea06df6876f46106ede",
    "sar_scio": "a556f699bda90c9e004281d81bb8d87f9edb242d",
    "head_of_trading": "8717e7292d0ea7ebca11632451d4db47d21bab02",
    "quote_followup": "dfa936e60f48aae47fe4fc277052613b4d571434",
    "market_update_ftt": "71abec0fdc5e9e691c7332a95b4bad3b72559371",
    "quote_amount": "a322fbaee9c8c63ddee6f733873f4ca8204233fb"
}

def debug_print(*args, **kwargs):
    if DEBUG_MODE:
        print(*args, **kwargs)

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
        #print("📥 Received PD webhook:", json.dumps(data, indent=2))

        person_data_raw = data.get("data", {})
        person_id = (
            data.get("meta", {}).get("entity_id") or
            data.get("current", {}).get("id")
        )

        if not person_id:
            print("⚠️ No person_id in webhook meta")
            return jsonify({"status": "noop", "error": "Missing person_id"}), 200

        # Fetch person from Pipedrive to get phone number
        person_url = f"https://api.pipedrive.com/v1/persons/{person_id}?api_token={os.getenv('PIPEDRIVE_API_KEY')}"
        resp = requests.get(person_url)
        person_info = resp.json()

        #print("📦 Full Pipedrive API response:", json.dumps(person_info, indent=2))

        person_data = person_info.get("data")
        if not person_data:
            print("⚠️ Person data missing in API response")
            return jsonify({"status": "noop", "error": "Person not found"}), 200

        # Extract phone
        phones = person_data.get("phone", [])
        phone = phones[0]["value"] if phones else None
        if not phone:
            print("⚠️ No phone number found in person record")
            return jsonify({"status": "noop", "error": "No phone number"}), 200

        results = []
        custom_fields = person_data_raw.get("custom_fields", {})

        for template_name, field_id in TEMPLATE_FIELD_MAP.items():
            field = custom_fields.get(field_id)
            field_value = field.get("value") if field else None

            # ✅ Only trigger if current value is not empty and previous value was empty
            previous_fields = data.get("previous", {}).get("custom_fields", {})
            previous_value = None

            if previous_fields and field_id in previous_fields:
                prev_field = previous_fields.get(field_id)
                if prev_field and isinstance(prev_field, dict):
                    previous_value = prev_field.get("value")
            
            if field_value and not previous_value:
                print(f"📤 {template_name} → {phone}")
                content_sid = TEMPLATE_CONTENT_MAP.get(template_name)

                if not content_sid:
                    results.append({"template": template_name, "status": "error", "error": "Unknown ContentSid"})
                    continue
    
                # ✅ Variable handling logic per template
                if template_name == "24hrs":
                    variables = {}
                elif template_name in ["payment_account", "payment_which", "quote_amount"]:
                    # Split into two variables by the first space
                    parts = field_value.strip().split(" ", 1)
                    variables = {
                        "1": parts[0],
                        "2": parts[1] if len(parts) > 1 else ""
                    }
                elif template_name.lower() == "quote":
                    print("DEBUG: Entered quote template handler")
                    # Special case: send to quote endpoint instead of Twilio
                    parts = field_value.strip().split(" ", 2)
                    print(f"DEBUG: parts = {parts}")  # Shows split result
                    if len(parts) != 3:
                        print(f"❌ Invalid Quote field format: {field_value}")
                        results.append({"template": template_name, "status": "error", "error": "Invalid format"})
                        continue  # Skip this iteration

                    pair = parts[0]
                    direction = parts[1]
                    amount = parts[2].replace(",", "").replace("£", "")  # Strip commas or currency symbols if needed
                    try:
                        amount_value = float(amount.replace(",", ""))
                    except ValueError:
                        print(f"❌ Invalid amount in Quote field: {amount}")
                        results.append({"template": template_name, "status": "error", "error": "Invalid amount"})
                        continue

                    quote_payload = {
                        "phone": phone,
                        "pair": pair,
                        "direction": direction,
                        "amount": amount_value
                    }

                    print(f"🚀 Sending Quote payload: {quote_payload}")
                    print("Sending Quote API request with API key:", repr(os.getenv("SEND_QUOTE_API_KEY")))
                    quote_response = requests.post(
                        "https://quote-production-f1f1.up.railway.app/send_quote",
                        headers={
                            "Content-Type": "application/json",
                            "X-API-KEY": os.getenv("SEND_QUOTE_API_KEY")
                        },
                        json=quote_payload
                    )

                    print("📩 Quote API response:", quote_response.status_code, quote_response.text)

                    # ✅ Clear the Pipedrive field after quote send, even if no Twilio message
                    clear_url = f"https://api.pipedrive.com/v1/persons/{person_id}?api_token={os.getenv('PIPEDRIVE_API_KEY')}"
                    clear_payload = {field_id: ""}
                    clear_resp = requests.put(clear_url, json=clear_payload)
                    print(f"🧹 Cleared field {field_id}: {clear_resp.status_code}")

                    results.append({"template": template_name, "status": "sent_to_quote_api", "response": quote_response.text})
                    continue  # Skip Twilio send for Quote
                
                else:
                    variables = {"1": field_value}

                send_status = send_whatsapp_template(phone, content_sid, variables)
                results.append({"template": template_name, "status": send_status.get("status")})

                # Clear the field if successful
                if send_status.get("status") == "success":
                    # Compose the note with variables and full message
                    note_text = (
                        f"Variables: {json.dumps(variables, indent=2)}\n\n"
                        f"Full Message:\n{field_value.strip()}"
                    )
                    # ✅ Log Activity in Pipedrive
                    activity_payload = {
                        "subject": f"WhatsApp Message Sent: {template_name}",
                        "done": 1,
                        "person_id": person_id,
                        "note": note_text,
                        "type": "whatsapp"
                    }
                    activity_url = f"https://api.pipedrive.com/v1/activities?api_token={os.getenv('PIPEDRIVE_API_KEY')}"
                    activity_resp = requests.post(activity_url, json=activity_payload)
                    print("📌 Activity logged:", activity_resp.status_code, activity_resp.text)
                    
                    # Clear the field if successful
                    clear_url = f"https://api.pipedrive.com/v1/persons/{person_id}?api_token={os.getenv('PIPEDRIVE_API_KEY')}"
                    clear_payload = {field_id: ""}
                    clear_resp = requests.put(clear_url, json=clear_payload)
                    print(f"🧹 Cleared field {field_id}: {clear_resp.status_code}")

        if not results:
            print("ℹ️ No fields with values found to process")
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

def sanitize_number(number):
    number = number.strip()
    if number.startswith('+'):
        return '+' + re.sub(r'\D', '', number[1:])
    else:
        # If the number begins without +, add it:
        return '+' + re.sub(r'\D', '', number) 

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
    sanitized_number = sanitize_number(to_number)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "To": f"whatsapp:{sanitized_number}",
        "From": f"whatsapp:{TWILIO_WHATSAPP_FROM}",
        "ContentSid": content_sid,
        "ContentVariables": json.dumps(variables)
    }
    
    response = requests.post(
        url, headers=headers, data=payload, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    )

    # Single line result instead of multiple prints
    print(f"Twilio: {response.status_code}")

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