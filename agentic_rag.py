import os
import re
import sys
import json
from datetime import datetime
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
from google import genai
import chromadb
from langgraph.graph import StateGraph, END

# Reconfigure stdout for UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load environment
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file.")

client = genai.Client(api_key=API_KEY)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_collection(name="amazon_shipping_docs")

# Mock Transactional Order Database (Multiple diverse real-world orders)
# Mock Transactional Order Database (8 diverse real-world orders in memory)
MOCK_ORDERS = {
    "112-9874561-3456789": {
        "item": "Sony WH-1000XM5 Noise-Canceling Headphones",
        "price": "$349.99",
        "status": "Delayed in Transit",
        "reason": "Severe winter weather grounding flights at Louisville, KY distribution hub",
        "carrier": "UPS Air Ground",
        "tracking_number": "1Z999AA10123456784",
        "original_delivery": "Yesterday by 8:00 PM",
        "revised_delivery": "Tomorrow by 8:00 PM",
        "action_required": "Please allow 48 hours for tracking updates. If not received by tomorrow, a full refund or replacement can be issued."
    },
    "114-1234567-7654321": {
        "item": "Kindle Paperwhite (16 GB, Black)",
        "price": "$149.99",
        "status": "Out for Delivery",
        "reason": "Loaded onto Amazon delivery van with your local driver",
        "carrier": "Amazon Logistics",
        "tracking_number": "TBA123456789000",
        "original_delivery": "Today by 9:00 PM",
        "revised_delivery": "Today by 9:00 PM",
        "action_required": "Driver is 4 stops away in your neighborhood."
    },
    "113-5544332-9988776": {
        "item": "Nike Air Zoom Pegasus Running Shoes",
        "price": "$129.00",
        "status": "Ready for Pickup at Amazon Locker",
        "reason": "Delivered securely into Amazon Locker - 'Acorn' (Whole Foods Market, 5th Ave)",
        "carrier": "Amazon Logistics",
        "tracking_number": "TBA998877665544",
        "original_delivery": "Delivered Today at 11:30 AM",
        "revised_delivery": "Pickup deadline: Thursday by 9:00 PM (3 days remaining)",
        "action_required": "Scan pickup barcode or use 6-digit code '482910' at the Locker screen or via Bluetooth."
    },
    "111-7788990-1122334": {
        "item": "Apple iPad Air 11-inch (M2 chip, 128GB)",
        "price": "$599.00",
        "status": "Preparing for Shipment",
        "reason": "Order verified and inventory is being packaged at the fulfillment center",
        "carrier": "FedEx Priority Overnight",
        "tracking_number": "Pending dispatch scan",
        "original_delivery": "Friday by 8:00 PM",
        "revised_delivery": "Friday by 8:00 PM",
        "action_required": "Order has not dispatched yet. You can still cancel or change shipping address in Your Orders."
    },
    "115-4433221-5566778": {
        "item": "De'Longhi Magnifica Espresso Machine (AmazonGlobal)",
        "price": "$699.95",
        "status": "Customs Clearance Hold",
        "reason": "Border customs document clearance processing at Port of Entry",
        "carrier": "DHL Express International",
        "tracking_number": "DHL9876543210",
        "original_delivery": "October 24",
        "revised_delivery": "October 28 by 6:00 PM",
        "action_required": "Import duties and taxes are fully covered by your Import Fees Deposit. No action required."
    },
    "116-2233445-6677889": {
        "item": "The North Face ThermoBall Winter Jacket",
        "price": "$220.00",
        "status": "Marked Delivered (Check Safe Drop)",
        "reason": "Carrier reported package delivered to front porch at 2:15 PM today",
        "carrier": "USPS Priority Mail",
        "tracking_number": "9400100000000000000000",
        "original_delivery": "Today at 2:15 PM",
        "revised_delivery": "Delivered",
        "action_required": "Please check porch, garage, and with neighbors. If still missing after 48 hours, contact us for an instant replacement."
    },
    "117-6655443-2211009": {
        "item": "Lego Star Wars Millennium Falcon Starship Model",
        "price": "$169.99",
        "status": "Returned & Refunded",
        "reason": "Customer return received and inspected at fulfillment center in Hebron, KY",
        "carrier": "UPS Return Service",
        "tracking_number": "1Z999RET0192837465",
        "original_delivery": "October 18",
        "revised_delivery": "Refund Complete",
        "action_required": "A full refund of $169.99 was credited back to your original payment card on October 22. Receipt available in Your Payments."
    },
    "118-9900112-3344556": {
        "item": "Anker Prime 100W GaN Fast Charger & USB-C Cable",
        "price": "$45.99",
        "status": "Same-Day Prime Delivery in Progress",
        "reason": "Dispatched from local sub-same-day delivery station with Prime Courier",
        "carrier": "Amazon Prime FastTrack",
        "tracking_number": "TBA887766554433",
        "original_delivery": "Today between 5:00 PM and 10:00 PM",
        "revised_delivery": "Today by 7:30 PM (Est. 45 mins away)",
        "action_required": "Courier is making deliveries in your postal code. Delivery photo will be uploaded upon drop-off."
    }
}

