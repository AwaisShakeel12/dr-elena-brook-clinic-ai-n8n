import os
import logging
import httpx

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from dotenv import load_dotenv


# Load environment variables from .env
load_dotenv()


app = FastAPI(title="Clinic AI Chat")


# n8n production webhook
N8N_WEBHOOK = os.getenv("N8N_WEBHOOK")

if not N8N_WEBHOOK:
    raise ValueError("N8N_WEBHOOK environment variable is not set.")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the chat page."""
    return FileResponse("index.html")


@app.post("/api/send")
async def send_message(payload: dict):
    """Send user message + session ID to n8n and return AI response."""

    # Get message from frontend
    message = payload.get("message", "").strip()

    # Get conversation session ID from frontend
    session_id = payload.get("sessionId", "").strip()

    # Validate message
    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )

    # Validate session ID
    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="Session ID is required"
        )

    logging.info(
        f"Sending message to n8n. Session: {session_id}"
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:

            response = await client.post(
                N8N_WEBHOOK,

                # IMPORTANT:
                # Send BOTH message and sessionId to n8n
                json={
                    "message": message,
                    "sessionId": session_id
                },

                headers={
                    "Content-Type": "application/json"
                }
            )

            response.raise_for_status()

            data = response.json()

            logging.info(f"n8n response: {data}")

            # -----------------------------------------
            # Parse n8n response
            # -----------------------------------------

            # Example:
            # {"output": "Hello! How can I help?"}
            if isinstance(data, dict) and "response" in data:
                ai_text = data["response"]

            elif isinstance(data, dict) and "output" in data:
                ai_text = data["output"]

            # Example:
            # [{"output": "Hello!"}]
            elif (
                isinstance(data, list)
                and len(data) > 0
                and isinstance(data[0], dict)
            ):
                ai_text = (
                    data[0].get("output")
                    or data[0].get("response")
                    or data[0].get("text")
                )

            # If n8n returns a plain string
            elif isinstance(data, str):
                ai_text = data

            # Example:
            # {"json": {"output": "Hello!"}}
            elif isinstance(data, dict) and "json" in data:

                inner = data["json"]

                if isinstance(inner, dict):
                    ai_text = (
                        inner.get("output")
                        or inner.get("response")
                        or inner.get("text")
                    )

                elif isinstance(inner, str):
                    ai_text = inner

                else:
                    ai_text = None

            else:
                ai_text = None

            # -----------------------------------------
            # Make sure we actually got AI response
            # -----------------------------------------

            if ai_text is None:

                logging.warning(
                    f"Unexpected n8n response: {data}"
                )

                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Could not extract AI response. "
                        f"Raw: {str(data)[:200]}"
                    )
                )

    # n8n returned an HTTP error
    except httpx.HTTPStatusError as e:

        logging.error(
            f"n8n HTTP error {e.response.status_code}: "
            f"{e.response.text[:300]}"
        )

        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"n8n error: {e.response.text[:300]}"
        )

    # Could not connect to n8n
    except httpx.RequestError as e:

        logging.error(
            f"Failed to connect to n8n: {str(e)}"
        )

        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to n8n: {str(e)}"
        )

    # Return response to frontend
    return {
        "response": str(ai_text)
    }


# Run FastAPI directly
if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True
    )
