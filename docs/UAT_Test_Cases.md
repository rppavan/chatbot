# User Acceptance Test Cases
## Multi-Tenant E-commerce CX Chatbot

**Version:** 1.0
**Date:** 2026-03-26
**References:** Multi-Tenant_Chatbot_PRD.md, To-Be_Flow.md, API_Flows.md

---

## Test Environment

| Service | URL | Purpose |
|---|---|---|
| Chatbot | http://localhost:8000 | LangGraph conversation engine |
| Mock API | http://localhost:8100 | Simulated e-commerce backend |

**Start services:**
```bash
python -m mock_api.app        # Terminal 1
python run.py                  # Terminal 2
```

**Seed Users:**
| User ID | Name | Phone | Orders |
|---|---|---|---|
| user-001 | Priya Sharma | +919876543210 | ORD-10001 (pre-dispatch), ORD-10002 (shipped) |
| user-002 | Rahul Mehta | +919876543211 | ORD-10003 (out-for-delivery), ORD-10004 (delivered) |
| user-003 | Ananya Gupta | +919876543212 | ORD-10005 (cancelled), ORD-10006 (return-initiated) |

---

## UAT-001: Guest User — OTP Authentication

**User Story:** As a new visitor, I want to verify my phone number so that I can access my orders.
**PRD Reference:** §3.2 Authentication & Profile
**Flow:** To-Be_Flow → CheckUser(No) → GuestFlow

### Preconditions
- Fresh session (no prior conversation)
- No `X-TMRW-User-Id` or `X-TMRW-User-Session` reuse

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send any greeting (e.g., "Hi") | Bot asks for phone number: *"Please enter your phone number (e.g., +919876543210)"* |
| 2 | Enter registered phone: `+919876543210` | Bot sends OTP to phone and shows prompt: *"An OTP has been sent… Please enter the OTP"* (debug OTP shown in dev mode) |
| 3 | Enter the correct OTP | Bot confirms: *"✅ Verified successfully!"* followed by welcome greeting |
| 4 | Observe welcome message | Bot greets: *"Hi Priya Sharma! Welcome to [Store Name]"* and shows main menu (2 options) |

### Pass Criteria
- [ ] Phone prompt appears without `X-TMRW-User-Id` header
- [ ] OTP request succeeds for registered phone
- [ ] Incorrect OTP returns an error, allows retry
- [ ] Correct OTP transitions to welcome with user's name
- [ ] Chat response `is_escalated = false`

---

## UAT-002: Guest User — Wrong OTP Rejected

**User Story:** As a user, if I enter the wrong OTP, I should get an error and be allowed to try again.
**PRD Reference:** §3.2, §5 Security

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hello" (no auth header) | Phone prompt |
| 2 | Enter `+919876543211` | OTP sent message |
| 3 | Enter `000000` (wrong OTP) | Bot shows: *"❌ OTP verification failed. Please try again."* |
| 4 | (Optional) Enter correct OTP | Verification succeeds |

### Pass Criteria
- [ ] Wrong OTP does not authenticate the user
- [ ] Error message is shown
- [ ] Flow allows retry (does not get stuck)

---

## UAT-003: Pre-Authenticated User — Welcome & Main Menu

**User Story:** As a known user (WhatsApp integration has resolved my phone), I want to skip OTP and go straight to support options.
**PRD Reference:** §3.3 Order Fetching
**Header:** `X-TMRW-User-Id: user-001`

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" with `X-TMRW-User-Id: user-001` | Bot greets by name: *"Hi Priya Sharma! Welcome to…"* |
| 2 | Observe menu options | Two options shown: *(1) I need help with my orders* and *(2) Other Issues / FAQs* |

### Pass Criteria
- [ ] No OTP prompt shown
- [ ] User's actual name appears in greeting
- [ ] Two menu options visible
- [ ] `is_escalated = false`, `awaiting_input = true`

---

## UAT-004: Pre-Dispatch Order — View Menu