# Numbered order index lookup
ORDER_INDEX_MAP = {
    "1": "112-9874561-3456789",
    "2": "114-1234567-7654321",
    "3": "113-5544332-9988776",
    "4": "111-7788990-1122334",
    "5": "115-4433221-5566778",
    "6": "116-2233445-6677889",
    "7": "117-6655443-2211009",
    "8": "118-9900112-3344556",
}

# Keyword mapping to orders for natural conversational queries (e.g. "where is my kindle?")
ORDER_KEYWORDS_MAP = {
    "112-9874561-3456789": ["sony", "wh-1000xm5", "1000xm5", "headphone", "headphones", "headset"],
    "114-1234567-7654321": ["kindle", "paperwhite", "e-reader", "ereader", "book"],
    "113-5544332-9988776": ["nike", "pegasus", "shoes", "shoe", "running shoes", "sneakers"],
    "111-7788990-1122334": ["ipad", "apple", "tablet", "m2", "ipad air"],
    "115-4433221-5566778": ["delonghi", "de'longhi", "espresso", "coffee", "magnifica"],
    "116-2233445-6677889": ["north face", "jacket", "coat", "thermoball", "winter jacket"],
    "117-6655443-2211009": ["lego", "star wars", "millennium falcon", "falcon"],
    "118-9900112-3344556": ["anker", "charger", "fast charger", "usb-c", "gan", "cable"]
}

# Define LangGraph State
class AgentState(TypedDict):
    question: str
    intent: str                  # 'order_tracking' | 'list_orders' | 'policy_query' | 'urgent_escalation' | 'action_execution' | 'out_of_scope'
    order_id: Optional[str]
    action_type: Optional[str]   # 'replacement' | 'refund' | 'callback'
    documents: List[str]
    doc_distances: List[float]
    doc_relevance: str           # 'relevant' | 'not_relevant'
    response: str
    steps_taken: List[str]
    orders_list: Optional[List[dict]]

# Helper: Extract 17-digit Amazon Order ID, ordinal index, or item keyword
def extract_order_id(text: str) -> Optional[str]:
    # 1. Direct 17-digit Order ID (with hyphens e.g. 112-9874561-3456789)
    match = re.search(r"\b\d{3}-\d{7}-\d{7}\b", text)
    if match:
        return match.group(0)

    # 1b. Direct 17-digit Order ID without hyphens
    match_digits = re.search(r"\b(\d{3})(\d{7})(\d{7})\b", text)
    if match_digits:
        formatted_id = f"{match_digits.group(1)}-{match_digits.group(2)}-{match_digits.group(3)}"
        if formatted_id in MOCK_ORDERS:
            return formatted_id

    # 2. Exact key check
    for word in text.split():
        clean_word = word.strip("#,.;:!?()")
        if clean_word in MOCK_ORDERS:
            return clean_word

    text_lower = text.lower().strip()

    # 3. Direct number input (e.g. "1", "2", "3", ... "8")
    if text_lower in ORDER_INDEX_MAP:
        return ORDER_INDEX_MAP[text_lower]

    # 4. Ordinal phrase (e.g. "order 1", "order #2", "order number 3", "order no. 4", "item 3", "#5")
    num_match = re.search(r"\b(?:order(?:\s*(?:number|no\.?))?|item|#)\s*#?\s*([1-8])\b", text_lower)
    if num_match:
        idx = num_match.group(1)
        if idx in ORDER_INDEX_MAP:
            return ORDER_INDEX_MAP[idx]

    # 5. Item keyword matching (e.g. "kindle", "ipad", "headphones", "nike", "espresso")
    for oid, kws in ORDER_KEYWORDS_MAP.items():
        if any(kw in text_lower for kw in kws):
            return oid

    # 6. Check for partial order ID (e.g. unique 7-digit segment like 7654321)
    for oid in MOCK_ORDERS:
        segments = oid.split("-")
        for seg in segments[1:]:
            if seg in text:
                return oid

    return None

