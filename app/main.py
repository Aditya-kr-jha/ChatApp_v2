
import uvicorn
from fastapi import FastAPI, Depends, HTTPException, status



# Initialize FastAPI app
app = FastAPI(title="Chat Application",version="0.1.2")

@app.get("/")
async def root():
    return {"message": "Welcome to the Chat API"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)