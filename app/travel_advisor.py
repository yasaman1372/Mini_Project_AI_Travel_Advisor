import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Literal

import requests
from openai import OpenAI
from pydantic import BaseModel, Field


MODEL = "gpt-6-luna"
HTTP_TIMEOUT = (3, 5)
MAX_TOOL_ROUNDS = 4
INLINE_CITATION_RE = re.compile(r"\(?\[([^\]]+)\]\((https?://[^)\s]+)\)\)?")

SYSTEM_PROMPT = """You are a friendly, practical AI travel advisor.
Help the user plan a personalized, realistic trip through conversation.
Before generating an itinerary, make sure you know all three essentials:
(1) destination,
(2) trip duration (number of days or dates), and
(3) at least one travel interest (for example food, museums, hiking, beaches,
nightlife, or shopping).

Ask one concise, natural follow-up covering only the missing essentials. Do not
ask for optional preferences if the user has not volunteered them; use sensible
assumptions instead.
When any essential information is missing or contradictory, fill only
follow_up and leave title, summary, itinerary, practical_tips, and budget empty.

If the destination, dates, duration, or other details conflict or are materially
ambiguous, ask the user to clarify before planning. Do not silently choose between
contradictory details. Treat an explicit "surprise me" destination as permission
to suggest a destination and proceed, while briefly stating your choice.

Once the essentials are clear and there is no unresolved contradiction, provide
the complete plan without asking for confirmation. Include a memorable trip title,
a short summary, a day-by-day itinerary with a sensible pace, practical travel
tips, and an estimated per-person budget with currency and a clear breakdown.
State assumptions, especially when dates, departure city, or budget are unknown.
When the plan is ready, leave follow_up empty and fill every plan field. Use plain
text in each field, not Markdown headings or formatting.

Use the weather and exchange-rate function tools when current weather or currency
conversion is relevant to the user's request or itinerary. Weather forecasts are
only meaningful within the available forecast period; beyond that, describe
seasonal expectations instead. Label retrieved data with its date, and treat
exchange rates as approximate mid-market rates, not guaranteed card or bank rates.
Use web search for current public-transport options, operator information, or
service changes. Prefer official sources. Do not claim live availability or
opening hours. Keep citations and URLs out of plan fields; sources are returned
separately. Recommend checking details before booking.

Respect any accessibility, dietary, safety, or budget constraints the user mentions.
Be transparent when a specific recommendation or cost is uncertain.
"""


class Structure(BaseModel):
    follow_up: str = Field(description="One concise question if trip details are missing; otherwise empty")
    title: str = Field(description="A memorable trip title, or empty if not ready")
    summary: str = Field(description="A short trip summary, or empty if not ready")
    itinerary: str = Field(description="Day-by-day itinerary, or empty if not ready")
    practical_tips: str = Field(description="Practical travel tips, or empty if not ready")
    budget: str = Field(description="Estimated budget, or empty if not ready")


class Source(BaseModel):
    title: str
    url: str


class TravelPlan(BaseModel):
    title: str
    summary: str
    itinerary: str
    practical_tips: str
    budget: str
    sources: list[Source]


class AdvisorReply(BaseModel):
    status: Literal["needs_info", "complete"]
    response_id: str
    message: str | None = None
    plan: TravelPlan | None = None


TOOLS = [
    {
        "type": "function",
        "name": "get_weather_forecast",
        "description": "Get a daily weather forecast for a location and dates within the next 16 days.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City and country"},
                "start_date": {"type": "string", "description": "First date in YYYY-MM-DD format"},
                "days": {"type": "integer", "minimum": 1, "maximum": 16},
            },
            "required": ["location", "start_date", "days"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_exchange_rate",
        "description": "Get a recent exchange rate and convert an amount.",
        "parameters": {
            "type": "object",
            "properties": {
                "base_currency": {"type": "string", "description": "Three-letter currency code"},
                "quote_currency": {"type": "string", "description": "Three-letter currency code"},
                "amount": {"type": "number", "description": "Amount in the base currency"},
            },
            "required": ["base_currency", "quote_currency", "amount"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {"type": "web_search"},
]


def get_weather_forecast(location: str, start_date: str, days: int) -> dict:
    today = date.today()
    if not 1 <= days <= 16:
        return {"error": "Choose between 1 and 16 forecast days."}

    forecast_start = date.fromisoformat(start_date)
    forecast_end = forecast_start + timedelta(days=days - 1)
    if forecast_start < today or forecast_end > today + timedelta(days=15):
        return {
            "error": "Forecasts are only available within the next 16 days. "
            "Use seasonal expectations for later trips."
        }

    geocoding = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=HTTP_TIMEOUT,
    )
    geocoding.raise_for_status()
    locations = geocoding.json().get("results", [])
    if not locations:
        return {"error": f"Could not find a location matching {location!r}."}

    place = locations[0]
    forecast = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max"
            ),
            "timezone": "auto",
            "start_date": forecast_start.isoformat(),
            "end_date": forecast_end.isoformat(),
        },
        timeout=HTTP_TIMEOUT,
    )
    forecast.raise_for_status()

    return {
        "location": f"{place['name']}, {place.get('country', '')}",
        "daily_forecast": forecast.json().get("daily", {}),
        "retrieved_on": today.isoformat(),
        "sources": [
            {"title": "Open-Meteo geocoding", "url": geocoding.url},
            {"title": "Open-Meteo forecast", "url": forecast.url},
        ],
    }


