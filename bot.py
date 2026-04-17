import os
import logging
import anthropic
import requests
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")

claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I am Beaute Magasin product creation bot.\n"
        "Send me a photo of a product and I will automatically create a product card in Shopify!"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photo received! Analyzing...")
    
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()
    photo_base64 = base64.standard_b64encode(photo_bytes).decode("utf-8")
    
    prompt = (
        "You are a senior beauty industry expert and e-commerce specialist with 15+ years of experience "
        "in luxury cosmetics retail. You combine deep knowledge of cosmetic chemistry, dermatology, and "
        "digital marketing to create product listings that convert browsers into buyers.\n\n"
        "Analyze this cosmetic product photo and create a complete professional product listing in English only.\n\n"
        "Reply ONLY in this exact format with no extra text:\n\n"
        "НАЗВАНИЕ: [Full product name with brand]\n\n"
        "ОПИСАНИЕ: [Write a compelling expert-level product description covering:\n"
        "PRODUCT OVERVIEW: 2-3 sentences that hook the customer.\n"
        "KEY BENEFITS: 4-5 specific results-driven benefits.\n"
        "KEY INGREDIENTS AND THEIR ACTION: Star ingredients and their effects.\n"
        "SKIN TYPE: Which skin types and why.\n"
        "TEXTURE AND SENSORY EXPERIENCE: Texture, scent, absorption, finish.\n"
        "HOW TO USE: Step-by-step application instructions.\n"
        "PRECAUTIONS: Warnings and safety information.\n"
        "PRODUCT DETAILS: Volume, format, country of origin.\n"
        "Minimum 250 words in English only.]\n\n"
        "ЦЕНА: [Retail price in EUR]\n\n"
        "ТЕГИ: [20 SEO tags in English separated by commas]"
    )
    
    message = claude_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": photo_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ],
            }
        ],
    )
    
    response_text = message.content[0].text
    await update.message.reply_text(f"Analysis result:\n\n{response_text}")
    
    lines = response_text.strip().split('\n')
    product_data = {}
    description_lines = []
    in_description = False
    
    for line in lines:
        if line.startswith('НАЗВАНИЕ:'):
            product_data['title'] = line.replace('НАЗВАНИЕ:', '').strip()
            in_description = False
        elif line.startswith('ОПИСАНИЕ:'):
            description_lines = [line.replace('ОПИСАНИЕ:', '').strip()]
            in_description = True
        elif line.startswith('ЦЕНА:'):
            in_description = False
            price_str = line.replace('ЦЕНА:', '').strip()
            price_str = ''.join(filter(lambda x: x.isdigit() or x == '.', price_str))
            product_data['price'] = price_str if price_str else '0'
        elif line.startswith('ТЕГИ:'):
            in_description = False
            product_data['tags'] = line.replace('ТЕГИ:', '').strip()
        elif in_description:
            description_lines.append(line)
    
    if description_lines:
        product_data['description'] = '\n'.join(description_lines)
    
    if 'title' in product_data:
        await create_shopify_product(update, product_data)
    else:
        await update.message.reply_text("Could not recognize the product. Please try another photo.")

async def create_shopify_product(update: Update, product_data: dict):
    await update.message.reply_text("Creating product in Shopify...")
    
    query = """
    mutation productCreate($input: ProductInput!) {
      productCreate(input: $input) {
        product {
          id
          title
          handle
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    
    variables = {
        "input": {
            "title": product_data.get('title', 'New Product'),
            "bodyHtml": product_data.get('description', ''),
            "tags": product_data.get('tags', ''),
            "variants": [
                {
                    "price": product_data.get('price', '0'),
                }
            ],
            "status": "DRAFT"
        }
    }
    
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/graphql.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json"
    }
    
    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if 'errors' not in data and data.get('data', {}).get('productCreate', {}).get('product'):
            product = data['data']['productCreate']['product']
            product_id = product['id'].split('/')[-1]
            product_url = f"https://{SHOPIFY_STORE}/admin/products/{product_id}"
            await update.message.reply_text(
                f"✅ Product created in Shopify!\n"
                f"Title: {product_data.get('title')}\n"
                f"Price: {product_data.get('price')} EUR\n"
                f"Status: Draft\n"
                f"Link: {product_url}"
            )
        else:
            errors = data.get('data', {}).get('productCreate', {}).get('userErrors', [])
            error_msg = ', '.join([e.get('message', '') for e in errors]) if errors else str(data)
            await update.message.reply_text(f"❌ Error: {error_msg}")
    else:
        await update.message.reply_text(
            f"❌ Error creating product: {response.status_code}\n{response.text}"
        )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
