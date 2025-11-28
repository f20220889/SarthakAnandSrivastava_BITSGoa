from fastapi import FastAPI, HTTPException, BackgroundTasks
from app.models import ExtractRequest, APIResponse, ExtractionData, TokenUsage
from app.utils import download_file, process_document
from app.services import extract_from_image
from dotenv import load_dotenv
import requests
import json

load_dotenv()

app = FastAPI(title="HackRx Bill Extractor (Webhook)")

def process_bill_and_send_webhook(document_url: str, webhook_url: str):
    """
    This function runs in the background.
    It does the heavy lifting and then POSTs the result to the webhook_url.
    """
    try:
        print(f"Background Task Started for: {document_url}")
        
        # 1. Download
        file_content = download_file(document_url)
        
        # 2. Convert to Images
        images = process_document(file_content, document_url)
        
        # 3. Process Pages
        pagewise_items = []
        total_usage = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0}
        
        for idx, img in enumerate(images):
            page_data, usage = extract_from_image(img, idx + 1)
            pagewise_items.append(page_data)
            
            total_usage["total_tokens"] += usage.get("total_tokens", 0)
            total_usage["input_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["output_tokens"] += usage.get("completion_tokens", 0)

        # 4. Reconciliation Logic
        has_details = any(p.page_type == "Bill Detail" for p in pagewise_items)
        final_line_items = []
        reconciled_total = 0.0
        
        for page in pagewise_items:
            if has_details and page.page_type == "Final Bill":
                continue
            final_line_items.append(page)
            for item in page.bill_items:
                reconciled_total += item.item_amount

        total_count = sum(len(p.bill_items) for p in final_line_items)

        # 5. Create the Result Object
        result_payload = APIResponse(
            is_success=True,
            token_usage=TokenUsage(**total_usage),
            data=ExtractionData(
                pagewise_line_items=final_line_items,
                total_item_count=total_count,
                reconciled_amount=round(reconciled_total, 2)
            )
        )

        # 6. SEND WEBHOOK (Call the user back)
        print(f"Sending data to webhook: {webhook_url}")
        response = requests.post(webhook_url, json=result_payload.model_dump())
        print(f"Webhook response: {response.status_code}")

    except Exception as e:
        print(f"Background Task Failed: {e}")
        # Optionally send a failure webhook here
        error_payload = {"is_success": False, "error": str(e)}
        requests.post(webhook_url, json=error_payload)

@app.post("/extract-bill-data")
async def extract_bill_data(request: ExtractRequest, background_tasks: BackgroundTasks):
    """
    Async Endpoint. Returns immediately, processes in background.
    """
    # Validate URL (Basic check)
    if not request.webhook_url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid webhook_url")

    # Add the processing function to the background queue
    background_tasks.add_task(
        process_bill_and_send_webhook, 
        request.document, 
        request.webhook_url
    )

    # Return immediate confirmation
    return {
        "message": "Request received. Processing started.",
        "status": "processing",
        "info": "Results will be sent to your webhook_url when ready."
    }