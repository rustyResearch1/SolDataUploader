from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from typing import Dict, Any
import json
from datetime import datetime
from pathlib import Path
import logging
import secrets

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)