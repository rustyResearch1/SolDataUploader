from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import json
from datetime import datetime
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create data directory if it doesn't exist
Path("data").mkdir(exist_ok=True)

app = FastAPI(title="Simple Data Receiver")

class DataUpload(BaseModel):
    data: Dict[str, Any]

@app.post("/upload")
async def upload_data(upload: DataUpload):
    try:
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/upload_{timestamp}.json"
        
        print(upload.data)
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

@app.get("/")
async def root():
    return {"message": "Data receiver is running! Send POST requests to /upload"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)