# Global session tracker for active order
ACTIVE_SESSION = {
    "last_order_id": None
}

# ==========================================
# Graph Nodes
# ==========================================

def intent_router_node(state: AgentState) -> dict:
    """Classifies user intent using Gemini reasoning and keyword triggers."""
    q = state["question"].lower()
    steps = state.get("steps_taken", []) + ["1. Intent Routing"]
    
    # Check 1: Did customer explicitly ask to discuss a different/another order?
    switch_order_triggers = [
        "different order", "another order", "switch order", "new order", 
        "other order", "change order", "different package", "separate order",
        "talk about a different", "discuss a different", "check another",
        "about another", "about a different"
    ]
    if any(k in q for k in switch_order_triggers):
        ACTIVE_SESSION["last_order_id"] = None
        return {
            "intent": "switch_order",
            "order_id": None,
            "steps_taken": steps + ["-> Customer requested to switch orders; cleared previous order memory"]
        }

    # Check 2: Did customer ask to see all orders loaded in memory?
    list_orders_triggers = [
        "show orders", "list orders", "show my orders", "list my orders",
        "orders in memory", "what orders", "which orders", "order ids",
        "my orders", "view orders", "all orders", "orders loaded",
        "different orders", "available orders"
    ]
    if any(k in q for k in list_orders_triggers) and not any(k in q for k in ["why", "delayed", "where is", "track order"]):
        return {
            "intent": "list_orders",
            "order_id": None,
            "steps_taken": steps + ["-> Customer requested to view all orders loaded in session memory"]
        }

    # Extract order ID if explicitly written in the message
    explicit_order_id = extract_order_id(state["question"])
    if explicit_order_id:
        ACTIVE_SESSION["last_order_id"] = explicit_order_id
        order_id = explicit_order_id
    else:
        order_id = None  # Do NOT assume previous order for new questions!

    # Fast Check: Action Execution (Option 1, 2, or 3) on currently active order
    cached_order_id = explicit_order_id or ACTIVE_SESSION.get("last_order_id")
    if any(k in q for k in ["option 1", "replace", "replacement", "send new", "resend"]):
        return {
            "intent": "action_execution",
            "action_type": "replacement",
            "order_id": cached_order_id,
            "steps_taken": steps + ["-> Classified intent as: ACTION_EXECUTION (Replacement)"]
        }
    if any(k in q for k in ["option 2", "refund", "money back"]):
        return {
            "intent": "action_execution",
            "action_type": "refund",
            "order_id": cached_order_id,
            "steps_taken": steps + ["-> Classified intent as: ACTION_EXECUTION (Refund)"]
        }
    if any(k in q for k in ["option 3", "callback", "have someone call", "call my phone"]):
        return {
            "intent": "action_execution",
            "action_type": "callback",
            "order_id": cached_order_id,
            "steps_taken": steps + ["-> Classified intent as: ACTION_EXECUTION (Live Callback)"]
        }

    # Fast Check: Urgent Escalation / Rejection of waiting
    urgency_keywords = [
        "can't wait", "cant wait", "cannot wait", "direct now", "reply now",
        "urgent", "immediately", "right now", "too late", "don't want to wait", "dont want to wait"
    ]
    if any(k in q for k in urgency_keywords):
        return {
            "intent": "urgent_escalation",
            "order_id": cached_order_id,
            "steps_taken": steps + ["-> Classified intent as: URGENT_ESCALATION"]
        }

    prompt = f"""You are an intent classifier for Amazon Customer Support.
Classify the following customer question into exactly ONE of these categories:
- ORDER_TRACKING: The customer is asking about their personal order, package delivery status, delays on their specific shipment, or tracking a package.
- URGENT_ESCALATION: The customer expresses frustration with delays, demands an immediate reply/solution right now, or says they cannot wait.
- POLICY_QUERY: The customer is asking a general policy, pricing, shipping speed, Amazon Locker, or terms question (not about a specific personal package).
- OUT_OF_SCOPE: The question is about returns, refunds, password resets, account security, or non-shipping topics.

Customer Question: "{state['question']}"

Respond with ONLY the category name."""

    res = client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
    raw_intent = res.text.strip().upper()

    if "URGENT" in raw_intent:
        intent = "urgent_escalation"
    elif "ORDER_TRACKING" in raw_intent or "my package" in q or "my delivery" in q or "my order" in q:
        intent = "order_tracking"
    elif "OUT_OF_SCOPE" in raw_intent:
        intent = "out_of_scope"
    else:
        intent = "policy_query"

    return {
        "intent": intent,
        "order_id": order_id,
        "steps_taken": steps + [f"-> Classified intent as: {intent.upper()}"]
    }

