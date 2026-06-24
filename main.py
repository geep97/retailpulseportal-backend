from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import ingestion, auth, dashboard

app = FastAPI(title="RetailPulse Portal Core Engine")


origins = [
    "http://localhost:5173",
    "https://retailpulseportal-frontend-r34v7k773-geep97s-projects.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ingestion.router)
app.include_router(dashboard.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)