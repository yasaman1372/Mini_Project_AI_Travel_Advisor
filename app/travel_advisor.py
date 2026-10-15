from openai import OpenAI
import json
import os
import re
from datetime import date, timedelta

import requests
from pydantic import BaseModel, Field

MODEL = "gpt-6-luna"
client = OpenAI()

SYSTEM_PROMPT = """
You are a friendly, practical AI travel advisor.
Help the user plan a personalized, realistic trip through conversation.
Before generating an itinerary, make sure you know all three essentials:
(1) destination,
(2) trip duration (number of days or dates), and
(3) at least one travel interest (for example food, museums, hiking, beaches,
nightlife, or shopping).

Ask one concise, natural follow-up covering only the missing essentials. Do not
ask for optional preferences if the user has not volunteered them; use sensible
assumptions instead.

If the destination, dates, duration, or other details conflict or are materially
ambiguous, ask the user to clarify before planning. Do not silently choose between
contradictory details. Treat an explicit "surprise me" destination as permission
to suggest a destination and proceed, while briefly stating your choice.

Once the essentials are clear and there is no unresolved contradiction, provide
the complete plan without asking for confirmation. Include a memorable trip title,
a short summary, a day-by-day itinerary with a sensible pace, practical travel
tips, and an estimated per-person budget with currency and a clear breakdown.
State assumptions, especially when dates, departure city, or budget are unknown.

Use the weather and exchange-rate function tools when current weather or currency
conversion is relevant to the user's request or itinerary. Weather forecasts are
only meaningful within the available forecast period; beyond that, describe
seasonal expectations instead. Label retrieved data with its date, and treat
exchange rates as approximate mid-market rates, not guaranteed card or bank rates.
Use web search for current public-transport options, operator information, or
service changes. Prefer official sources. Do not claim live availability or
opening hours. Include clickable source URLs for retrieved facts and recommend
checking details before booking.

Respect any accessibility, dietary, safety, or budget constraints the user mentions.
Be transparent when a specific recommendation or cost is uncertain.
"""


PRICING_USD_PER_MILLION = {
    "gpt-6-luna": {"input": 0.10, "cached_input": 0.01, "output": 0.50}
}
history = [{"role": "system", "content": SYSTEM_PROMPT}]

conversation_usage = {
    "input_tokens": 0,
    "cached_input_tokens": 0,
    "output_tokens": 0,
    "estimated_cost_usd": 0.0,
}

class Structure(BaseModel):
    title: str = Field(description="A title for the trip")
    summary: str = Field(description="Trip summary")
    itinerary: str = Field(description="Day-by-day itinerary")
    practical_tips: str = Field(description="Practical travel tips")
    budget: str = Field(description="Estimated budget")


TOOLS = [
    {
        "type": "function",
        "name": "get_weather_forecast",
        "description": "Get a daily weather forecast for a location and dates within the next 16 days.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City and country"},
                "start_date": {"type": "string", "description": "First forecast date in YYYY-MM-DD format"},
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
        "description": "Get a recent exchange rate and convert an amount between two currencies.",
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


def get_weather_forecast(location, start_date, days):
    forecast_start = date.fromisoformat(start_date)
    forecast_end = forecast_start + timedelta(days=days - 1)
    today = date.today()
    if days < 1 or days > 16:
        return {"error": "Choose between 1 and 16 forecast days."}
    if forecast_start < today or forecast_end > today + timedelta(days=15):
        return {"error": "A forecast is only available for dates within the next 16 days. Use seasonal expectations for later trips."}

    geocoding_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=20,
    )
    geocoding_response.raise_for_status()
    locations = geocoding_response.json().get("results", [])
    if not locations:
        return {"error": f"Could not find a location matching {location!r}."}

    place = locations[0]
    forecast_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "start_date": forecast_start.isoformat(),
            "end_date": forecast_end.isoformat(),
        },
        timeout=20,
    )
    forecast_response.raise_for_status()
    forecast_data = forecast_response.json()
    return {
        "location": f"{place['name']}, {place.get('country', '')}",
        "timezone": forecast_data.get("timezone"),
        "daily_forecast": forecast_data.get("daily", {}),
        "retrieved_on": today.isoformat(),
        "sources": [
            {"title": "Open-Meteo geocoding", "url": geocoding_response.url},
            {"title": "Open-Meteo forecast", "url": forecast_response.url},
        ],
    }


