# Day 11 Task 2: Gemini With OpenAI SDK And Prompt Layer

This task shows how to create a reusable prompt layer and send the generated messages to Gemini using the OpenAI Python SDK through Gemini's OpenAI-compatible endpoint.

## Files

```text
Ey_training_genai/day11/task2/main.py
```

## Setup

Install the OpenAI SDK if it is not already installed:

```bash
.venv/bin/pip install openai
```

Then open `main.py` and replace:

```python
GEMINI_API_KEY = "PASTE_YOUR_GEMINI_API_KEY_HERE"
```

with your Gemini API key.

## Run

From the repository root:

```bash
.venv/bin/python Ey_training_genai/day11/task2/main.py
```

## What The Code Does

1. Imports the OpenAI SDK.
2. Defines a `PromptLayer` class.
3. Stores the system prompt and user prompt template in the prompt layer.
4. Creates final chat messages by filling template variables.
5. Creates an `OpenAI` client.
6. Points the client to Gemini's OpenAI-compatible base URL:

```text
https://generativelanguage.googleapis.com/v1beta/openai/
```

7. Sends the prompt-layer messages to:

```text
gemini-3.5-flash
```

8. Prints the prompt-layer messages and Gemini response.

## Prompt Layer

The prompt layer is responsible for prompt creation only:

```python
prompt_layer = create_prompt_layer()
messages = prompt_layer.create_messages(
    topic="time-series dataset",
    audience="Python beginner",
    points="5",
)
```

The Gemini API function receives already-created messages:

```python
answer = ask_gemini(messages)
```

This keeps prompt design separate from API calling logic.

## Note

The API key is shown as a placeholder in the file. Avoid committing a real API key to GitHub or sharing it in screenshots.
