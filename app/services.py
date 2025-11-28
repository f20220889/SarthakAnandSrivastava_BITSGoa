import os
import google.generativeai as genai
from app.models import PageLineItems, BillItem
import json
import base64
from dotenv import load_dotenv

# Load environment variables to get the API Key
load_dotenv()

# Configure the Google AI library
# Make sure GOOGLE_API_KEY is in your .env file
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# System Prompt to guide the AI
# We ask it to be a strict JSON machine.
SYSTEM_PROMPT = """
You are an expert medical bill auditor. 
Your task is to extract line items from the provided bill image.

OUTPUT FORMAT:
You must return a strict JSON object following this schema exactly:
{
    "page_type": "Bill Detail" | "Final Bill" | "Pharmacy",
    "bill_items": [
        {
            "item_name": "string (exact text from bill)",
            "item_amount": float (net amount),
            "item_rate": float (unit cost),
            "item_quantity": float (count)
        }
    ]
}

RULES:
1. Extract every service, medicine, or charge listed.
2. "page_type": detect if this page is a detailed breakdown ("Bill Detail") or a summary page ("Final Bill").
3. "item_amount": This is the Total Amount for that line item.
4. If Rate or Quantity are missing, calculate them: (Amount = Rate * Quantity).
5. Do NOT include "Subtotal", "Total", "Discount", or "Tax" lines as bill items.
6. Return ONLY the JSON. Do not write "Here is the JSON" or markdown formatting.
"""

def extract_from_image(base64_image: str, page_num: int) -> tuple[PageLineItems, dict]:
    """
    Sends a base64 encoded image to Google Gemini 1.5 Flash and returns parsed data.
    """
    try:
        # 1. Initialize the Model
        # gemini-1.5-flash is free, fast, and good at reading text in images.
        model = genai.GenerativeModel('gemini-1.5-flash')

        # 2. Decode the Base64 string back to bytes
        image_bytes = base64.b64decode(base64_image)

        # 3. Generate Content
        # We send the image bytes and the prompt together
        response = model.generate_content([
            {'mime_type': 'image/jpeg', 'data': image_bytes},
            SYSTEM_PROMPT
        ])

        # 4. Clean the Response
        raw_text = response.text
        
        # Remove Markdown formatting if Gemini adds it (e.g., ```json ... ```)
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0]
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0]
        
        # Clean whitespace
        raw_text = raw_text.strip()

        # 5. Parse JSON
        data = json.loads(raw_text)

        # 6. Map to Pydantic Models (Safety Check)
        bill_items = []
        for item in data.get("bill_items", []):
            bill_items.append(BillItem(
                item_name=str(item.get("item_name", "Unknown Item")),
                # Ensure numbers are floats, default to 0.0 if missing
                item_amount=float(item.get("item_amount", 0.0)),
                item_rate=float(item.get("item_rate", 0.0)),
                item_quantity=float(item.get("item_quantity", 1.0))
            ))

        page_data = PageLineItems(
            page_no=str(page_num),
            page_type=data.get("page_type", "Bill Detail"),
            bill_items=bill_items
        )

        # 7. Extract Token Usage (for Cost tracking)
        # We allow usage_metadata to be None just in case, though usually it exists
        usage_meta = response.usage_metadata
        
        usage = {
            "total_tokens": usage_meta.total_token_count if usage_meta else 0,
            "prompt_tokens": usage_meta.prompt_token_count if usage_meta else 0,
            "completion_tokens": usage_meta.candidates_token_count if usage_meta else 0
        }

        return page_data, usage

    except json.JSONDecodeError:
        print(f"Error: Gemini returned invalid JSON on page {page_num}.")
        print(f"Raw Output: {raw_text[:100]}...") # Print start of output for debugging
        # Return empty data so the process continues
        return PageLineItems(page_no=str(page_num), page_type="Bill Detail", bill_items=[]), {}
        
    except Exception as e:
        print(f"Critical Error parsing page {page_num}: {str(e)}")
        return PageLineItems(page_no=str(page_num), page_type="Bill Detail", bill_items=[]), {}