**User Story:** As a customer with a recently placed order, I want to see what actions are available before it ships.
**User:** user-001 | **Order:** ORD-10001 (status: preparing / pre-dispatch)

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-001) | Welcome + main menu |
| 2 | Select `1` (order help) | Bot fetches orders and lists them with status icons |
| 3 | Select `1` (ORD-10001) | Pre-dispatch action menu appears with options |
| 4 | Read menu options | Must include: Cancel, Change address, Change phone, Make changes in product, Back to main menu |

### Pass Criteria
- [ ] Order list shows ORD-10001 with "preparing" / "🟡" status indicator
- [ ] Pre-dispatch menu shows exactly 5 options
- [ ] Order ID is displayed in menu header
- [ ] Status label is human-readable (e.g., "Preparing")

---

## UAT-005: Pre-Dispatch Order — Cancel Order (Happy Path)

**User Story:** As a customer, I want to cancel my order before it ships and receive a refund.
**PRD Reference:** §3.4 Pre-dispatch
**API Flow:** If not shipped → UC cancel API

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-001) | Welcome + main menu |
| 2 | Select `1` (order help) | Order list |
| 3 | Select `1` (ORD-10001) | Pre-dispatch menu |
| 4 | Select `1` (Cancel my order) | Confirmation prompt with cancellation reasons list |
| 5 | Select `1` (first reason) | Success message: *"✅ Order ORD-10001 has been cancelled"* with refund details |
| 6 | Observe CSAT prompt | Rating options 1–5 shown |
| 7 | Enter `5` (Excellent) | Thank you message and chat closes |

### Pass Criteria
- [ ] Cancellation reasons list is not empty
- [ ] Success message includes order ID
- [ ] Refund amount and method are shown
- [ ] Estimated refund days are mentioned
- [ ] CSAT prompt appears automatically after resolution
- [ ] Chat terminates after CSAT

---

## UAT-006: Pre-Dispatch Order — Cancel Aborted

**User Story:** As a customer, I should be able to back out of a cancellation.

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1–4 | (Same as UAT-005 steps 1–4) | Confirmation prompt |
| 5 | Type `no` | *"Okay, cancellation aborted. Returning to menu."* |

### Pass Criteria
- [ ] Order is NOT cancelled after typing "no"
- [ ] Bot acknowledges the abort gracefully
- [ ] Order status unchanged on subsequent API check

---

## UAT-007: Pre-Dispatch Order — Product Modification Escalates

**User Story:** As a customer wanting to change my order's product/variant, I should be connected to an agent.
**To-Be Flow:** PD_Modify -.-> AgentHandoff

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1–3 | (Navigate to pre-dispatch menu for ORD-10001) | Pre-dispatch menu |
| 4 | Select `4` (Make changes in the product) | Message about agent review needed |
| 5 | Observe bot response | Ticket ID is created; agent handoff message appears |
| 6 | Check `is_escalated` field | Must be `true` |

### Pass Criteria
- [ ] Option 4 leads to agent handoff, not self-service
- [ ] Ticket ID (TKT-XXXXXXXX format) appears in response
- [ ] `is_escalated = true` in API response
- [ ] CSAT shown after ticket creation

---

## UAT-008: Shipped Order — Track Location (AWB & ETA)

**User Story:** As a customer waiting for delivery, I want to see where my order is.
**PRD Reference:** §3.4 Shipped / In-Transit
**User:** user-001 | **Order:** ORD-10002 (status: shipped)

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-001) | Welcome + main menu |
| 2 | Select `1` (order help) | Order list (ORD-10001, ORD-10002) |
| 3 | Select `2` (ORD-10002 — shipped) | Shipped action menu |
| 4 | Observe shipped menu | Options: Where is my order?, Cancel, Change address, Back |
| 5 | Select `1` (Where is my order?) | Tracking info: AWB number, courier name, estimated delivery date, tracking history |

