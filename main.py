from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
import json
from datetime import datetime
from pathlib import Path
import logging
import secrets
import os
import re
from pymongo import MongoClient

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")  # You'll get this from MongoDB Atlas
client = MongoClient(MONGO_URI)
db = client['your_database_name']
collection = db['data_logs']

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create data directory if it doesn't exist
Path("data").mkdir(exist_ok=True)

app = FastAPI(title="Simple Data Receiver")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)  
# Generate a random API key - you should save this somewhere secure
API_KEY_NAME = "X-API-Key"
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise Exception("API_KEY environment variable is not set!")

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key"
        )
    return api_key_header

class DataUpload(BaseModel):
    data: Dict[str, Any]

@app.post("/upload")
async def upload_data(upload: DataUpload, api_key: str = Depends(get_api_key)):
    try:
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # filename = f"data/upload_{timestamp}.json"
        
        document = {
            "timestamp": datetime.utcnow(),
            "data": upload.data,
            "raw_data": str(upload.data)  # Store raw string just in case
        }

        # Write data to file
        #with open(filename, 'w') as f:
            #json.dump(upload.data, f, indent=4)
        print("----RAW DATA RECEIVED----")
        print(json.dumps(upload.data, indent=2))

        result = collection.insert_one(document)
        
        print("\n----PARSED DATA----")
        print(json.dumps(parse_data(upload.data), indent=2))
        print("----------------------")

        logger.info(f"Data written and sent")
        
        return {
            "status": "success",
            "id": str(result.inserted_id),
            "message": "Data saved successfully"
        }
        
    except Exception as e:
        error_msg = f"Error saving data: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/feed", response_class=HTMLResponse)
async def get_feed():
    """Return recent entries as HTML"""
    try:
        # Get latest 50 entries from MongoDB
        entries = list(collection.find().sort("timestamp", -1).limit(50))
        
        # Generate HTML
        html_content = """
        <div class="feed-container">
        """
        
        for entry in entries:
            # Get the data from MongoDB document
            data = entry.get('data', {})
            parsed = parse_data({'data': data})  # Wrap in same structure as before
            content_type = parsed.get("parsed", {}).get("type", "unknown")
            
            if content_type == "tool_call":
                html_content += f"""
                <div class="entry tool-call">
                    <div class="timestamp">{entry['timestamp'].isoformat()}</div>
                    <div class="function">Function: {parsed['parsed']['function_name']}</div>
                    <div class="arguments">Arguments: {json.dumps(parsed['parsed']['arguments'], indent=2)}</div>
                </div>
                """
            elif content_type == "text_content":
                html_content += f"""
                <div class="entry text-content">
                    <div class="timestamp">{entry['timestamp'].isoformat()}</div>
                    <div class="text">{parsed['parsed']['text']}</div>
                </div>
                """
            else:
                # Fallback for unknown types - just show raw data
                html_content += f"""
                <div class="entry unknown">
                    <div class="timestamp">{entry['timestamp'].isoformat()}</div>
                    <div class="raw">{json.dumps(data, indent=2)}</div>
                </div>
                """
        
        html_content += "</div>"
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        print(f"Error generating feed: {e}")  # Print to Railway logs
        return HTMLResponse(content=f"<div>Error loading feed: {str(e)}</div>")


def parse_tool_call(data: str) -> Dict[str, Any]:
    """Parse tool call data"""
    try:
        # Extract function name and arguments using regex
        function_match = re.search(r"name='([^']*)'", data)
        arguments_match = re.search(r"arguments='([^']*)'", data)
        
        function_name = function_match.group(1) if function_match else "unknown"
        arguments = json.loads(arguments_match.group(1)) if arguments_match else {}
        
        return {
            "type": "tool_call",
            "function_name": function_name,
            "arguments": arguments,
            "raw": data
        }
    except Exception as e:
        logger.error(f"Error parsing tool call: {e}")
        return {"type": "tool_call", "error": str(e), "raw": data}

def parse_text_content(data: str) -> Dict[str, Any]:
    """Parse text content data"""
    try:
        # Extract the actual text value using regex
        text_match = re.search(r"value=\"([^\"]*)", data)
        text_content = text_match.group(1) if text_match else data
        
        return {
            "type": "text_content",
            "text": text_content,
            "raw": data
        }
    except Exception as e:
        logger.error(f"Error parsing text content: {e}")
        return {"type": "text_content", "error": str(e), "raw": data}

def parse_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Main parsing function"""
    parsed_data = {
        "timestamp": datetime.now().isoformat(),
        "original_data": data
    }
    
    # Check the content and parse accordingly
    content = str(data.get("data", ""))
    if "RequiredActionFunctionToolCall" in content:
        parsed_data["parsed"] = parse_tool_call(content)
    elif "TextContentBlock" in content:
        parsed_data["parsed"] = parse_text_content(content)
    else:
        parsed_data["parsed"] = {"type": "unknown", "raw": content}
    
    return parsed_data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)