def get_exchange_rate(
    base_currency: str, quote_currency: str, amount: float
) -> dict:
    base_currency = base_currency.upper()
    quote_currency = quote_currency.upper()
    if not re.fullmatch(r"[A-Z]{3}", base_currency) or not re.fullmatch(
        r"[A-Z]{3}", quote_currency
    ):
        return {"error": "Currency codes must each contain exactly three letters."}

    response = requests.get(
        f"https://api.frankfurter.dev/v2/rate/{base_currency}/{quote_currency}",
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()
    rate_data = response.json()

    return {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "rate": rate_data["rate"],
        "rate_date": rate_data["date"],
        "amount": amount,
        "converted_amount": round(amount * rate_data["rate"], 2),
        "sources": [{"title": "Frankfurter exchange rates", "url": response.url}],
    }


def execute_function_tool(name: str, arguments: dict) -> dict:
    try:
        if name == "get_weather_forecast":
            return get_weather_forecast(**arguments)
        if name == "get_exchange_rate":
            return get_exchange_rate(**arguments)
        return {"error": f"Unknown function tool: {name}"}
    except (requests.RequestException, KeyError, ValueError) as error:
        return {"error": f"Could not retrieve tool data: {error}"}


def extract_web_sources(response) -> list[tuple[str, str]]:
    sources = []
    seen_urls = set()

    for item in response.output:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []):
            for annotation in getattr(content, "annotations", []) or []:
                url = getattr(annotation, "url", None)
                if (
                    getattr(annotation, "type", None) == "url_citation"
                    and url
                    and url not in seen_urls
                ):
                    sources.append((getattr(annotation, "title", None) or url, url))
                    seen_urls.add(url)

    return sources


def remove_inline_citations(
    text: str, sources: list[tuple[str, str]]
) -> str:
    seen_urls = {url for _, url in sources}

    def add_source(match: re.Match[str]) -> str:
        title, url = match.groups()
        if url not in seen_urls:
            sources.append((title, url))
            seen_urls.add(url)
        return ""

    cleaned_text = INLINE_CITATION_RE.sub(add_source, text)
    cleaned_text = re.sub(r"[ \t]{2,}", " ", cleaned_text)
    return cleaned_text.strip()


class TravelAdvisor:
    """Creates travel advice while keeping conversation state in response IDs."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing.")

        # Avoid long automatic retries; callers can retry failed requests.
        self.client = OpenAI(
            api_key=api_key,
            timeout=60.0,
            max_retries=0,
        )

    def _request(self, input_data, previous_response_id: str | None = None):
        request = {
            "model": MODEL,
            "instructions": SYSTEM_PROMPT,
            "input": input_data,
            "text_format": Structure,
            "tools": TOOLS,
        }
        if previous_response_id:
            request["previous_response_id"] = previous_response_id
        return self.client.responses.parse(**request)

    def get_response(
        self,
        user_message: str,
        previous_response_id: str | None = None,
    ) -> AdvisorReply:
        """Return a follow-up or structured travel plan with its response ID."""
        response = self._request(user_message, previous_response_id)
        sources = []

        for tool_round in range(MAX_TOOL_ROUNDS):
            function_calls = [
                item
                for item in response.output
                if getattr(item, "type", None) == "function_call"
            ]
            if not function_calls:
                break
            if tool_round == MAX_TOOL_ROUNDS - 1:
                raise RuntimeError("Maximum tool-call rounds reached.")

            def run_tool(call):
                arguments = json.loads(call.arguments)
                result = execute_function_tool(call.name, arguments)
                call_output = {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
                call_sources = [
                    (source["title"], source["url"])
                    for source in result.get("sources", [])
                ]
                return call_output, call_sources

            # Weather and exchange-rate requests do not depend on each other.
            with ThreadPoolExecutor(
                max_workers=min(3, len(function_calls))
            ) as executor:
                results = list(executor.map(run_tool, function_calls))

            tool_outputs = [output for output, _ in results]
            for _, tool_sources in results:
                sources.extend(tool_sources)

            response = self._request(tool_outputs, response.id)

        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("The model returned no structured response.")

        sources.extend(extract_web_sources(response))
        plan_values = {
            "title": parsed.title,
            "summary": parsed.summary,
            "itinerary": parsed.itinerary,
            "practical_tips": parsed.practical_tips,
            "budget": parsed.budget,
        }
        plan_values = {
            key: remove_inline_citations(value, sources)
            for key, value in plan_values.items()
        }
        plan_sections = (
            plan_values["title"],
            plan_values["summary"],
            plan_values["itinerary"],
            plan_values["practical_tips"],
            plan_values["budget"],
        )
        if parsed.follow_up.strip() or not all(
            section.strip() for section in plan_sections
        ):
            return AdvisorReply(
                status="needs_info",
                message=parsed.follow_up.strip() or "What trip details would you like to add?",
                response_id=response.id,
            )

        plan = TravelPlan(
            title=plan_values["title"],
            summary=plan_values["summary"],
            itinerary=plan_values["itinerary"],
            practical_tips=plan_values["practical_tips"],
            budget=plan_values["budget"],
            sources=[Source(title=title, url=url) for title, url in sources],
        )
        return AdvisorReply(
            status="complete",
            plan=plan,
            response_id=response.id,
        )