from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import ingestion, auth

app = FastAPI(title="RetailPulse Portal Core Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ingestion.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)