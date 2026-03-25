"""
Intent Classification — uses LLM to map free-text user input to menu options.
"""
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from src.config import GOOGLE_API_KEY, GEMINI_MODEL


def get_llm():
    """Get the LLM instance."""
    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=GOOGLE_API_KEY,
        temperature=0,
    )


INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an intent classifier for an e-commerce customer support chatbot.
Given the user's message, classify it into EXACTLY ONE of the following valid options:
{valid_options}

Respond with ONLY the option label, nothing else. If the user's message doesn't clearly match any option, respond with "unclear".
"""),
    ("human", "{user_message}"),
])


async def classify_intent(user_message: str, valid_options: list[str]) -> str:
    """
    Classify user free-text into one of the valid menu options.
    Returns the matched option string, or 'unclear' if no match.
    """
    llm = get_llm()
    chain = INTENT_PROMPT | llm
    options_str = "\n".join(f"- {opt}" for opt in valid_options)
    result = await chain.ainvoke({
        "user_message": user_message,
        "valid_options": options_str,
    })
    response = result.content.strip().lower()

    # Match against valid options (case-insensitive)
    for opt in valid_options:
        if opt.lower() == response or opt.lower() in response:
            return opt

    return "unclear"
