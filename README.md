# 🛡️ Scam Call Shield · Real-Time Voice AI Agent

A sub-second, mid-call guardian system that protects senior citizens and first-time smartphone users from extortion schemes ("Digital Arrest", Courier Narcotics claims, and fake KYC frauds). 

Unlike traditional STT transcript scrapers that miss colloquial Hindi and Gujarati, Scam Call Shield streams audio directly through **Google Gemini Native Audio (Live API)** via the **Google Agent Development Kit (ADK)** pattern.

---

## 🌟 Key Features

1. **Mid-Call Interruption**: Audio is ingested in 0.5s PCM slices. Gemini analyzes acoustic and conversational intent mid-stream rather than waiting for the call to end.
2. **Native Indic Audio Reasoning**: Comprehends conversational Gujarati, Hindi, and English without brittle intermediary transcriptions.
3. **No False Alarms ("Does not cry wolf")**: Stays completely silent during authentic courier and daily service calls (e.g., Swiggy delivery partner asking about gates).
4. **Instant Spoken Counter-Warning**: Directly speaks to the victim in simple Gujarati (`ચેતવણી! આ એક ફેક કૉલ છે...`) or Hindi (`सावधान! यह एक फर्जी कॉल है...`), warning them to disconnect.
5. **Auto-Emergency Dispatch Tool**: Automatically calls `trigger_emergency_alert()` to notify family contacts via SMS/WhatsApp with identified red flags (urgency, money demand, fake police authority).

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+
- Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/)

### 2. Setup
```bash
git clone <your-repo>
cd scam-call-shield

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
```

Add your Gemini API key in `.env`:
```env
GEMINI_API_KEY=AIzaSy...
```

### 3. Add Pre-Recorded `.wav` Calls
Place your `.wav` recordings in `static/audio/` (or in the project root, or upload them directly via the web UI).

### 4. Run the Application
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser at **`http://localhost:8000`**.

---

## 🧪 Testing the 4 Scenarios

| Test Case | Scenario Description | Expected Outcome |
| :--- | :--- | :--- |
| **Gujarati Scam** | Mumbai Cyber Cell claims drugs were found in a parcel; demands ₹50,000 for "digital arrest" clearance. | **MID-CALL WARNING** in spoken Gujarati. Alert dispatched to son. |
| **Hindi Scam** | Police cyber cell threatening "digital arrest" unless money is transferred immediately. | **MID-CALL WARNING** in spoken Hindi. Red flags highlighted. |
| **English KYC Scam** | Impersonating bank KYC team requesting urgent OTP to avoid account block. | **MID-CALL WARNING** in English against sharing OTPs. |
| **English Genuine** | Swiggy delivery rider asking which gate to enter. | **AGENT REMAINS SILENT**. No alerts fired (avoids crying wolf). |
