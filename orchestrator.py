import os
import time
import json
import shutil
import subprocess
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv
import calendar_client

# Load Environment Variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("CRITICAL ERROR: GEMINI_API_KEY not found. Please set it in .env")
    exit(1)

# Configuration
INPUT_DIR = Path("inputs")
PROCESSED_DIR = Path("processed")

# Initialize Calendar Map
print("Loading available calendars...")
try:
    service = calendar_client.get_service()
    CALENDARS = calendar_client.get_calendar_map(service)
    # Ensure primary exists
    if "primary" not in CALENDARS:
        CALENDARS["primary"] = "primary"
    
    print(f"Loaded {len(CALENDARS)} calendars: {list(CALENDARS.keys())}")
except Exception as e:
    print(f"WARNING: Could not load calendars ({e}). Using fallback.")
    CALENDARS = {"primary": "primary"}

DEFAULT_CALENDAR = "brandon" if "brandon" in CALENDARS else "primary"

# Configure GenAI Client (New SDK)
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = 'gemini-2.0-flash-lite-preview-02-05'

SYSTEM_PROMPT = f"""
You are an intelligent calendar assistant. 
I will provide an email body, text, or image. 

The user has the following calendars available: {list(CALENDARS.keys())}

Your goal is to Extract:
1. Event Details (Summary, Start, End)
2. Target Calendar (Category/Person/Topic)
   - Identify who or what this event is for.
   - Match it to one of the available calendars if possible.
   - If it effectively refers to a specific person or topic not in the list, use that new name (we will create it).
   - Only default to "{DEFAULT_CALENDAR}" if the event is clearly personal to the main user or unspecified.
3. Recurrence
   - If the user implies a recurring event (e.g., "every Tuesday", "weekly meeting"), generate a valid RRULE string.
   - Example: "RRULE:FREQ=WEEKLY;BYDAY=TU"
   - If not recurring, return null.

Return a JSON object:
{{
  "summary": "Short title",
  "start": "ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
  "end": "ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
  "description": "Any context",
  "calendar": "existing_name_or_new_name_or_default", 
  "recurrence": "RRULE:..." or null,
  "confidence": "Low/Medium/High"
}}
IMPORTANT: Assume current year is 2026.
"""

def process_file(file_path):
    print(f"Processing: {file_path}")
    
    try:
        content = []
        content.append(SYSTEM_PROMPT)
        
        # Determine input type
        if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
            # Load image bytes
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            # In new SDK, we can pass image objects or bytes directly if configured, 
            # but types.Part.from_bytes is a standard way.
            # Assuming mime type based on extension
            mime = "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
            content.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        else:
            # Assume text
            with open(file_path, "r") as f:
                text_content = f.read()
            content.append(text_content)

        # Generate Content
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=content,
            config=types.GenerateContentConfig(
                response_mime_type="application/json" # Use JSON mode for reliability
            )
        )

        response_text = response.text
        # JSON mode usually returns clean JSON, but just in case
        if "```json" in response_text:
            response_text = response_text.replace("```json", "").replace("```", "")
        
        data = json.loads(response_text)
        
        if not data:
            print("No event found in file.")
            return

        # Handle list vs single object
        events = data if isinstance(data, list) else [data]

        for event in events:
            if event.get('confidence') == 'Low':
                print(f"Skipping low confidence event: {event.get('summary')}")
                continue

            # Resolve Calendar ID
            cal_name = event.get('calendar', DEFAULT_CALENDAR).lower()
            
            # Fuzzy fallback
            target_cal_id = CALENDARS.get(cal_name)
            if not target_cal_id:
                for key in CALENDARS:
                    if cal_name in key or key in cal_name:
                        target_cal_id = CALENDARS[key]
                        cal_name = key
                        break
            
            # Create if missing
            if not target_cal_id:
                print(f"Calendar '{cal_name}' not found. Creating it...")
                try:
                    create_cmd = ["uv", "run", "calendar_client.py", "--create-calendar", event.get('calendar')]
                    subprocess.run(create_cmd, check=True, capture_output=True)
                    
                    service = calendar_client.get_service()
                    CALENDARS.update(calendar_client.get_calendar_map(service))
                    target_cal_id = CALENDARS.get(cal_name.lower())
                    print(f"Created and loaded new calendar: {target_cal_id}")
                except Exception as e:
                    print(f"Failed to create calendar: {e}")
                    target_cal_id = CALENDARS[DEFAULT_CALENDAR]

            print(f"Creating Event: {event['summary']} -> {cal_name} ({target_cal_id[:10]}...)")
            
            # Ensure all args are strings, handling potential None values
            cmd = [
                "uv", "run", "calendar_client.py",
                "--summary", str(event.get('summary', 'New Event')),
                "--start", str(event.get('start', '')),
                "--end", str(event.get('end', '')),
                "--description", str(event.get('description', '')),
                "--calendar-id", str(target_cal_id)
            ]
            
            if event.get("recurrence"):
                print(f"  > Recurring: {event['recurrence']}")
                cmd.extend(["--recurrence", str(event['recurrence'])])
            
            subprocess.run(cmd, check=True)

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

def main():
    print(f"Orchestrator started (SDK: google-genai). Watching {INPUT_DIR.absolute()}...")
    
    # Ensure dirs exist
    INPUT_DIR.mkdir(exist_ok=True)
    PROCESSED_DIR.mkdir(exist_ok=True)

    while True:
        # List files in input directory
        files = [f for f in INPUT_DIR.iterdir() if f.is_file() and f.name != ".DS_Store"]
        
        for file_path in files:
            process_file(file_path)
            
            # Move to processed
            destination = PROCESSED_DIR / file_path.name
            shutil.move(str(file_path), str(destination))
            print(f"Moved {file_path.name} to processed.")
        
        time.sleep(5)  # Sleep for 5 seconds

if __name__ == "__main__":
    main()
