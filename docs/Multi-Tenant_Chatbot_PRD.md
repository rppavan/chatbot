# Product Requirements Document (PRD): Multi-Tenant E-commerce CX Chatbot

## 1. Product Overview
### 1.1 Purpose
To design and implement a scalable, multi-tenant Customer Experience (CX) Chatbot that automates customer support for an e-commerce platform. The chatbot will serve multiple storefronts (tenants) seamlessly across various communication channels, reducing manual support volume and improving customer satisfaction.

### 1.2 Target Audience
- **End-users:** Customers shopping on various tenant storefronts (both registered users and guest visitors).
- **Internal Users:** Customer Support Agents using Freshdesk to manage escalated queries.

### 1.3 Supported Channels
- WhatsApp
- Web Chat Widget
- Social Media Bots (e.g., Facebook Messenger, Instagram DM)

---

## 2. Architecture & System Integrations
The chatbot must connect to a unified middleware that routes requests to the appropriate downstream service based on the tenant context.

### 2.1 Multi-Tenancy Support
- **Tenant Identification:** The system will identify the tenant based on the incoming channel identifier (e.g., the specific WhatsApp Business number, web widget domain, or social media page).
- **Data Isolation:** Ensure strict data isolation so that users interacting with Store A cannot access data or orders from Store B.

### 2.2 Core Integrations
1. **Shopify (Multi-store):** Integration for fetching order, customer, and product data for Shopify-hosted tenants.
2. **Custom Platform APIs:** Integration using the provided custom endpoints for order management (OMS), user profiles, addresses, and OTP authentication.
3. **Freshdesk:** Integration for support ticket tracking, creation, and live agent handoffs.
4. **3rd Party Logistics & Returns:**
   - **Clickpost:** For AWB tracking, ETA updates, and cancelling shipped orders.
   - **Pragma:** For initiating and managing return and exchange logistics.

### 2.3 API Orchestration Flow
Detailed backend routing and service orchestration are defined in:
👉 **[API_Flows.md](./API_Flows.md)**

---

## 3. Core Features & User Journeys

### 3.1 Conversational Flow (To-Be)
The primary user interaction flow, including decision nodes for different order statuses and escalation paths, is defined in:
👉 **[To-Be_Flow.md](./To-Be_Flow.md)**

### 3.2 Authentication & Profile
- **OTP Login:** Authenticate users via phone number (`/v1/otp/{type}/verify` and `/v2/user/auth/login/otp`).
- **Profile Management:** Address management (`/v2/user/{id}/address`), wallet checks (`/v2/user/{id}/wallet`), and account deletion.

### 3.3 Order Fetching & Selection
- Welcome registered users by name and present a list of recent orders (`/v1/order-search`).
- Provide an intuitive menu for users to select an order and choose an action (Track, Cancel, Return, Exchange).

### 3.4 Order Status & Tracking
**Flow is dependent on the order's state in the OMS:**
- **Pre-dispatch (Preparing/Ready):** 
  - Allow order cancellation (`/v1/order/{id}/cancel`).
  - Allow modification requests (change delivery address, phone number, or product variants).
- **Shipped / In-Transit:** 
  - Fetch tracking details (`/v1/order/{id}/tracking-summary`).
  - Display AWB and ETA (via Clickpost integration or order metafields).
  - Provide options to cancel (reject at delivery) or request delivery address changes.
- **Out for Delivery & Attempt Failed:** 
  - Connect to tracking APIs for real-time status.
- **Delivered:**
  - Enable post-purchase flows: Returns, Exchanges, or reporting missing/damaged items.

### 3.5 Returns & Exchanges
- **Eligibility Check:** Call `/v1/order/{id}/return-options` and `/v1/order/{id}/exchange-options` to verify if the timeframe (e.g., 7 days) and product category allow returns/exchanges.
- **Initiation:** Trigger `/v1/order/{id}/return` or `.../exchange` and optionally send the request to Pragma for logistics routing.
- **Refund Status:** Handle queries regarding refund timelines and failed refunds (escalate to agent if necessary).

### 3.6 Agent Handoff & Ticketing (Freshdesk)
- **Objective:** Reduce agent handoffs as much as possible by fulfilling requests via APIs.
- **Handoff Triggers:** "Chat with an Agent" option on nodes where automated resolution fails (e.g., complex refund issues, missing items, unresolvable delivery delays).
- **Ticketing:** Automatically create a Freshdesk ticket in scenarios requiring asynchronous action (e.g., manual backend verifications) and provide the user with a Ticket ID.

### 3.7 Chat Navigation & CSAT
- **Global Navigation:** All conversation nodes must provide a "Back to Main Menu" or "Close Chat" option.
- **Customer Satisfaction (CSAT):** Automatically initiate a CSAT survey immediately after closing a chat or resolving an issue.

---

## 4. API Endpoints Mapping (Custom Platform)
The chatbot will utilize the following key custom endpoints for user operations:
- **Auth:** `POST /v2/user/auth/login/otp`, `POST /v2/user/auth/verify-otp`
- **User:** `GET /v2/user/{id}/profile`, `GET /v2/user/{id}/address`
- **Orders:** `GET /v1/order-search`, `GET /v1/order/{id}`
- **Order Actions:**
  - `GET /v1/order/{id}/tracking-summary`
  - `GET /v1/order/{id}/cancel_options` -> `POST /v1/order/{id}/cancel`
  - `GET /v1/order/{id}/return-options` -> `POST /v1/order/{id}/return`
  - `GET /v1/order/{id}/exchange-options` -> `POST /v1/order/{id}/exchange`

---

## 5. Non-Functional Requirements
- **High Availability & Low Latency:** Required for seamless chat experiences.
- **Security:** PII and order data must be encrypted; strict OAuth/OTP validation is required before displaying sensitive order details.
- **Scalability:** The architecture must scale horizontally to handle traffic spikes during sales events across all tenants.