def ask_order_id_node(state: AgentState) -> dict:
    """Directly presents available orders and prompts for selection."""
    steps = state["steps_taken"] + ["2. Request Order Selection from Account Memory"]
    
    orders_data = []
    icons = ["🎧", "📖", "👟", "📱", "☕", "🧥", "🚀", "⚡"]
    for i, (oid, o) in enumerate(MOCK_ORDERS.items(), 1):
        icon = icons[i-1] if i-1 < len(icons) else "📦"
        orders_data.append({
            "index": i,
            "order_id": oid,
            "icon": icon,
            "item": o["item"],
            "price": o["price"],
            "status": o["status"],
            "carrier": o["carrier"],
            "revised_delivery": o["revised_delivery"]
        })
    
    order_lines = []
    for o in orders_data:
        order_lines.append(f"• **[{o['index']}]** {o['icon']} **{o['item']}** ({o['price']}) — *{o['status']}*")
    
    orders_formatted = "\n".join(order_lines)
    
    reply = (
        "Here are your recent active orders.\n\n"
        "👉 **Click any order below** to view its full live tracking and carrier details, or reply with the **order number** (e.g. *1*, *2*), **item name** (e.g. *Kindle*), or **Order ID**:\n\n"
        f"{orders_formatted}"
    )
    return {
        "response": reply, 
        "steps_taken": steps,
        "orders_list": orders_data
    }

def list_orders_node(state: AgentState) -> dict:
    """Displays full formatted dashboard of all orders in account memory."""
    steps = state["steps_taken"] + ["2. List All Orders in Account Memory"]
    
    order_lines = []
    icons = ["🎧", "📖", "👟", "📱", "☕", "🧥", "🚀", "⚡"]
    for i, (oid, o) in enumerate(MOCK_ORDERS.items(), 1):
        icon = icons[i-1] if i-1 < len(icons) else "📦"
        order_lines.append(
            f"**[{i}] {icon} {o['item']}** ({o['price']})\n"
            f"   • **Order ID:** `{oid}`\n"
            f"   • **Status:** {o['status']}\n"
            f"   • **Carrier:** {o['carrier']} (`{o['tracking_number']}`)\n"
            f"   • **Delivery:** {o['revised_delivery']}"
        )
    
    orders_formatted = "\n\n".join(order_lines)
    
    reply = (
        "📦 **Your Orders Loaded in Memory (8 Total):**\n\n"
        f"{orders_formatted}\n\n"
        "💡 **You can ask about any of these anytime!** For example:\n"
        "- *'Where is my Kindle?'*\n"
        "- *'Why is my Sony headphone order delayed?'*\n"
        "- *'What is the locker pickup code for my shoes?'*\n"
        "- *'Can I cancel my iPad order?'*\n"
        "- *'Check order #5'* or provide any 17-digit Order ID directly."
    )
    return {"response": reply, "steps_taken": steps}

