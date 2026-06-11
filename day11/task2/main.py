from dataclasses import dataclass

from openai import OpenAI


GEMINI_API_KEY = ""
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODEL_NAME = "gemini-3.5-flash"


@dataclass
class PromptLayer:
    system_prompt: str
    user_template: str

    def create_messages(self, **variables: str) -> list[dict[str, str]]:
        user_prompt = self.user_template.format(**variables)
        return [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]


def create_prompt_layer() -> PromptLayer:
    return PromptLayer(
        system_prompt=(
            "You are a helpful AI tutor. Explain concepts in simple language, "
            "use examples, and keep the answer beginner friendly."
        ),
        user_template=(
            "Topic: {topic}\n"
            "Audience: {audience}\n"
            "Task: Explain the topic clearly in {points} short bullet points."
        ),
    )


def create_client() -> OpenAI:
    return OpenAI(
        api_key=GEMINI_API_KEY,
        base_url=GEMINI_BASE_URL,
    )


def ask_gemini(messages: list[dict[str, str]]) -> str:
    client = create_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
    )
    return response.choices[0].message.content or ""


def main() -> None:
    if GEMINI_API_KEY == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        raise ValueError("Replace GEMINI_API_KEY in main.py with your Gemini API key.")

    prompt_layer = create_prompt_layer()
    messages = prompt_layer.create_messages(
        topic="time-series dataset",
        audience="Python beginner",
        points="5",
    )
    answer = ask_gemini(messages)

    print("Messages Created By Prompt Layer:")
    for message in messages:
        print(f"{message['role'].upper()}: {message['content']}")
    print("\nGemini Response:")
    print(answer)


if __name__ == "__main__":
    main()
