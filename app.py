import os
import logging
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Clinic AI Chat")

N8N_WEBHOOK = os.getenv("N8N_WEBHOOK")
if not N8N_WEBHOOK:
    raise ValueError("N8N_WEBHOOK environment variable is not set.")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the chat page."""
    return FileResponse("index.html")


@app.post("/api/send")
async def send_message(payload: dict):
    """Proxy message to n8n workflow and return AI response."""
    message = payload.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    ai_text = None
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                N8N_WEBHOOK,
                json={"message": message},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()

            # Parse various n8n response formats
            if isinstance(data, dict) and "response" in data:
                ai_text = data["response"]
            elif isinstance(data, dict) and "output" in data:
                ai_text = data["output"]
            elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                ai_text = data[0].get("output") or data[0].get("response") or data[0].get("text")
            elif isinstance(data, str):
                ai_text = data
            elif isinstance(data, dict) and "json" in data:
                inner = data["json"]
                if isinstance(inner, dict):
                    ai_text = inner.get("output") or inner.get("response") or inner.get("text")
                elif isinstance(inner, str):
                    ai_text = inner

            if ai_text is None:
                logging.warning(f"Unexpected n8n response: {data}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not extract AI response. Raw: {str(data)[:200]}"
                )

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"n8n error: {e.response.text[:300]}"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to n8n: {str(e)}"
        )

    return {"response": str(ai_text)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)