def lookup_order_node(state: AgentState) -> dict:
    """Fetches real order tracking status from mock/API database."""
    order_id = state["order_id"]
    ACTIVE_SESSION["last_order_id"] = order_id
    steps = state["steps_taken"] + [f"2. Query Live Order API for #{order_id}"]
    
    order = MOCK_ORDERS.get(order_id)
    if not order:
        order = {
            "item": "Ordered Item",
            "price": "$0.00",
            "status": "Delayed in Transit",
            "reason": "Carrier transit scan delayed due to regional network backlog",
            "carrier": "Amazon Logistics",
            "tracking_number": "TBA987654321000",
            "original_delivery": "Yesterday",
            "revised_delivery": "Expected within 24 to 48 hours",
            "action_required": "Per our 48-hour buffer policy, if not delivered within 48 hours, contact us for an instant replacement or refund."
        }

    reply = (
        f"Thank you! Here are the live tracking details for Order #{order_id}:\n\n"
        f"📦 **Item:** {order.get('item')} ({order.get('price', '$0.00')})\n"
        f"📍 **Status:** **{order.get('status')}**\n"
        f"🚚 **Carrier:** {order.get('carrier')} (Tracking: `{order.get('tracking_number')}`)\n"
        f"ℹ️ **Status Details:** {order.get('reason')}\n"
        f"🕒 **Expected Delivery / Window:** {order.get('revised_delivery')}\n\n"
        f"👉 **Next Steps:** {order.get('action_required')}\n\n"
        f"*(To ask about another order, type 'switch order' or mention another item!)*"
    )
    return {"response": reply, "steps_taken": steps, "order_id": order_id}

def retriever_node(state: AgentState) -> dict:
    """Retrieves top matching policy chunks from ChromaDB."""
    steps = state["steps_taken"] + ["2. Retrieve Chunks from Vector DB"]
    
    q_emb = client.models.embed_content(
        model="gemini-embedding-001",
        contents=state["question"]
    ).embeddings[0].values

    results = collection.query(query_embeddings=[q_emb], n_results=3)
    docs = results["documents"][0]
    distances = results["distances"][0] if "distances" in results else [0.0]*len(docs)

    return {
        "documents": docs,
        "doc_distances": distances,
        "steps_taken": steps + [f"-> Retrieved {len(docs)} chunks (top distance: {distances[0]:.4f})"]
    }

def document_grader_node(state: AgentState) -> dict:
    """Corrective RAG: Checks if retrieved chunks are genuinely relevant."""
    steps = state["steps_taken"] + ["3. Document Relevance Grader"]
    top_dist = state["doc_distances"][0] if state["doc_distances"] else 1.0

    # If distance is too high (> 0.38), the knowledge base does not have the answer
    if top_dist > 0.38:
        relevance = "not_relevant"
        steps.append(f"-> Grader rejected docs: Top distance {top_dist:.4f} > 0.38 threshold.")
    else:
        relevance = "relevant"
        steps.append(f"-> Grader approved docs: Top distance {top_dist:.4f} is within relevance threshold.")

    return {"doc_relevance": relevance, "steps_taken": steps}

def generator_node(state: AgentState) -> dict:
    """Generates grounded answer from approved documents."""
    steps = state["steps_taken"] + ["4. Grounded Response Generation"]
    context = "\n\n".join(state["documents"])
    
    prompt = f"""You are a professional Amazon Customer Support Assistant.
Answer the customer's question strictly using ONLY the following verified policy context:

[Verified Context]:
{context}

[Customer Question]:
{state['question']}

Rules:
- State the specific policy name and section.
- Be clear, direct, and concise.
- Do not make up any policies outside the provided context.
"""
    res = client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
    return {"response": res.text, "steps_taken": steps}