def get_exchange_rate(base_currency, quote_currency, amount):
    base_currency = base_currency.upper()
    quote_currency = quote_currency.upper()
    if (
        not re.fullmatch(r"[A-Z]{3}", base_currency)
        or not re.fullmatch(r"[A-Z]{3}", quote_currency)
    ):
        return {"error": "Currency codes must each contain exactly three letters."}

    rate_response = requests.get(
        f"https://api.frankfurter.dev/v2/rate/{base_currency}/{quote_currency}",
        timeout=20,
    )
    rate_response.raise_for_status()
    rate_data = rate_response.json()
    return {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "rate": rate_data["rate"],
        "rate_date": rate_data["date"],
        "amount": amount,
        "converted_amount": round(amount * rate_data["rate"], 2),
        "sources": [{"title": "Frankfurter exchange rates", "url": rate_response.url}],
    }


def execute_function_tool(name, arguments):
    try:
        if name == "get_weather_forecast":
            return get_weather_forecast(**arguments)
        if name == "get_exchange_rate":
            return get_exchange_rate(**arguments)
        return {"error": f"Unknown function tool: {name}"}
    except (requests.RequestException, KeyError, ValueError) as error:
        return {"error": f"Tool {name} could not retrieve data: {error}"}


def extract_web_sources(response):
    sources = []
    seen_urls = set()
    for output_item in response.output:
        if getattr(output_item, "type", None) != "message":
            continue
        for content in getattr(output_item, "content", []):
            for annotation in getattr(content, "annotations", []) or []:
                if getattr(annotation, "type", None) == "url_citation":
                    url = getattr(annotation, "url", None)
                    if url and url not in seen_urls:
                        sources.append((getattr(annotation, "title", None) or url, url))
                        seen_urls.add(url)
    return sources


def format_as_markdown(trip: Structure, sources=()):
    markdown = f"""# {trip.title}

## Summary
{trip.summary}

## Day-by-day itinerary
{trip.itinerary}

## Practical tips
{trip.practical_tips}

## Estimated budget
{trip.budget}"""
    if sources:
        source_links = "\n".join(f"- [{title}]({url})" for title, url in sources)
        markdown += f"\n\n## Sources\n{source_links}"
    return markdown


def send_request(input):
    return client.responses.parse(
        model=MODEL,
        input=input,
        text_format=Structure,
        tools=TOOLS,
    )


def chat(user_text):
    input_items = list(history)
    input_items.append({"role": "user", "content": user_text})
    tool_sources = []
    total_input_tokens = 0
    total_cached_input_tokens = 0
    total_output_tokens = 0

    for tool_round in range(6):
        response = send_request(input_items)
        usage = response.usage
        total_input_tokens += usage.input_tokens
        total_cached_input_tokens += getattr(
            getattr(usage, "input_tokens_details", None), "cached_tokens", 0
        ) or 0
        total_output_tokens += usage.output_tokens

        function_calls = [
            item for item in response.output
            if getattr(item, "type", None) == "function_call"
        ]
        if not function_calls:
            break
        if tool_round == 5:
            raise RuntimeError("Tool calling exceeded the maximum of six rounds.")

        input_items.extend(response.output)
        for function_call in function_calls:
            function_arguments = json.loads(function_call.arguments)
            tool_result = execute_function_tool(function_call.name, function_arguments)
            for source in tool_result.get("sources", []):
                tool_sources.append((source["title"], source["url"]))
            input_items.append({
                "type": "function_call_output",
                "call_id": function_call.call_id,
                "output": json.dumps(tool_result),
            })

    answer = response.output_text
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": answer})

    conversation_usage["input_tokens"] += total_input_tokens
    conversation_usage["cached_input_tokens"] += total_cached_input_tokens
    conversation_usage["output_tokens"] += total_output_tokens

    rates = PRICING_USD_PER_MILLION[MODEL]
    uncached_input_tokens = total_input_tokens - total_cached_input_tokens
    conversation_usage["estimated_cost_usd"] += (
        uncached_input_tokens * rates["input"]
        + total_cached_input_tokens * rates["cached_input"]
        + total_output_tokens * rates["output"]
    ) / 1_000_000

    print(
        f"Conversation totals: {conversation_usage['input_tokens']:,} input tokens, "
        f"{conversation_usage['output_tokens']:,} output tokens; "
        f"estimated model cost ${conversation_usage['estimated_cost_usd']:.6f} USD"
    )
    sources = tool_sources + extract_web_sources(response)
    return response
    #return format_as_markdown(response.output_parsed, sources)



class TravelAdvisor:
    """Handles conversations with the AI Travel Advisor."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is missing. "
                "Add it to your .env file."
            )

        self.client = OpenAI(api_key=api_key)

    def get_response(self, user_message: str) -> tuple[str, str]:
        """Send a message and return its text and response ID."""

        response = chat(user_message)
     
        return response.output_text