### Pass Criteria
- [ ] Order shows 🚚 shipped indicator in order list
- [ ] Shipped menu shows 4 options
- [ ] Tracking response contains AWB number (AWB123456789)
- [ ] Courier name displayed (BlueDart)
- [ ] Tracking history events shown (at least one event)
- [ ] CSAT prompt appears after tracking

---

## UAT-009: Shipped Order — Cancel (RTO Flow)

**User Story:** As a customer who changed their mind after shipping, I want to initiate a return-to-origin.
**PRD Reference:** §3.4 Shipped — Cancel
**API Flow:** If shipped → Clickpost cancel API

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1–3 | (Navigate to shipped menu for ORD-10002) | Shipped menu |
| 4 | Select `2` (Cancel my order) | RTO warning: *"Order has already been shipped… Cancelling will initiate Return to Origin"* |
| 5 | Type `yes` | RTO initiated; refund timeline after return mentioned |
| 6 | Observe CSAT | Rating prompt shown |

### Pass Criteria
- [ ] RTO warning is clearly shown (not immediate cancel like pre-dispatch)
- [ ] Confirmation step required before proceeding
- [ ] Success message mentions "Return to Origin"
- [ ] Refund is conditional on package return

---

## UAT-010: Delivered Order — View Menu

**User Story:** As a customer who received their delivery, I want to see post-delivery options.
**User:** user-002 | **Order:** ORD-10004 (status: delivered)

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-002) | Welcome: *"Hi Rahul Mehta! Welcome…"* |
| 2 | Select `1` (order help) | Two orders listed (ORD-10003 OFD, ORD-10004 delivered) |
| 3 | Select `2` (ORD-10004 — delivered) | Delivered action menu |
| 4 | Read menu options | 6 options: Return, Exchange, Missing item, Wrong/damaged, Not received, Back |

### Pass Criteria
- [ ] ORD-10004 shows ✅ delivered indicator
- [ ] Delivered menu has all 6 options
- [ ] Order ID appears in menu header

---

## UAT-011: Delivered Order — Initiate Return

**User Story:** As a customer unsatisfied with my delivery, I want to return the order for a refund.
**PRD Reference:** §3.5 Returns & Exchanges
**API Flow:** If Delivered → Initiate Return → Send to Pragma → 40% refund

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1–3 | (Navigate to delivered menu for ORD-10004) | Delivered menu |
| 4 | Select `1` (Return my order) | Return eligibility confirmed; return reasons shown |
| 5 | Select `1` (first return reason) | Return initiated confirmation: Return ID, pickup date, refund amount, refund timeline |
| 6 | Observe CSAT | Rating prompt |
| 7 | Enter `4` (Good) | Thank you + chat closed |

### Pass Criteria
- [ ] Return eligibility check runs (within 7-day window)
- [ ] Return reasons are populated
- [ ] Return ID is generated (format: RTN-XXXXXXXX or similar)
- [ ] Pickup date is shown
- [ ] Refund amount and timeline (7 business days) are mentioned
- [ ] CSAT collected after return initiation

---

## UAT-012: Delivered Order — Exchange with Variant Selection

