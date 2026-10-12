
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "ChronosMatch API is running successfully!"}