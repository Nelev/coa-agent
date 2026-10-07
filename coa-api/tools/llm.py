"""The OpenRouter client. Built on first use, so importing never needs a key."""

from langchain_openai import ChatOpenAI

from settings import OPENROUTER_BASE_URL, get_settings


def chat_model(model: str | None = None) -> ChatOpenAI:
    """A chat model on OpenRouter's OpenAI-compatible API, at temperature 0.

    Two retries with the SDK's exponential backoff cover transient provider
    errors; after that the error surfaces to the caller.
    """
    settings = get_settings()
    key = settings.openrouter_api_key
    return ChatOpenAI(
        model=model or settings.openrouter_model,
        base_url=OPENROUTER_BASE_URL,
        api_key=key.get_secret_value() if key else None,
        temperature=0,
        max_retries=2,
    )