**User Story:** As a customer who received the wrong size, I want to exchange for a different variant.
**PRD Reference:** §3.5 Returns & Exchanges
**API Flow (Design Critique #2):** Exchange with differential amount handling

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1–3 | (Navigate to delivered menu for ORD-10004) | Delivered menu |
| 4 | Select `2` (Exchange my order) | Available exchange variants shown with size/color/price |
| 5 | If differential amount shown, verify it is visible | Variant list must include differential cost (e.g., "+₹200") |
| 6 | Select `1` (first variant) | If differential > 0: confirmation prompt *"This exchange requires ₹X payment. Proceed? (yes/no)"* |
| 7 | Type `yes` (if differential) OR automatically confirmed | Exchange initiated: Exchange ID, pickup date |
| 8 | Observe CSAT | Rating prompt |

### Pass Criteria
- [ ] Variant list shows size, color, and price
- [ ] Differential amount is visible next to variant (if applicable)
- [ ] Differential > 0 requires explicit "yes" confirmation
- [ ] Exchange ID returned in confirmation
- [ ] Pickup date shown
- [ ] CSAT collected

---

## UAT-013: Delivered Order — Missing Item → Agent Escalation

**User Story:** As a customer who received an incomplete package, I need human support.
**To-Be Flow:** DL_Missing -.-> AgentHandoff

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1–3 | (Navigate to delivered menu for ORD-10004) | Delivered menu |
| 4 | Select `3` (The order had an item missing) | Agent escalation message: *"Sorry… This requires manual investigation"* |
| 5 | Observe ticket creation | Ticket ID (TKT-XXXXXXXX) shown; agent will follow up |
| 6 | Check `is_escalated` | Must be `true` |

### Pass Criteria
- [ ] Option 3 triggers agent handoff (no self-service)
- [ ] Empathetic message shown ("Sorry")
- [ ] Ticket ID is unique and formatted correctly
- [ ] `is_escalated = true`
- [ ] CSAT shown after ticket creation

---

## UAT-014: Delivered Order — Wrong/Damaged Items → Agent Escalation

**User Story:** As a customer who received wrong or damaged goods, I need to raise a complaint.
**To-Be Flow:** DL_Wrong -.-> AgentHandoff

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1–3 | (Navigate to delivered menu for ORD-10004) | Delivered menu |
| 4 | Select `4` (Received wrong or damaged items) | Escalation message + ticket ID |
| 5 | Verify `is_escalated` | Must be `true` |

### Pass Criteria
- [ ] Option 4 goes to agent, not self-service
- [ ] Ticket created with unique ID
- [ ] `is_escalated = true`

---

## UAT-015: Delivered Order — Shows Delivered But Not Received → Escalation

**To-Be Flow:** DL_NotReceived -.-> AgentHandoff

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1–3 | (Navigate to delivered menu) | Delivered menu |
| 4 | Select `5` (Order shows delivered but not received) | Escalation message mentioning courier investigation |
| 5 | Verify `is_escalated` | Must be `true` |

### Pass Criteria
- [ ] Message mentions courier investigation
- [ ] Ticket created
- [ ] `is_escalated = true`

---

## UAT-016: Cancelled Order — Refund Status

**User Story:** As a customer whose order was cancelled, I want to know my refund status.
**To-Be Flow:** CheckStatus(Cancelled) → RefundCheck → EndNode
**User:** user-003 | **Order:** ORD-10005 (cancelled, refund: processed)

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-003) | Welcome: *"Hi Ananya Gupta! Welcome…"* |
| 2 | Select `1` (order help) | Two orders: ORD-10005 (cancelled), ORD-10006 (return initiated) |
| 3 | Select `1` (ORD-10005) | Refund status display: *"Order ORD-10005 was cancelled. ✅ Refund Status: Processed. ₹1899. Date: YYYY-MM-DD"* |
| 4 | Observe CSAT | Rating prompt shown |

### Pass Criteria
- [ ] ORD-10005 shows ❌ cancelled indicator
- [ ] Refund status shown as "Processed" (matches seed data)
- [ ] Refund amount (₹1899) shown correctly
- [ ] Refund date shown
- [ ] No option to cancel/return (order is already cancelled)

---

## UAT-017: Return-Initiated Order — Track Pickup & Refund

**User Story:** As a customer who initiated a return, I want to know the pickup schedule and refund status.
**To-Be Flow:** CheckStatus(Returns) → RT_Track → EndNode
**User:** user-003 | **Order:** ORD-10006 (return_initiated, pickup_scheduled)

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-003) | Welcome |
| 2 | Select `1` (order help) | Order list |
| 3 | Select `2` (ORD-10006) | Return status display: *"Return Status: Pickup Scheduled. Pickup Date: YYYY-MM-DD. Refund Status: Pending. Refund in 7–10 business days."* |
| 4 | CSAT | Rating prompt |

