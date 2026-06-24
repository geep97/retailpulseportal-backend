from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import ingestion, auth, dashboard

app = FastAPI(title="RetailPulse Portal Core Engine")

# Exact origins allowed
origins = [
    "http://localhost:5173",
    "https://retailpulseportal-frontend.vercel.app",
    "https://retailpulseportal-frontend-r34v7k773-geep97s-projects.vercel.app",
    "https://retailpulseportal-frontend-s4hup561v-geep97s-projects.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # This regex allows ANY preview deployment URL from your geep97s-projects Vercel account
    allow_origin_regex=r"https://retailpulseportal-frontend-.*-geep97s-projects\.vercel\.app",
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