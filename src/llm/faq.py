"""
FAQ Answer — simple LLM-based FAQ answering (no RAG for MVP).
Uses hardcoded FAQ context per category.
"""
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from src.config import GOOGLE_API_KEY, GEMINI_MODEL


FAQ_KNOWLEDGE = {
    "order_delivery_payment": """
- Orders are typically delivered within 5-7 business days.
- Express delivery is available in select cities (2-3 business days).
- We accept UPI, Credit/Debit Cards, Net Banking, and COD.
- COD orders have an additional fee of ₹50.
- You can track your order using the order tracking feature in your chat.
- If your order is delayed beyond the estimated delivery date, please contact support.
""",
    "cancellation": """
- Orders can be cancelled before they are shipped.
- Once shipped, cancellation will be processed as a return-to-origin (RTO).
- Cancellation requests are processed immediately for pre-dispatch orders.
- Refund for cancelled orders is processed within 5-7 business days.
- COD orders that are cancelled do not require any refund processing.
""",
    "refunds_returns": """
- Returns are accepted within 7 days of delivery.
- Products must be unused and in original packaging for returns.
- Refunds are processed within 7-10 business days after pickup.
- Refund will be credited to the original payment method.
- For COD orders, refund will be credited to your wallet or bank account.
- Exchange is available within 7 days for size/color changes.
""",
    "my_account": """
- You can update your profile, addresses, and preferences in your account.
- To delete your account, please contact our support team.
- Wallet balance can be used for future purchases.
- You can manage multiple delivery addresses.
""",
    "other": """
- For any issues not covered here, please connect with our support agent.
- Our support team is available Monday-Saturday, 9 AM - 6 PM.
- You can reach us via WhatsApp, web chat, or email.
""",
}


FAQ_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful customer support assistant for {store_name}, an e-commerce store.
Answer the customer's question based ONLY on the following knowledge base:

{faq_context}

If the question cannot be answered from the knowledge base, say "I'm unable to answer this question. Let me connect you with a support agent."
Keep your answer concise and friendly.
"""),
    ("human", "{question}"),
])


async def answer_faq(question: str, store_name: str, category: str | None = None) -> str:
    """
    Answer a FAQ question using LLM with hardcoded knowledge context.
    Returns the answer string.
    """
    # Build context from relevant categories
    if category and category in FAQ_KNOWLEDGE:
        context = FAQ_KNOWLEDGE[category]
    else:
        # Use all FAQ knowledge
        context = "\n".join(FAQ_KNOWLEDGE.values())

    llm = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=GOOGLE_API_KEY,
        temperature=0.3,
    )

    chain = FAQ_PROMPT | llm
    result = await chain.ainvoke({
        "store_name": store_name,
        "faq_context": context,
        "question": question,
    })

    return result.content.strip()
