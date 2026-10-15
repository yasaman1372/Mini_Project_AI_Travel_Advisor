from dotenv import load_dotenv
from openai import APIError, OpenAIError

from app.travel_advisor import TravelAdvisor


def main():
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


    try:
        while True:
            user_message = input("You: ").strip()

            if user_message.lower() in {"exit", "quit"}:
                print("Assistant: Happy travels! Goodbye.")
                break

            if not user_message:
                continue

            try:
                answer = advisor.get_response(user_message)
                
                print(f"\nAssistant: {answer}\n")

            except APIError as error:
                print(f"\nOpenAI API error: {error}\n")

            except OpenAIError as error:
                print(f"\nOpenAI client error: {error}\n")

    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")


if __name__ == "__main__":
    main()