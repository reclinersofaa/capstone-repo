from pathlib import Path
from datetime import datetime, timezone
import random
import threading
import time
import os
import smtplib
from email.message import EmailMessage

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ROOT = Path(__file__).resolve().parents[2]

EMAILS_FILE = ROOT / "human_experiment" / "data" / "human_emails.csv"

# This file stores participant → email assignments.
ASSIGNMENTS_FILE = (
    ROOT / "human_experiment" / "data" / "assignments.csv"
)

# This will store participant responses later.
RESULTS_FILE = (
    ROOT / "human_experiment" / "data" / "experiment_results.csv"
)

DELIVERIES_FILE = ROOT / "human_experiment" / "data" / "experiment_deliveries.csv"

PARTICIPANTS_FILE = (
    ROOT / "human_experiment" / "data" / "participants.csv"
)


emails = pd.read_csv(
    EMAILS_FILE,
    keep_default_na=False,
)



participants = pd.read_csv(
    PARTICIPANTS_FILE,
    keep_default_na=False,
)


print(f"Loaded {len(participants)} participants")

class ResponseRequest(BaseModel):
    participant_id: str
    trial_id: str
    decision: str
    opened_at: str
    answered_at: str

print(f"Loaded {len(emails)} human-experiment emails")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def load_assignments():
    if not ASSIGNMENTS_FILE.exists():
        return pd.DataFrame(
            columns=[
                "participant_id",
                "trial_id",
                "email_id",
                "assigned_at",
            ]
        )

    return pd.read_csv(
        ASSIGNMENTS_FILE,
        keep_default_na=False,
    )


def save_assignments(df):
    df.to_csv(
        ASSIGNMENTS_FILE,
        index=False,
    )

def load_results():
    if not RESULTS_FILE.exists():
        return pd.DataFrame(
            columns=[
                "participant_id",
                "trial_id",
                "email_id",
                "scheduled_at",
                "sent_at",
                "opened_at",
                "answered_at",
                "reaction_time_ms",
                "decision",
                "actual_class",
                "correct",
            ]
        )

    return pd.read_csv(
        RESULTS_FILE,
        keep_default_na=False,
    )

def save_deliveries(deliveries):
    deliveries.to_csv(DELIVERIES_FILE, index=False)


def load_deliveries():
    if not DELIVERIES_FILE.exists():
        return pd.DataFrame(
            columns=[
                "participant_id",
                "trial_id",
                "email_id",
                "scheduled_at",
                "sent_at",
            ]
        )

    return pd.read_csv(
        DELIVERIES_FILE,
        keep_default_na=False,
    )

if not DELIVERIES_FILE.exists():
    save_deliveries(load_deliveries())


def save_results(df):
    df.to_csv(
        RESULTS_FILE,
        index=False,
    )


def parse_timestamp(value):
    try:
        timestamp = pd.to_datetime(value, utc=True)

        if pd.isna(timestamp):
            raise ValueError

        return timestamp

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid timestamp",
        )

def send_email(to_address, subject, body):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Gmail credentials are not configured")

    message = EmailMessage()
    message["From"] = GMAIL_ADDRESS
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(message)

def build_experiment_link(participant_id, trial_id):
    return (
        "http://localhost:5173/"
        f"?participant={participant_id}&trial={trial_id}"
    )


def build_notification_body(participant_id, trial_id):
    link = build_experiment_link(participant_id, trial_id)


def run_scheduler():
    schedule = {
        "08:00": "T01",
        "10:00": "T02",
        "12:00": "T03",
        "14:00": "T04",
        "16:00": "T05",
    }

    while True:
        now = datetime.now().strftime("%H:%M")

        if now in schedule:
            trial_id = schedule[now]

            for _, participant in participants.iterrows():
                participant_id = str(participant["participant_id"])
                recipient = str(participant["email"])

                assignments = load_assignments()

                existing_assignment = assignments[
                    (assignments["participant_id"].astype(str) == participant_id)
                    & (assignments["trial_id"].astype(str) == trial_id)
                ]

                if len(existing_assignment) > 0:
                    email_id = int(existing_assignment.iloc[0]["email_id"])
                else:
                    email_row = get_assigned_email(
                        participant_id,
                        trial_id,
                    )
                    email_id = int(email_row["email_id"])

                deliveries = load_deliveries()

                already_sent = deliveries[
                    (deliveries["participant_id"].astype(str) == participant_id)
                    & (deliveries["trial_id"].astype(str) == trial_id)
                ]

                if len(already_sent) > 0:
                    continue

                body = build_notification_body(
                    participant_id,
                    trial_id,
                )

                send_email(
                    recipient,
                    "Email Classification Experiment",
                    body,
                )

                new_delivery = pd.DataFrame([{
                "participant_id": participant_id,
                "trial_id": trial_id,
                "email_id": email_id,
                "scheduled_at": now,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                }])

                deliveries = pd.concat(
                    [deliveries, new_delivery],
                    ignore_index=True,
                )

                save_deliveries(deliveries)

        time.sleep(60)