def urgent_escalation_node(state: AgentState) -> dict:
    """Provides immediate, real-time resolution options instead of waiting."""
    order_id = state.get("order_id") or ACTIVE_SESSION.get("last_order_id") or "112-9874561-3456789"
    order = MOCK_ORDERS.get(order_id, {})
    item_name = order.get("item", "your item")
    price = order.get("price", "$349.99")
    steps = state["steps_taken"] + [f"2. Instant Escalation Handler for Order #{order_id}"]
    
    reply = (
        f"I completely understand this is urgent and waiting does not work for you!\n"
        f"Since Order #{order_id} ({item_name}) has experienced delivery issues, I can resolve this immediately right now:\n\n"
        f"1. [Option 1] - Dispatch a Free Priority Replacement: I will create a priority replacement for {item_name} with complimentary One-Day Shipping.\n"
        f"2. [Option 2] - Issue an Instant Full Refund: I will cancel this shipment and process an immediate full refund of {price} to your original payment method.\n"
        f"3. [Option 3] - Request a Live Phone Callback: A supervisor from our Senior Escalation Desk will call your phone in under 2 minutes.\n\n"
        f"Please reply with 'Option 1', 'Option 2', or 'Option 3' and I will execute it immediately!"
    )
    return {"response": reply, "steps_taken": steps}

def action_execution_node(state: AgentState) -> dict:
    """Executes the chosen immediate action (Refund, Replacement, Callback)."""
    action_type = state.get("action_type", "refund")
    order_id = state.get("order_id") or ACTIVE_SESSION.get("last_order_id") or "112-9874561-3456789"
    order = MOCK_ORDERS.get(order_id, {})
    item_name = order.get("item", "your ordered item")
    price = order.get("price", "$349.99")
    steps = state["steps_taken"] + [f"2. Action Execution Engine ({action_type.upper()})"]

    if action_type == "replacement":
        new_order_id = "114-8889999-4455667"
        reply = (
            f"[ACTION COMPLETED: FREE REPLACEMENT DISPATCHED]\n\n"
            f"I have initiated a complimentary priority replacement for Order #{order_id}!\n"
            f"- New Replacement Order ID: #{new_order_id}\n"
            f"- Item: {item_name}\n"
            f"- Shipping Speed: Priority One-Day (Complimentary)\n"
            f"- Guaranteed Delivery: Tomorrow by 8:00 PM\n"
            f"- Confirmation: A confirmation receipt has been sent to your registered email address.\n\n"
            f"Is there anything else I can assist you with today?"
        )
    elif action_type == "callback":
        reply = (
            f"[ACTION COMPLETED: LIVE AGENT CALLBACK INITIATED]\n\n"
            f"I have connected your inquiry regarding Order #{order_id} ({item_name}) directly to our Senior Logistics Escalation Desk.\n"
            f"- Estimated Wait Time: Under 2 minutes\n"
            f"- Destination: Your registered account phone number (ending in -4829)\n"
            f"- Agent Dossier: The supervisor will already have your tracking history and delay logs ready when they ring.\n\n"
            f"Please keep your phone nearby. Thank you for your patience!"
        )
    else:  # refund
        reply = (
            f"[ACTION COMPLETED: INSTANT REFUND PROCESSED]\n\n"
            f"I have canceled shipment #{order_id} and processed your full refund!\n"
            f"- Refund Reference: REF-8492019-AMZ\n"
            f"- Amount Refunded: {price}\n"
            f"- Item: {item_name}\n"
            f"- Destination: Original payment card\n"
            f"- Timeline: Funds will reflect in your account within 1 to 3 business days depending on your bank.\n\n"
            f"We sincerely apologize for the shipping delay. Is there anything else I can help with?"
        )

    return {"response": reply, "steps_taken": steps}

