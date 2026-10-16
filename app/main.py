from dotenv import load_dotenv
from openai import APIError, OpenAIError

from app.travel_advisor import TravelAdvisor


def main() -> None:
    load_dotenv()

    try:
        advisor = TravelAdvisor()
    except ValueError as error:
        print(f"Configuration error: {error}")
        return

    print("\nAI Travel Advisor")
    print("=================")
    print("Plan your next trip!")
    print("Type 'exit' or 'quit' to end the conversation.\n")

    previous_response_id: str | None = None

    try:
        while True:
            user_message = input("You: ").strip()

            if user_message.lower() in {"exit", "quit"}:
                print("Assistant: Happy travels! Goodbye.")
                break

            if not user_message:
                continue

            try:
                reply = advisor.get_response(
                    user_message,
                    previous_response_id,
                )
                previous_response_id = reply.response_id
                if reply.status == "needs_info":
                    print(f"\nAssistant: {reply.message}\n")
                    for source in reply.sources or []:
                        print(f"Source: {source.title} ({source.url})")
                    continue

                plan = reply.plan
                if plan is None:
                    raise RuntimeError("The advisor returned no travel plan.")
                answer_parts = [
                    plan.title,
                    plan.summary,
                    "Itinerary",
                    plan.itinerary,
                    "Practical tips",
                    plan.practical_tips,
                    "Estimated budget",
                    plan.budget,
                ]
                if plan.sources:
                    answer_parts.extend(
                        ["Sources", *(source.url for source in plan.sources)]
                    )
                answer = "\n".join(answer_parts)
                print(f"\nAssistant:\n{answer}\n")
            except APIError as error:
                print(f"\nOpenAI API error: {error}\n")
            except OpenAIError as error:
                print(f"\nOpenAI client error: {error}\n")

    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")


if __name__ == "__main__":
    main()