def build_notification_body(participant_id, trial_id):
    link = build_experiment_link(participant_id, trial_id)

    return f"""Hello,

Thank you for taking part in this controlled email classification experiment.

Instructions:
Please open the link below. You will be shown an email and asked to classify it as either Benign or Malicious.

Please review the email carefully before making your decision.

Experiment link:
{link}

Please complete the task when you are ready.

Thank you.

Participant ID: {participant_id}
Trial ID: {trial_id}
"""

def get_assigned_email(participant_id, trial_id):
    assignments = load_assignments()

    existing = assignments[
        (assignments["participant_id"].astype(str) == str(participant_id))
        & (assignments["trial_id"].astype(str) == str(trial_id))
    ]

    if len(existing) > 0:
        email_id = int(existing.iloc[0]["email_id"])

        match = emails[
            emails["email_id"].astype(int) == email_id
        ]

        if len(match) > 0:
            return match.iloc[0]

    used_ids = (
    set(assignments["email_id"].astype(int).tolist())
    if len(assignments)
    else set()
)

    available = emails[
        ~emails["email_id"].astype(int).isin(used_ids)
    ]

    if len(available) == 0:
        raise HTTPException(
            status_code=500,
            detail="No unused emails remain for this participant",
        )

    row = available.sample(
        n=1,
        random_state=random.randint(0, 2**32 - 1),
    ).iloc[0]

    assigned_at = datetime.now(timezone.utc).isoformat()

    new_assignment = pd.DataFrame(
        [{
            "participant_id": participant_id,
            "trial_id": trial_id,
            "email_id": int(row["email_id"]),
            "assigned_at": assigned_at,
        }]
    )

    assignments = pd.concat(
        [assignments, new_assignment],
        ignore_index=True,
    )

    save_assignments(assignments)

    return row
# ---------------------------------------------------------
# API
# ---------------------------------------------------------

@app.get("/api/email")
def get_email(
    participant_id: str,
    trial_id: str,
):
    if not participant_id or not trial_id:
        raise HTTPException(
            status_code=400,
            detail="participant_id and trial_id are required",
        )

    row = get_assigned_email(
        participant_id,
        trial_id,
    )

    # IMPORTANT:
    # Never expose actual_class or source.
    results = load_results()

    existing = results[
        (results["participant_id"].astype(str) == str(participant_id))
        & (results["trial_id"].astype(str) == str(trial_id))
    ]

    if len(existing) > 0:
        opened_at = str(existing.iloc[0]["opened_at"])
        submitted = True
    else:
        opened_at = datetime.now(timezone.utc).isoformat()
        submitted = False

    return {
        "email_id": int(row["email_id"]),
        "subject": str(row["subject"]),
        "sender": str(row["sender"]),
        "body": str(row["body"]),
        "extracted_urls": str(row["extracted_urls"]),
        "submitted": submitted,
        "opened_at": opened_at,
}

@app.post("/api/response")
def record_response(payload: ResponseRequest):
    if payload.decision not in {"benign", "phishing"}:
        raise HTTPException(
            status_code=400,
            detail="Decision must be benign or phishing",
        )

    opened = parse_timestamp(payload.opened_at)
    answered = parse_timestamp(payload.answered_at)

    reaction_time_ms = int(
        (answered - opened).total_seconds() * 1000
    )

    if reaction_time_ms < 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid response timing",
        )

    assignments = load_assignments()

    assignment = assignments[
        (assignments["participant_id"].astype(str) == str(payload.participant_id))
        & (assignments["trial_id"].astype(str) == str(payload.trial_id))
    ]

    if len(assignment) == 0:
        raise HTTPException(
            status_code=404,
            detail="No email assignment found",
        )

    results = load_results()

    existing = results[
        (results["participant_id"].astype(str) == str(payload.participant_id))
        & (results["trial_id"].astype(str) == str(payload.trial_id))
    ]

    if len(existing) > 0:
        raise HTTPException(
            status_code=409,
            detail="This trial has already been answered",
        )

    email_id = int(assignment.iloc[0]["email_id"])

    match = emails[
        emails["email_id"].astype(int) == email_id
    ]

    if len(match) == 0:
        raise HTTPException(
            status_code=404,
            detail="Assigned email no longer exists",
        )

    row = match.iloc[0]

    actual_class = int(row["actual_class"])
    predicted_class = 0 if payload.decision == "benign" else 1
    correct = int(predicted_class == actual_class)

    new_result = pd.DataFrame([{
        "participant_id": payload.participant_id,
        "trial_id": payload.trial_id,
        "email_id": email_id,
        "scheduled_at": "",
        "sent_at": "",
        "opened_at": opened.isoformat(),
        "answered_at": answered.isoformat(),
        "reaction_time_ms": reaction_time_ms,
        "decision": payload.decision,
        "actual_class": actual_class,
        "correct": correct,
    }])

    results = pd.concat(
        [results, new_result],
        ignore_index=True,
    )

    save_results(results)

    return {
        "status": "recorded",
        "reaction_time_ms": reaction_time_ms,
    }

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "emails": len(emails),
    }

scheduler_thread = threading.Thread(
    target=run_scheduler,
    daemon=True,
)

scheduler_thread.start()