from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "alive"}

@app.get("/")
async def root():
    return {"message": "EnergyMind API"}