### Pass Criteria
- [ ] ORD-10006 shows 🔄 return indicator
- [ ] Return status is human-readable ("Pickup Scheduled")
- [ ] Pickup date is shown
- [ ] Refund status "Pending" and timeline shown

---

## UAT-018: FAQ — Category Selection & Answer

**User Story:** As a customer with a general query, I want answers from the FAQ section.
**To-Be Flow:** MenuFAQs → FAQ_Categories → (select) → Answer

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-001) | Welcome + main menu |
| 2 | Select `2` (Other Issues / FAQs) | FAQ category menu: 5 categories shown |
| 3 | Read categories | Order/Delivery/Payment, Cancellation Policy, Refunds and Returns, My Account, Other Issues |
| 4 | Select `2` (Cancellation Policy) | Informative answer about cancellation policy |
| 5 | Observe follow-up prompt | Bot asks if there are more questions |
| 6 | Type `no` or `main menu` | Flow proceeds to CSAT |

### Pass Criteria
- [ ] FAQ menu shows exactly 5 categories
- [ ] Cancellation policy answer is relevant and non-empty
- [ ] Follow-up prompt asks if more help needed
- [ ] "main menu" or "no" exits FAQ gracefully
- [ ] CSAT shown after FAQ

---

## UAT-019: FAQ — "Other Issues" Escalates to Agent

**User Story:** If my issue doesn't fit any FAQ category, I should be connected to a human agent.
**To-Be Flow:** FAQ_Other -.-> AgentHandoff

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-001) | Welcome |
| 2 | Select `2` (FAQs) | FAQ categories |
| 3 | Select `5` (Other Issues) | Agent handoff: ticket created |
| 4 | Observe response | Ticket ID shown; agent will follow up |
| 5 | Check `is_escalated` | Must be `true` |

### Pass Criteria
- [ ] Option 5 goes directly to agent (no self-service)
- [ ] Ticket ID appears in response
- [ ] `is_escalated = true`

---

## UAT-020: CSAT Survey — Rating Collection

**User Story:** After every resolved interaction, I should be asked to rate my experience.
**PRD Reference:** §3.7 Customer Satisfaction (CSAT)

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Complete any resolution (e.g., track order) | CSAT prompt: *"How would you rate your experience? 1–5"* |
| 2 | Enter `5` | *"Thank you for your feedback (Rating: 5)! Have a great day! 👋"* |
| 3 | Verify chat is closed | No further responses; graph reaches END |

### Pass Criteria
- [ ] CSAT prompt shown after every flow completion (cancel, return, exchange, track, FAQ, handoff)
- [ ] Rating 1–5 accepted
- [ ] "skip" accepted as valid response
- [ ] Thank you message includes the entered rating
- [ ] Close message sent after CSAT

---

## UAT-021: CSAT Survey — Skip Option

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | At CSAT prompt | Rating prompt visible |
| 2 | Type `skip` | *"Thank you for chatting with us! Have a great day! 👋"* |

### Pass Criteria
- [ ] "skip" accepted without error
- [ ] Chat closes normally

---

## UAT-022: Multi-Tenancy — Store A vs Store B Branding

**User Story:** Each merchant's chatbot must show their store name.
**PRD Reference:** §2.1 Multi-Tenancy Support

### Steps
| # | Header | Expected Bot Response |
|---|---|---|
| 1 | `X-Tenant-Id: store-a` + user-001 | Welcome message contains Store A's name |
| 2 | `X-Tenant-Id: store-b` + user-001 | Welcome message contains Store B's name (different) |

### Pass Criteria
- [ ] Store A and Store B have different store names in welcome
- [ ] Same user sees different branding per tenant
- [ ] No data bleed between tenants

---

## UAT-023: Multi-Tenancy — Session Isolation

**User Story:** Two customers using the same session ID on different stores must have completely independent conversations.
**PRD Reference:** §2.1 Data Isolation

