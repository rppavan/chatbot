 Critique the design document @Design_Document.md created using following prompt.

   Create a design document to implement Customer Support Chatbot with PRP: @Multi-Tenant_Chatbot_PRD.md, using LangChain, LangGraph, with 'guided flows' for
   @To-Be_Flow.md & @API_Flows.md
   Use shared memory for multi-step flows, LLM, Tools, dbs.
▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ✓  ReadManyFiles Will attempt to read and concatenate files using patterns:                                                                                     │
│                                                                                                                                                                 │
│ ReadManyFiles Result (Target Dir: /Users/Apparao.Parwatikar/Desktop/tmrw/chatbot)                                                                               │
│                                                                                                                                                                 │
│ Successfully read and concatenated content from 4 file(s).                                                                                                      │
│                                                                                                                                                                 │
│ Processed Files:                                                                                                                                                │
│  - docs/API_Flows.md                                                                                                                                            │
│  - docs/Design_Document.md                                                                                                                                      │
│  - docs/Multi-Tenant_Chatbot_PRD.md                                                                                                                             │
│  - docs/To-Be_Flow.md                                                                                                                                           │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
✦ Here is a critique of the Design Document based on the provided PRD, Mermaid flows, and prompt requirements.

  Overall Assessment
  The design document is exceptionally well-structured and technically sound. It faithfully translates the requirements of the PRD and the visual Mermaid flows into a
  highly feasible LangGraph-based architecture. By treating LangGraph as a deterministic state machine (guided flows) rather than an open-ended autonomous agent, it
  ensures the reliability, safety, and strict multi-tenant isolation required for an enterprise CX chatbot.

  ---

  Strengths & Core Alignments

   1. Perfect Execution of "Guided Flows" (LangGraph):
      - The mapping of the To-Be_Flow.md to LangGraph Nodes and Conditional Edges (Section 4.1) is 1-to-1 and brilliant.
      - Using the interrupt() pattern for human-in-the-loop (waiting for user menu selections) is exactly the right paradigm for asynchronous chat applications like
        WhatsApp.
   2. Excellent Shared Memory Design:
      - The ConversationState TypedDict captures everything perfectly: session auth, tenant boundaries, order caching, and current navigation state. Using
        PostgresSaver with a compound thread_id ({tenant_id}:{session_id}) guarantees strict multi-tenant data isolation.
   3. Appropriate LLM Scoping:
      - Instead of letting the LLM wander, the design limits it to specific, high-value nodes: Intent Classification (routing), Slot Extraction (parsing order IDs from
        text), and RAG (FAQ answers). This prevents hallucinations in critical transaction flows.
   4. Comprehensive Tool Abstraction:
      - Section 5 accurately maps the custom API endpoints from the PRD into LangChain StructuredTool objects.
   5. Robust Global Navigation:
      - Implementing global commands ("main menu", "close chat") via a decorator/wrapper (Section 11) is an elegant way to handle user interrupts without complicating
        the main graph logic.

  ---

  Gaps & Areas for Improvement

  While the design is strong, it misses a few nuanced details present in the API_Flows.md and To-Be_Flow.md:

  1. Shopify vs. OMS Cancellation Branching (API_Flows.md strictness):
   - The Gap: The API_Flows.md explicitly shows a decision tree for "If not shipped": it branches into Shopify cancel API / Initiate Refund on Shopify vs. UC cancel
     API vs. Clickpost cancel API.
   - The Fix: The cancel_order node in the design document (Section 5.2) currently just calls a generic cancel_order_tool. The design should explicitly mention a
     router or logic inside the tool to handle this 3-way split based on the order's origin or state.

  2. Exchange Differential Amounts (API_Flows.md):
   - The Gap: The API_Flows.md mentions a specific edge for Exchanges: "Add case for differential amount?" and for Returns "40% for return / Refund".
   - The Fix: The state schema (ConversationState) and the initiate_exchange node need to account for payment links or differential amount confirmations before
     finalizing the Pragma API call.

  3. Guest Flow Authentication (To-Be_Flow.md):
   - The Gap: The To-Be_Flow.md states: "Guest Flow: Prompt for Phone/Order ID". The design doc routes guests to otp_send, implying they just log in.
   - The Fix: Guest users often don't want to log in fully. The design should allow a "Track via Order ID + Email/Phone" flow without forcing a full JWT/OTP session,
     or explicitly clarify that OTP is mandatory even for guests.

  4. FAQ Knowledge Base Ingestion:
   - The Gap: The design uses a vector store (faq_retriever.invoke) but doesn't explain how tenant-specific documents are ingested.
   - The Fix: Briefly mention a sync job or admin API tool that embeds Freshdesk/Shopify knowledge base articles into the vector DB, tagged with tenant_id metadata.

  5. Handling "Agent Handoff" State:
   - The Gap: Once a user is handed off to an agent (Freshdesk ticket created), what happens to subsequent messages?
   - The Fix: Add a state flag (e.g., is_escalated: bool) to ConversationState. If is_escalated is true, the webhook should route messages directly to the Freshdesk
     conversation API rather than invoking the LangGraph flow, until the agent resolves the ticket.

  ---

  Technical Recommendations for Implementation

   1. State Reducers: In LangGraph ConversationState, ensure you define reducers for fields like messages (using add_messages) so that new chat turns append to the
      list rather than overwriting it.
   2. Timeouts & Cache Expiry: If a user abandons the chat at a menu interrupt() and replies 3 days later, the cached orders in state might be stale. Consider adding a
      timestamp to the state and forcing a re-fetch if the interrupt resumes after a certain TTL (e.g., > 1 hour).
   3. LLM Fallback: In the faq_answer node, ensure there is a fallback to agent_handoff if the RAG retriever returns 0 documents or the LLM output is low confidence.

  Conclusion
  The design document is 95% ready for implementation. It perfectly leverages LangChain and LangGraph to fulfill the PRD. By addressing the minor gaps regarding
  differential exchange amounts, specific API cancellation branching, and the post-handoff chat state, this document will serve as a flawless blueprint for the
  engineering team.