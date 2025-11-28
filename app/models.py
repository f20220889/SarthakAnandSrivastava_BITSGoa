from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# --- Response Structures ---

class BillItem(BaseModel):
    item_name: str = Field(..., description="Exactly as mentioned in the bill")
    item_amount: float = Field(..., description="Net Amount of the item post discounts")
    item_rate: float = Field(..., description="Unit rate")
    item_quantity: float = Field(..., description="Quantity")

class PageLineItems(BaseModel):
    page_no: str
    page_type: Literal["Bill Detail", "Final Bill", "Pharmacy"] = Field(..., description="Type of page content")
    bill_items: List[BillItem]

class TokenUsage(BaseModel):
    total_tokens: int
    input_tokens: int
    output_tokens: int

class ExtractionData(BaseModel):
    pagewise_line_items: List[PageLineItems]
    total_item_count: int
    reconciled_amount: float

class APIResponse(BaseModel):
    is_success: bool
    token_usage: TokenUsage
    data: ExtractionData

# --- Request Structure ---

class ExtractRequest(BaseModel):
    document: str