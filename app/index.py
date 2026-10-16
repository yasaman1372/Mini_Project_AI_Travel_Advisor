from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.travel_advisor import AdvisorReply, TravelAdvisor


load_dotenv()

app = FastAPI(
    title="AI Travel Advisor API",
    description="Create personalized travel plans with an AI advisor.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

advisor = TravelAdvisor()


class ChatRequest(BaseModel):
    """A message sent to the travel advisor."""

    message: str = Field(min_length=1)
    previous_response_id: str | None = None


@app.get("/", include_in_schema=False)
def home() -> dict[str, str]:
    """Point API visitors to the service documentation and health check."""

    return {
        "service": "AI Travel Advisor API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the HTTP service is running."""

    return {"status": "ok"}


@app.post(
    "/chat",
    response_model=AdvisorReply,
    response_model_exclude_none=True,
)
def chat(request: ChatRequest) -> AdvisorReply:
    """Send one message in a client-managed conversation."""

    message = request.message.strip()
    if not message:
        raise HTTPException(
            status_code=422,
            detail="Message must not be blank.",
        )


    try:
        return advisor.get_response(
            message,
            request.previous_response_id,
        )
    except OpenAIError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider could not process the request.",
        ) from error
