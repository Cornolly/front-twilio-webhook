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

# Check for required environment variables
required_vars = ["PIPEDRIVE_API_KEY", "SEND_QUOTE_API_KEY"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    print(f"⚠️ Missing required environment variables: {missing_vars}")
else:
    print("✅ All required environment variables are set")

print("🚀 Application initialization complete")

# Template-to-ContentSid mapping
TEMPLATE_CONTENT_MAP = {
    "payment_released": "HX6b4482f404e6b063984df49dc3b3e69c",
    "settlement_received": "HX706c585bc08250b45418ae5c6da063a9",
    "24hrs": "HX1e412e64b25964ab226f5de522dab1eb",
    "ftt_chase": "HXfe271e7714fa29bb31625c1080081d8b",
    "payment_account": "HX373b8d1366c112e7001acffe88f99056",
    "payment_which": "HX6434eec56092adba95513f65d82bc26d",
    "gb_sar": "HX046f744c9a57569d809d7c1954b867ef",
    "colleagues": "HXcf671083796da95467bb1b5b84b0def0",
    "activated": "HX3c3ffc8ee57ffaf52d5fc1b5333129d3",
    "sar_scio": "HX04e292959d0113b0860b44308a83e5d1",
    "head_of_trading": "HX1ea7ef8a998d1ede17f89b2bfdac384e",
    "quote_followup": "HX7783b35f18ce38d7c87c6aa34c5375e8",
    "market_update_ftt": "HX765872487eed72459937b3e85fd4d549",
    "quote_amount": "HX4e63c9c8e2d3234fd6b99d3ea1a14f45",
    "feefo_request": "HX3cb6b2df08b5da2f129fa14db6360d05",
    "request_settlement_confirmation": "HXf38446e303ffe1001116f80f5cecce22",
    "payment_released_referral": "HXb9566f7e05bade6949bd6da2ee650bb6",
    "tips": "HX88c606bc1918c125393d36e396e03a5c",
    "signup_docs": "HXcb0286305fa09c209e9d9f4ea3caf08b",
    "sab_statement": "HXcc7b9f2ca20de356d49781c4ffb49c2a",
    "get_started": "HXa5b6d2a538543999fc8820cb414fbdf7",
    "quote_tips": "HX0a5cb200cc70c627679db007daaa3980",
    "doc_email": "HX2c36decd6afee23ed75f7769a389f1fc",
    "scio_terms": "HX42cda745d4c86d237b57a261495023af",
    "signaturesense": "HX6a7f72d93eef510bf9ace988fcdf2f5b",
    "scio_and_equals_terms": "HXe63f2f4a3c64e9f8fbca83c8d123db43",
    "docs_chaser": "HX416ab0e4a1b6b24a069a844ba8fce956",
    "1k_reminder": "HXaf766506fce839520e9581c77075a0fd",
    "next_exchange": "HXff6a8e293fd00d9ba474f191817bb2d2",
    "api_down": "HX010913785628c422e493b900b30e8195",
    "signaturesense_sumsub": "HXe7f127f05b981706891376ff7dc41d11",
    "ftt_chase_calendar": "HXbc7ae8533ff4ae809ccac7094c431ca3"
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
    "quote_amount": "a322fbaee9c8c63ddee6f733873f4ca8204233fb",
    "feefo_request": "b516f03e81f6b97e31db84296acd148c4152afdc",
    "request_settlement_confirmation": "aa06fc13c3f373d94bc711a134ddf49515ce38c7",
    "payment_released_referral": "76678853d8dd0b4a6f2d1d40915431bd893fc5fc",
    "tips": "6d72df5ef2b9eb2694ab21a22af5e5705717affd",
    "signup_docs": "de76832c599bfedd14e027666f7b418ed90a65ce",
    "sab_statement": "fee0adba212034720f41444545bc97e10154f045",
    "get_started": "edeb777424af67eefd570f1e6f8d6e7e5d39e09e",
    "quote_tips": "d03d8914feae2025033af46c1d24e09144262693",
    "doc_email": "98d619ca6534ea827eb3465f9e5fda92f0578b32",
    "scio_terms": "bb58212d8bd299b571ae5aa22d15269212de102d",
    "signaturesense": "8ff2ba4e3f4df6a8ac45ff315c7bef513c8234bc",
    "scio_and_equals_terms": "37dc201b65b005dc0ab4bf6357a34a27101fadde",
    "docs_chaser": "a9431ed821dff1ce0ea03296ca6f3c0da7c46c55",
    "1k_reminder": "481cb2d8d31f9d6ab52346777d16d72023f00747",
    "next_exchange": "9a02d5a0f564d482747187ebf9ac0798d37ae0fd",
    "api_down": "eaffe302dc8d9a5e76d1bc25056e445d09750de8",
    "signaturesense_sumsub": "1cb2222c14a45ac2a7b10fab2e046f4fc7b5050e",
    "ftt_chase_calendar": "0b029c44cbb019951c693950892624ca4c58d94c"
}


@app.route("/", methods=["GET"])
def home():
    print("Health check received")  # Add this line
    return "Webhook server is running", 200

@app.route("/health", methods=["GET"])  # Add this route
def health():
    print("Health endpoint hit")
    return jsonify({"status": "healthy"}), 200

def debug_print(*args, **kwargs):
    if DEBUG_MODE:
        print(*args, **kwargs)

@app.route("/front-webhook", methods=["GET"])
def verify_webhook():
    return jsonify({"status": "ok"}), 200

def split_pair_to_vars(pair_text: str):
    """Accepts 'SARGBP', 'sar/gbp', 'SAR GBP' etc. Returns {'1': base, '2': quote, '3': base}."""
    pair = re.sub(r'[^A-Z]', '', (pair_text or '').upper())
    if len(pair) != 6:
        raise ValueError(f"Currency pair must be 6 letters (e.g. SARGBP). Got: {pair_text!r}")
    base, quote = pair[:3], pair[3:]
    return {"1": base, "2": quote, "3": base}

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
                    results.append({"template": template_name, "status": "sent_to_quote_api", "response_code": quote_response.status_code})
                    continue
    
                # ✅ Variable handling logic per template
                if template_name == "24hrs":
                    variables = {}
                elif template_name in ["payment_account", "payment_which", "quote_amount", "feefo_request", "request_settlement_confirmation", "quote_tips", "scio_terms", "scio_and_equals_terms", "1k_reminder"]:
                    # Split into two variables by the first space
                    parts = field_value.strip().split(" ", 1)
                    variables = {
                        "1": parts[0],
                        "2": parts[1] if len(parts) > 1 else ""
                    }

                elif template_name == "tips":
                    # PD field should contain SARGBP (or 'SAR/GBP', 'sar gbp', etc.)
                    try:
                        variables = split_pair_to_vars(field_value)
                    except ValueError as e:
                        print(f"❌ {e}")
                        results.append({"template": template_name, "status": "error", "error": str(e)})
                        continue

                
                elif template_name == "payment_released_referral":
                    raw = field_value.strip()

                    # Prefer a strict delimiter if provided; otherwise split on whitespace ONLY
                    if "|" in raw:
                        tokens = [t.strip() for t in raw.split("|")]
                    else:
                        tokens = raw.split()  # whitespace split (won't split the comma inside 30,001.29)

                    if len(tokens) < 3:
                        print(f"❌ Need 3 variables for payment_released_referral, got: {tokens}")
                        results.append({"template": template_name, "status": "error", "error": "Need 3 variables: amount currency pd_id"})
                        continue

                    amount_raw, currency_raw, pd_id_raw = tokens[0], tokens[1], tokens[2]

                    # Normalise amount: strip currency symbols/spaces, remove thousands commas
                    amount_norm = re.sub(r'^[£$\u20ac]\s*', '', amount_raw).replace(",", "")
                    # Optional: validate it's numeric
                    try:
                        float(amount_norm)
                    except ValueError:
                        print(f"❌ Invalid amount for payment_released_referral: {amount_raw}")
                        results.append({"template": template_name, "status": "error", "error": "Invalid amount"})
                        continue

                    # Normalise currency (expect a 3-letter code)
                    currency = currency_raw.upper()

                    # PD person id should be digits
                    if not re.fullmatch(r"\d+", pd_id_raw):
                        print(f"❌ Invalid PD ID for payment_released_referral: {pd_id_raw}")
                        results.append({"template": template_name, "status": "error", "error": "Invalid PD ID"})
                        continue

                    variables = {
                        "1": amount_norm,  # e.g., 30001.29
                        "2": currency,     # e.g., GBP
                        "3": pd_id_raw,    # e.g., 9
                    }


                elif template_name.lower() == "quote":
                    # Special case: send to quote endpoint instead of Twilio
                    parts = field_value.strip().split(" ", 2)
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

                    quote_response = requests.post(
                        "https://quote-production-f1f1.up.railway.app/send_quote",
                        headers={
                            "Content-Type": "application/json",
                            "X-API-KEY": os.getenv("SEND_QUOTE_API_KEY")
                        },
                        json=quote_payload
                    )

                    print(f"Quote API: {quote_response.status_code}")

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
                    print(f"Activity: {activity_resp.status_code}")
                    
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
            print("Front ping received")
            return jsonify({"status": "noop"}), 200

        print("Front event received")

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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)  # Set debug=False for production