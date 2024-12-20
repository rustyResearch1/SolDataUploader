from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any
import json
from datetime import datetime
from pathlib import Path
import logging
import secrets
import os
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create data directory if it doesn't exist
Path("data").mkdir(exist_ok=True)

app = FastAPI(title="Simple Data Receiver")

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
        filename = f"data/upload_{timestamp}.json"
        
        # Write data to file
        with open(filename, 'w') as f:
            json.dump(upload.data, f, indent=4)
        
        logger.info(f"Data written to {filename}")
        
        return {
            "status": "success",
            "filename": filename,
            "message": "Data saved successfully"
        }
        
    except Exception as e:
        error_msg = f"Error saving data: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


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

@app.get("/feed", response_class=HTMLResponse)
async def get_feed():
    """Return recent entries as HTML"""
    try:
        # Get last 50 entries
        entries = []
        data_files = sorted(Path("data").glob("upload_*.json"), reverse=True)[:50]
        
        for file in data_files:
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                    entries.append(data)
            except Exception as e:
                logger.error(f"Error reading file {file}: {e}")
        
        # Generate HTML
        html_content = """
        <div class="feed-container">
        """
        
        for entry in entries:
            parsed = parse_data(entry)
            content_type = parsed.get("parsed", {}).get("type", "unknown")
            
            if content_type == "tool_call":
                html_content += f"""
                <div class="entry tool-call">
                    <div class="timestamp">{parsed['timestamp']}</div>
                    <div class="function">Function: {parsed['parsed']['function_name']}</div>
                    <div class="arguments">Arguments: {json.dumps(parsed['parsed']['arguments'], indent=2)}</div>
                </div>
                """
            elif content_type == "text_content":
                html_content += f"""
                <div class="entry text-content">
                    <div class="timestamp">{parsed['timestamp']}</div>
                    <div class="text">{parsed['parsed']['text']}</div>
                </div>
                """
        
        html_content += "</div>"
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error generating feed: {e}")
        return HTMLResponse(content=f"<div>Error loading feed: {str(e)}</div>")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)