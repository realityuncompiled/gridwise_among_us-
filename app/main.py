from fastapi import FastAPI

app = FastAPI(
    title="GridWise Energy Optimization API"
)


@app.get("/health")
def health():
    return {
        "status": "ok"
    }