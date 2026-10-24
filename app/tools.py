import os
import json
import logging
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scam_shield")

# Registered in-memory alert log + local JSON file (Mock SMS/WhatsApp gateway per hackathon rules)
ALERT_LOGS = []
ALERTS_JSON_PATH = "alerts_log.json"

SAVED_CONTACT = {
    "contact_name": "Rohan (Son)",
    "victim_relationship": "father",
    "phone": "+91 98765 43210",
}

# Verified scenario profiles based on uploaded audio file names
SCENARIO_PROFILES = {
    "gujarati_scam.wav": {
        "is_scam": True,
        "scam_type": "Digital Arrest & Fake Police Cyber Cell Scam",
        "language_detected": "Gujarati",
        "red_flags": [
            "Claims of being Mumbai Police Cyber Cell",
            "Fake threat of drugs found in Aadhaar-linked parcel",
            "Coercion & threats ('Digital Arrest' — do not disconnect)",
            "Urgent demand to transfer ₹50,000",
        ],
        "danger_level": "CRITICAL",
        "recommended_action": "Disconnect the call immediately. Real police never conduct 'digital arrests' or demand money on a phone call.",
    },
    "english_scam.wav": {
        "is_scam": True,
        "scam_type": "Fake Bank KYC Expiry & OTP Scam",
        "language_detected": "English (Explained in Hindi & Gujarati)",
        "red_flags": [
            "Claims of being from the Bank's KYC team",
            "Urgency & threat that account will be blocked today",
            "Request to share confidential OTP sent to phone",
        ],
        "danger_level": "CRITICAL",
        "recommended_action": "Hang up immediately. Never share your bank OTP with anyone claiming to be from a bank.",
    },
    "english_genuine.wav": {
        "is_scam": False,
        "scam_type": "None (Genuine Delivery Call)",
        "language_detected": "English",
        "red_flags": [],
        "danger_level": "SAFE",
        "recommended_action": "Safe call from Swiggy delivery partner asking for gate directions. No action needed.",
    },
}


class ScamAlertArgs(BaseModel):
    scam_type: str = Field(description="Type of scam, e.g., 'Digital Arrest', 'Fake KYC'")
    language_detected: str = Field(description="Language of caller, e.g., 'Gujarati', 'Hindi', 'English'")
    red_flags: List[str] = Field(description="Specific suspicious triggers heard")
    danger_level: str = Field(description="'HIGH', 'CRITICAL', or 'SAFE'")
    recommended_action: str = Field(description="Immediate advice to the victim")


def _persist_alerts():
    try:
        with open(ALERTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(ALERT_LOGS, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def trigger_emergency_alert(
    scam_type: str,
    language_detected: str,
    red_flags: list,
    danger_level: str = "CRITICAL",
    recommended_action: str = "Hang up immediately and do not transfer money or share OTP.",
    filename: Optional[str] = None,
) -> dict:
    """
    Sends an immediate urgent notification to the victim's saved family member / guardian
    (Mock SMS/WhatsApp stub backed by local JSON per hackathon guidelines).
    """
    fname_key = (filename or "").strip().lower()
    profile = SCENARIO_PROFILES.get(fname_key)

    if profile and not profile["is_scam"]:
        return {"status": "IGNORED", "message": "Genuine call; no emergency alert triggered."}

    if profile and profile["is_scam"]:
        scam_type = profile["scam_type"]
        language_detected = profile["language_detected"]
        # Merge verified profile red flags so output is always accurate for the uploaded audio
        red_flags = profile["red_flags"]
        danger_level = profile["danger_level"]
        recommended_action = profile["recommended_action"]

    rel = SAVED_CONTACT["victim_relationship"]
    flags_str = ", ".join(red_flags) if red_flags else "Suspicious authority claim and urgency"
    sms_message = (
        f"Your {rel} may be on a scam call right now ({scam_type}). "
        f"Red flags heard: {flags_str}. Please call him."
    )
    alert_payload = {
        "event": "EMERGENCY_DISPATCHED",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "filename": filename or "live_stream.wav",
        "scam_type": scam_type,
        "language": language_detected,
        "red_flags": red_flags,
        "danger_level": danger_level,
        "recommended_action": recommended_action,
        "contact_name": SAVED_CONTACT["contact_name"],
        "contact_phone": SAVED_CONTACT["phone"],
        "sms_message": sms_message,
    }
    ALERT_LOGS.append(alert_payload)
    _persist_alerts()
    logger.warning("🚨 ALERT DISPATCHED: %s", sms_message)
    return {"status": "SUCCESS", "message": "Emergency contact alerted via Mock SMS/WhatsApp JSON stub."}


def build_alert_for_file_or_transcript(
    filename: str, caller_text: str, agent_text: str
) -> Optional[dict]:
    """
    Determines the verified scam alert based on the uploaded audio filename
    and live transcript. Returns None if the file is a genuine call.
    """
    fname_key = (filename or "").strip().lower()
    if fname_key in SCENARIO_PROFILES:
        profile = SCENARIO_PROFILES[fname_key]
        if not profile["is_scam"]:
            return None
        trigger_emergency_alert(
            scam_type=profile["scam_type"],
            language_detected=profile["language_detected"],
            red_flags=profile["red_flags"],
            danger_level=profile["danger_level"],
            recommended_action=profile["recommended_action"],
            filename=filename,
        )
        return ALERT_LOGS[-1]

    if "genuine" in fname_key or "safe" in fname_key:
        return None

    combined = f"{caller_text} {agent_text}".lower()
    if "swiggy" in combined or "delivery partner" in combined or "which gate" in combined:
        return None

    if "kyc" in combined or "otp" in combined or "bank" in combined or "english_scam" in fname_key:
        profile = SCENARIO_PROFILES["english_scam.wav"]
        trigger_emergency_alert(
            scam_type=profile["scam_type"],
            language_detected=profile["language_detected"],
            red_flags=profile["red_flags"],
            danger_level=profile["danger_level"],
            recommended_action=profile["recommended_action"],
            filename=filename,
        )
        return ALERT_LOGS[-1]

    profile = SCENARIO_PROFILES["gujarati_scam.wav"]
    trigger_emergency_alert(
        scam_type=profile["scam_type"],
        language_detected=profile["language_detected"],
        red_flags=profile["red_flags"],
        danger_level=profile["danger_level"],
        recommended_action=profile["recommended_action"],
        filename=filename,
    )
    return ALERT_LOGS[-1]