def switch_order_node(state: AgentState) -> dict:
    """Handles switching to a different order and prompts for new Order ID."""
    ACTIVE_SESSION["last_order_id"] = None
    steps = state["steps_taken"] + ["2. Switch Order Handler (Memory Cleared)"]
    
    order_lines = []
    icons = ["🎧", "📖", "👟", "📱", "☕", "🧥", "🚀", "⚡"]
    for i, (oid, o) in enumerate(MOCK_ORDERS.items(), 1):
        icon = icons[i-1] if i-1 < len(icons) else "📦"
        order_lines.append(f"{i}. {icon} **{o['item']}** (`{oid}`) - *{o['status']}*")
    
    orders_formatted = "\n".join(order_lines)
    
    reply = (
        "Certainly! I have cleared your previous order details from this active session.\n\n"
        "Here are the orders available in your account memory to discuss:\n\n"
        f"{orders_formatted}\n\n"
        "Which order would you like to check? You can reply with the **Order ID**, the **item name** (e.g. *'Kindle'*), or the **number** (e.g. *'3'*)."
    )
    return {"response": reply, "steps_taken": steps, "order_id": None}

def fallback_node(state: AgentState) -> dict:
    """Handles out of scope or ungrounded queries politely."""
    steps = state["steps_taken"] + ["4. Guardrail Fallback"]
    reply = (
        "Hello! I am specialized in Amazon Shipping and Delivery policies. "
        "The inquiry you asked about is outside my verified shipping documentation.\n\n"
        "For assistance with returns, refunds, payments, or account security, please visit our "
        "main Customer Service Hub or contact our general support specialists."
    )
    return {"response": reply, "steps_taken": steps}

# ==========================================
# Conditional Edge Routers
# ==========================================

def route_after_intent(state: AgentState) -> str:
    intent = state["intent"]
    if intent == "switch_order":
        return "switch_order"
    elif intent == "list_orders":
        return "list_orders"
    elif intent == "urgent_escalation":
        return "urgent_escalation"
    elif intent == "action_execution":
        return "action_execution"
    elif intent == "order_tracking":
        if state.get("order_id"):
            return "lookup_order"
        else:
            return "ask_order_id"
    elif intent == "out_of_scope":
        return "fallback"
    else:
        return "retriever"

def route_after_grader(state: AgentState) -> str:
    if state["doc_relevance"] == "relevant":
        return "generator"
    return "fallback"

# ==========================================
# Build the LangGraph Workflow
# ==========================================

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("intent_router", intent_router_node)
workflow.add_node("switch_order", switch_order_node)
workflow.add_node("list_orders", list_orders_node)
workflow.add_node("urgent_escalation", urgent_escalation_node)
workflow.add_node("action_execution", action_execution_node)
workflow.add_node("ask_order_id", ask_order_id_node)
workflow.add_node("lookup_order", lookup_order_node)
workflow.add_node("retriever", retriever_node)
workflow.add_node("document_grader", document_grader_node)
workflow.add_node("generator", generator_node)
workflow.add_node("fallback", fallback_node)

# Set entry point
workflow.set_entry_point("intent_router")

# Add edges
workflow.add_conditional_edges(
    "intent_router",
    route_after_intent,
    {
        "switch_order": "switch_order",
        "list_orders": "list_orders",
        "urgent_escalation": "urgent_escalation",
        "action_execution": "action_execution",
        "ask_order_id": "ask_order_id",
        "lookup_order": "lookup_order",
        "retriever": "retriever",
        "fallback": "fallback"
    }
)

workflow.add_edge("retriever", "document_grader")

workflow.add_conditional_edges(
    "document_grader",
    route_after_grader,
    {
        "generator": "generator",
        "fallback": "fallback"
    }
)

workflow.add_edge("switch_order", END)
workflow.add_edge("list_orders", END)
workflow.add_edge("urgent_escalation", END)
workflow.add_edge("action_execution", END)
workflow.add_edge("ask_order_id", END)
workflow.add_edge("lookup_order", END)
workflow.add_edge("generator", END)
workflow.add_edge("fallback", END)

# Compile LangGraph application
agent_app = workflow.compile()

# ==========================================
# Query & Interactive Execution
# ==========================================

