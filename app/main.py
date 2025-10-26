from fastapi import FastAPI, HTTPException, Request, Form, Depends, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from app.models import EventLog
from app.db import SessionLocal, create_db, get_db
from app import zapier
from twilio.rest import Client as TwilioClient
import requests
import os
import base64

# Import new API routers
from app.app import leads, active_loans, portfolio, tasks, calendar

app = FastAPI(
    title="Mortgage CRM API",
    description="Complete CRM system for mortgage lead and loan management",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Register all API routers
app.include_router(zapier.router)
app.include_router(leads.router)
app.include_router(active_loans.router)
app.include_router(portfolio.router)
app.include_router(tasks.router)
app.include_router(calendar.router)

@app.on_event("startup")
def on_startup():
    create_db()

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("static/crm.html")

def log_event(db: Session, event_type, from_number, body_or_status):
    entry = EventLog(event_type=event_type, from_number=from_number, body_or_status=body_or_status)
    db.add(entry)
    db.commit()

# --- Email (SMTP2GO) ---
SMTP2GO_API_KEY = os.getenv("SMTP2GO_API_KEY")
SMTP2GO_SENDER = os.getenv("SMTP2GO_SENDER")

@app.post("/send-email")
async def send_email(
    to: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    cc: str = Form(None),
    bcc: str = Form(None),
    html_body: str = Form(None),
    attachments: list[UploadFile] = File(default_factory=list)
):
    url = "https://api.smtp2go.com/v3/email/send"
    payload = {
        "api_key": SMTP2GO_API_KEY,
        "to": [addr.strip() for addr in to.split(",")],
        "sender": SMTP2GO_SENDER,
        "subject": subject,
        "text_body": body
    }
    if cc:
        payload["cc"] = [addr.strip() for addr in cc.split(",")]
    if bcc:
        payload["bcc"] = [addr.strip() for addr in bcc.split(",")]
    if html_body:
        payload["html_body"] = html_body
    if attachments:
        payload["attachments"] = []
        for upload in attachments:
            file_data = await upload.read()
            b64content = base64.b64encode(file_data).decode()
            payload["attachments"].append({
                "filename": upload.filename,
                "content": b64content
            })
    response = requests.post(url, json=payload)
    resp_json = response.json()
    if response.status_code == 200 and resp_json.get("data", {}).get("succeeded"):
        return JSONResponse(content={"detail": "Email sent successfully", "smtp2go": resp_json})
    else:
        raise HTTPException(status_code=400, detail={"smtp2go": resp_json})

# --- SMS / Call (Twilio) ---
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)

class SmsReq(BaseModel):
    to: str
    body: str

@app.post("/send-sms")
def send_sms(req: SmsReq, db: Session = Depends(get_db)):
    msg = twilio_client.messages.create(
        body=req.body,
        from_=TWILIO_NUMBER,
        to=req.to
    )
    log_event(db, "SMS", req.to, req.body)
    if msg.error_code:
        raise HTTPException(status_code=400, detail=msg.error_message)
    return {"sid": msg.sid}

class CallReq(BaseModel):
    to: str

@app.post("/make-call")
def make_call(req: CallReq, db: Session = Depends(get_db)):
    call = twilio_client.calls.create(
        to=req.to,
        from_=TWILIO_NUMBER,
        url="https://handler.twilio.com/twiml/EH..."  # Replace with your TwiML URL!
    )
    log_event(db, "CALL", req.to, "call initiated")
    if call.error_code:
        raise HTTPException(status_code=400, detail=call.error_message)
    return {"sid": call.sid}
