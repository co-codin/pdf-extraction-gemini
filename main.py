import os

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field

load_dotenv()

class BoundingBoxField(BaseModel):
    bounding_box: list[int] = Field(..., description='The bounding box where the information was found [y_min, x_min, y_max, x_max]')
    page: int = Field(..., description='Page number where the information was found. Start counting with 1.')

class TotalAmountField(BoundingBoxField):
    value: float = Field(..., description='The total amount of the invoice.')

class RecipientField(BoundingBoxField):
    name: str = Field(..., description='The name of the recipient.')

class TaxAmountField(BoundingBoxField):
    value: float = Field(..., description='The total amount of the tax.')

class SenderField(BoundingBoxField):
    name: str = Field(..., description='The name of the sender.')

class AccountNumberField(BoundingBoxField):
    account_no: str = Field(..., description='The number of the account.')


class InvoiceModel(BaseModel):
    total: TotalAmountField
    recipient: RecipientField
    tax: TaxAmountField
    sender: SenderField
    account_no: AccountNumberField

client = genai.Client(api_key=os.getenv("GEMENI_API_KEY"))


file_in = 'invoice.pdf'
file_out = 'invoice_annotated.pdf'
pdf = client.files.upload(file=file_in)

prompt = """
Extract the invoice recipient name and invoice total.
Return ONLY JSON that matches the provided schema.
If a field is missing, set it to null (and bounding_box to [0,0,0,0]).
"""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[pdf, prompt],
    config={
        "response_mime_type": "application/json",
        "response_schema": InvoiceModel
    },
)

invoice = InvoiceModel.model_validate_json(response.text)
print(invoice.model_dump())