def process_agentic_chat(query: str) -> dict:
    """Executes LangGraph agent and returns full structured result for Web UI."""
    initial_state: AgentState = {
        "question": query,
        "intent": "",
        "order_id": None,
        "action_type": None,
        "documents": [],
        "doc_distances": [],
        "doc_relevance": "",
        "response": "",
        "steps_taken": [],
        "orders_list": []
    }

    final_state = agent_app.invoke(initial_state)

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "intent": final_state.get("intent", ""),
        "steps": final_state.get("steps_taken", []),
        "response": final_state.get("response", "")
    }
    try:
        logs = []
        if os.path.exists("chat_history.json"):
            with open("chat_history.json", "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append(log_entry)
        with open("chat_history.json", "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass

    return {
        "response": final_state.get("response", ""),
        "intent": final_state.get("intent", ""),
        "steps": final_state.get("steps_taken", []),
        "order_id": final_state.get("order_id"),
        "doc_distances": final_state.get("doc_distances", []),
        "orders_list": final_state.get("orders_list", [])
    }

def run_agentic_query(query: str):
    print("\n" + "="*70)
    print(f"Customer Question: {query}")
    print("="*70)

    initial_state: AgentState = {
        "question": query,
        "intent": "",
        "order_id": None,
        "action_type": None,
        "documents": [],
        "doc_distances": [],
        "doc_relevance": "",
        "response": "",
        "steps_taken": [],
        "orders_list": []
    }

    final_state = agent_app.invoke(initial_state)

    print("\n[LangGraph Execution Path]:")
    for step in final_state["steps_taken"]:
        print(f"  • {step}")

    print("\n[Support Assistant Response]:")
    print(final_state["response"])
    print("="*70 + "\n")

    # Save to chat history log
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "intent": final_state["intent"],
        "steps": final_state["steps_taken"],
        "response": final_state["response"]
    }
    try:
        logs = []
        if os.path.exists("chat_history.json"):
            with open("chat_history.json", "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append(log_entry)
        with open("chat_history.json", "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass

    return final_state["response"]

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_agentic_query(" ".join(sys.argv[1:]))
    else:
        print("\n" + "="*75)
        print("🧠 LangGraph Agentic Customer Support (Amazon Shipping & Orders)")
        print("="*75)
        print("📦 8 Orders Loaded in Memory:")
        print("  [1] 112-9874561-3456789 | Sony WH-1000XM5 Headphones | Delayed in Transit")
        print("  [2] 114-1234567-7654321 | Kindle Paperwhite (16 GB)   | Out for Delivery")
        print("  [3] 113-5544332-9988776 | Nike Pegasus Running Shoes   | Ready at Amazon Locker")
        print("  [4] 111-7788990-1122334 | Apple iPad Air 11-inch M2    | Preparing for Shipment")
        print("  [5] 115-4433221-5566778 | De'Longhi Espresso Machine   | Customs Clearance Hold")
        print("  [6] 116-2233445-6677889 | The North Face Winter Jacket | Delivered to Porch")
        print("  [7] 117-6655443-2211009 | Lego Millennium Falcon       | Returned & Refunded")
        print("  [8] 118-9900112-3344556 | Anker 100W Fast Charger      | Same-Day Delivery")
        print("="*75)
        print("💡 Ask anything! E.g.:")
        print("   - 'Where is my Kindle?' or 'Where are my shoes?'")
        print("   - 'Why is my delivery delayed?' -> Prompts to pick an order")
        print("   - 'What orders do I have?' -> Shows all orders in memory")
        print("   - 'I want to talk about a different order' -> Clears and switches order")
        print("   - Or paste any 17-digit Order ID directly.")
        print("="*75 + "\n")

        while True:
            try:
                q = input("Customer: ").strip()
                if not q:
                    continue
                if q.lower() in ["exit", "quit", "q"]:
                    print("\nThank you for contacting Amazon Support. Goodbye!")
                    break
                run_agentic_query(q)
            except (KeyboardInterrupt, EOFError):
                print("\n\nThank you for contacting Amazon Support. Goodbye!")
                break
