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
from datetime import datetime
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

def parse_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the different types of data we receive and extract meaningful content"""
    try:
        timestamp = data.get('timestamp', datetime.now().isoformat())
        content_data = data.get('data', {})
        
        # Check for status updates
        ###if 'status' in content_data:
            #return {
              #  "type": "status",
            #    "timestamp": timestamp,
            #    "content": content_data['status'].replace('_', ' ').strip(),
            #    "category": "system_status"
           # }
            
        # Check for messages - extract actual text content
        elif 'messages' in content_data:
            message = content_data['messages']
            # Extract text between value=" and the next quote or end
            value_match = re.search(r'value="([^"]*)', message)
            text = value_match.group(1) if value_match else message
            return {
                "type": "message",
                "timestamp": timestamp,
                "content": text.strip(),
                "category": "ai_response"
            }
            
        # Check for tool calls - extract call ID and function name
        elif 'tool_calls' in content_data:
            tool_call = content_data['tool_calls']
            # Extract call ID
            call_id = re.search(r"id='([^']*)'", tool_call)
            call_id = call_id.group(1) if call_id else None
            
            # Extract function name (if present)
            function_match = re.search(r"function='([^']*)'", tool_call)
            function_name = function_match.group(1) if function_match else None
            
            content = f"Tool Call: {call_id}"
            if function_name:
                content += f" (Function: {function_name})"
                
            return {
                "type": "tool_call",
                "timestamp": timestamp,
                "content": content,
                "call_id": call_id,
                "function": function_name,
                "category": "system_action"
            }
            
        # Handle unknown data types
        return {
            "type": "unknown",
            "timestamp": timestamp,
            "content": str(content_data),
            "category": "unknown"
        }
        
    except Exception as e:
        logger.error(f"Error parsing data: {e}")
        return {
            "type": "error",
            "timestamp": timestamp,
            "content": f"Error parsing data: {str(e)}",
            "category": "error"
        }

@app.get("/feed", response_class=HTMLResponse)
async def get_feed():
    """Return recent entries as HTML"""
    try:
        entries = list(collection.find().sort("timestamp", -1).limit(50))
        
        html_content = """
        <style>
            .feed-container {
                font-family: 'Courier New', monospace;
                padding: 20px;
                background: #0a0a0a;
                color: #33ff33;
            }
            .entry {
                margin-bottom: 15px;
                padding: 10px;
                border-left: 3px solid #33ff33;
                background: rgba(0, 255, 0, 0.05);
            }
            .timestamp {
                color: #666;
                font-size: 0.8em;
            }
            .content {
                margin-top: 5px;
            }
            .system_action {
                color: #00ffff;
                border-left-color: #00ffff;
            }
            .system_status {
                color: #ff9900;
                border-left-color: #ff9900;
            }
            .error {
                color: #ff3333;
                border-left-color: #ff3333;
            }
            .prefix {
                opacity: 0.7;
            }
        </style>
        <div class="feed-container">
        """
        
        for entry in entries:
            parsed = parse_data(entry)
            category_class = parsed.get('category', 'unknown')
            
            prefix = {
                'ai_response': '>> AI:',
                'system_action': '## SYS:',
                'system_status': '!! STATUS:',
                'error': '** ERROR:',
                'unknown': '?? LOG:'
            }.get(category_class, '-- LOG:')
            
            html_content += f"""
            <div class="entry {category_class} log-entry">
                <div class="timestamp">[{parsed['timestamp']}]</div>
                <div class="content">
                    <span class="prefix">{prefix}</span> {parsed['content']}
                </div>
            </div>
            """
        
        html_content += "</div>"
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        print(f"Error generating feed: {e}")
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)