### Steps
| # | Action | Expected |
|---|---|---|
| 1 | Send "Hi" on store-a with session `shared-999` (user-001) | Store A welcome shown |
| 2 | Send "Hi" on store-b with session `shared-999` (user-001) | Store B welcome shown (fresh conversation) |
| 3 | Continue conversation on store-a | State from store-a unaffected by store-b |

### Pass Criteria
- [ ] Both tenants respond independently to the same session ID
- [ ] Conversation states are isolated (`{tenant_id}:{session_id}` compound key)

---

## UAT-024: Session Persistence Across Turns

**User Story:** My conversation state should persist between HTTP requests within the same session.

### Steps
| # | Action | Expected |
|---|---|---|
| 1 | Send "Hi" with `X-TMRW-User-Id: user-001`, session `persist-001` | Welcome + menu |
| 2 | Send "1" (same session, no user-id header) | Order list shown (not re-asked for auth) |
| 3 | Send "1" (same session) | Pre-dispatch menu shown (not restarted) |

### Pass Criteria
- [ ] Auth state persists (no phone prompt on turn 2)
- [ ] Order selection state persists (not reset between turns)
- [ ] No duplicate welcome messages on continued turns

---

## UAT-025: Free-Text Intent Classification (LLM Routing)

**User Story:** I should be able to type natural language instead of menu numbers.
**PRD Reference:** LLM intent classification in main menu and sub-menus

### Steps
| # | User Types | Expected Routing |
|---|---|---|
| 1 | "I want to check my orders" (at main menu) | Routes to order flow (same as typing "1") |
| 2 | "help me with a question about delivery" (at main menu) | Routes to FAQ flow (same as typing "2") |
| 3 | "cancel" (at pre-dispatch menu) | Routes to cancel (same as "1") |
| 4 | "where is my package" (at shipped menu) | Routes to tracking (same as "1") |
| 5 | "I want to return this" (at delivered menu) | Routes to return (same as "1") |

### Pass Criteria
- [ ] Natural language resolves to correct menu option
- [ ] LLM fallback is graceful for ambiguous inputs
- [ ] Edge cases (typos, partial phrases) handled without crash

---

## UAT-026: Out-for-Delivery Order — Tracking

**User Story:** When my order is out for delivery, I want to see the ETA.
**User:** user-002 | **Order:** ORD-10003 (out_for_delivery)

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-002) | Welcome: *"Hi Rahul Mehta! Welcome…"* |
| 2 | Select `1` (order help) | Two orders: ORD-10003 (OFD 🏃), ORD-10004 (delivered ✅) |
| 3 | Select `1` (ORD-10003) | Shipped menu (OFD routes to shipped_menu) with label "Out For Delivery" |
| 4 | Select `1` (Where is my order?) | Tracking info with AWB (AWB987654321), courier (Delhivery) |

### Pass Criteria
- [ ] ORD-10003 shows 🏃 OFD indicator
- [ ] Menu label reflects "Out For Delivery" status
- [ ] AWB and courier shown correctly
- [ ] ETA shown if available

---

## UAT-027: Return-Ineligible Order — Appropriate Rejection

**User Story:** If my order's return window has passed, I should be told clearly rather than shown an error.

### Preconditions
- Modify ORD-10004's delivered_at in mock data to be > 7 days ago, OR test with an order explicitly configured as return-ineligible.

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Navigate to delivered order menu | Delivered menu |
| 2 | Select `1` (Return my order) | *"❌ Order is not eligible for return. Return window is 7 days from delivery."* |

### Pass Criteria
- [ ] Clear ineligibility message shown
- [ ] Return window (7 days) stated explicitly
- [ ] No error/exception thrown
- [ ] Flow continues gracefully (CSAT or back to menu)

---

## UAT-028: No Orders Found

**User Story:** If a customer has no orders, they should see a helpful message rather than an empty screen.

### Preconditions
- Use a user_id with no associated orders (e.g., `user-004`)

### Steps
| # | User Action | Expected Bot Response |
|---|---|---|
| 1 | Send "Hi" (pre-auth user-004) | Welcome: *"Hi Vikram Patel! Welcome…"* |
| 2 | Select `1` (order help) | *"📦 You don't have any orders yet. Is there anything else I can help with?"* |

