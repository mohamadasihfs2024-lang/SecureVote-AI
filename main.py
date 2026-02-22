import face_recognition
import cv2
import numpy as np
import base64
import io
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt, JWTError
from datetime import datetime, timedelta
from pydantic import BaseModel
import database # Importing our separate database file

# --- CONFIGURATION ---
SECRET_KEY = "super-secret-key-change-in-production"
ALGORITHM = "HS256"

app = FastAPI(title="SecureVote AI Backend")

# --- CORS MIDDLEWARE (Fixes "Network Error") ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# --- STARTUP EVENT ---
@app.on_event("startup")
def startup_event():
    database.init_db() # Initialize DB on start

# --- SECURITY HELPERS ---
def create_jwt_token(user_id: int):
    expire = datetime.utcnow() + timedelta(hours=2)
    return jwt.encode({"sub": str(user_id)}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None: raise HTTPException(status_code=401, detail="Invalid Token")
        return int(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid Token")

# --- API ENDPOINTS ---

@app.post("/api/register")
async def register_user(
    aadhaar_id: str = Form(...), 
    name: str = Form(...), 
    file: UploadFile = File(...)
):
    try:
        # Read Image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        rgb_frame = frame[:, :, ::-1]
        
        # AI Processing
        encodings = face_recognition.face_encodings(rgb_frame)
        if not encodings:
            raise HTTPException(status_code=400, detail="No face detected. Please ensure good lighting.")
        
        face_encoding = encodings[0]
        
        # Database Check
        conn = database.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM voters WHERE aadhaar_id = ?", (aadhaar_id,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Aadhaar ID already registered")

        # Save to DB
        cursor.execute(
            "INSERT INTO voters (aadhaar_id, name, face_encoding) VALUES (?, ?, ?)",
            (aadhaar_id, name, face_encoding.tobytes())
        )
        conn.commit()
        conn.close()

        return {"status": "success", "message": f"Voter {name} registered successfully"}

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/login")
async def login_user(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image")

        rgb_frame = frame[:, :, ::-1]
        
        # AI Processing
        encodings = face_recognition.face_encodings(rgb_frame)
        if not encodings:
            raise HTTPException(status_code=400, detail="No face detected in frame")

        unknown_encoding = encodings[0]

        # Database Match
        conn = database.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, face_encoding FROM voters")
        voters = cursor.fetchall()
        conn.close()

        for voter_id, stored_enc_bytes in voters:
            stored_encoding = np.frombuffer(stored_enc_bytes, dtype=np.float64)
            
            # Match face
            matches = face_recognition.compare_faces([stored_encoding], unknown_encoding, tolerance=0.5)
            if matches[0]:
                token = create_jwt_token(voter_id)
                return {"status": "success", "token": token}

        raise HTTPException(status_code=401, detail="Face not recognized")

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Login Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

class VoteData(BaseModel):
    candidate: str

@app.post("/api/vote")
async def cast_vote(data: VoteData, user_id: int = Depends(get_current_user)):
    conn = database.get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT has_voted FROM voters WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row or row[0] == 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Already voted or invalid user")

    cursor.execute("INSERT INTO votes (voter_id, candidate) VALUES (?, ?)", (user_id, data.candidate))
    cursor.execute("UPDATE voters SET has_voted = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return {"status": "success"}

@app.get("/api/status")
async def get_status(user_id: int = Depends(get_current_user)):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, has_voted FROM voters WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"name": row[0], "has_voted": bool(row[1])}

# --- SERVE FRONTEND ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