### Pass Criteria
- [ ] No crash or empty list shown
- [ ] Friendly "no orders" message
- [ ] Flow continues (not stuck)

---

## UAT-029: WhatsApp Channel — Phone-to-User Resolution

**User Story:** When a WhatsApp message arrives from a known phone number, the system pre-authenticates the user.
**PRD Reference:** §1.3 Supported Channels — WhatsApp

### Preconditions
- WhatsApp service running on port 8200
- Valid `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` in `.env`

### Steps
| # | Action | Expected |
|---|---|---|
| 1 | WhatsApp service receives message from `+919876543210` | Calls `GET /v2/user?phone=+919876543210` |
| 2 | Mock API returns user-001 | WhatsApp service sets `X-TMRW-User-Id: user-001` in forwarded request |
| 3 | Chatbot receives request with pre-auth | Welcome shown without OTP |
| 4 | Response sent back via WhatsApp API | User sees greeting on WhatsApp |

### Pass Criteria
- [ ] Phone lookup returns correct user
- [ ] Pre-authentication bypasses OTP for known users
- [ ] Response forwarded back via WhatsApp Cloud API

---

## UAT-030: API Response Schema Validation

**User Story:** As a developer integrating the chatbot, all responses must have a consistent structure.

### Test Data
Any POST to `/chat`

### Expected Response Schema
```json
{
  "session_id": "string",
  "responses": ["string", "..."],
  "is_escalated": false,
  "awaiting_input": true
}
```

### Pass Criteria
- [ ] `session_id` matches `X-TMRW-User-Session` header value
- [ ] `responses` is always a non-empty list of strings
- [ ] `is_escalated` is always a boolean
- [ ] `awaiting_input` is always a boolean
- [ ] Missing `X-TMRW-User-Session` returns HTTP 400
- [ ] No 500 errors under normal operation

---

## Test Execution Summary

| UAT ID | Feature | Tester | Date | Result | Notes |
|---|---|---|---|---|---|
| UAT-001 | Guest OTP Authentication | | | | |
| UAT-002 | Wrong OTP Rejection | | | | |
| UAT-003 | Pre-Auth Skip OTP | | | | |
| UAT-004 | Pre-Dispatch View Menu | | | | |
| UAT-005 | Pre-Dispatch Cancel (Happy) | | | | |
| UAT-006 | Pre-Dispatch Cancel Abort | | | | |
| UAT-007 | Pre-Dispatch Product Modify → Agent | | | | |
| UAT-008 | Shipped Track (AWB/ETA) | | | | |
| UAT-009 | Shipped Cancel (RTO) | | | | |
| UAT-010 | Delivered View Menu | | | | |
| UAT-011 | Delivered Return | | | | |
| UAT-012 | Delivered Exchange + Differential | | | | |
| UAT-013 | Missing Item → Agent | | | | |
| UAT-014 | Wrong/Damaged → Agent | | | | |
| UAT-015 | Not Received → Agent | | | | |
| UAT-016 | Cancelled Refund Status | | | | |
| UAT-017 | Return-Initiated Tracking | | | | |
| UAT-018 | FAQ Category & Answer | | | | |
| UAT-019 | FAQ Other Issues → Agent | | | | |
| UAT-020 | CSAT Rating Collection | | | | |
| UAT-021 | CSAT Skip | | | | |
| UAT-022 | Multi-Tenant Branding | | | | |
| UAT-023 | Multi-Tenant Session Isolation | | | | |
| UAT-024 | Session Persistence | | | | |
| UAT-025 | Free-Text Intent (LLM) | | | | |
| UAT-026 | Out-for-Delivery Tracking | | | | |
| UAT-027 | Return-Ineligible Rejection | | | | |
| UAT-028 | No Orders Found | | | | |
| UAT-029 | WhatsApp Phone Resolution | | | | |
| UAT-030 | API Response Schema | | | | |
