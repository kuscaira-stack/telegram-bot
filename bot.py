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
        "НАЗВАНИЕ: [Full product name with brand - clear and SEO-optimized]\n\n"
        "ОПИСАНИЕ: [Write a compelling expert-level product description covering ALL sections:\n"
        "PRODUCT OVERVIEW: 2-3 sentences that hook the customer. Highlight the hero benefit.\n"
        "KEY BENEFITS: 4-5 specific results-driven benefits using professional beauty language.\n"
        "KEY INGREDIENTS AND THEIR ACTION: Name star ingredients and explain what they do scientifically.\n"
        "SKIN TYPE: Specify which skin types this product is suitable for and why.\n"
        "TEXTURE AND SENSORY EXPERIENCE: Describe texture, scent, absorption, and finish.\n"
        "HOW TO USE: Clear step-by-step application instructions including frequency and pro tips.\n"
        "PRECAUTIONS: Warnings, patch test recommendation, keep away from eyes, etc.\n"
        "PRODUCT DETAILS: Volume, format, country of origin if visible.\n"
        "Write minimum 250 words total. Use professional beauty industry terminology.]\n\n"
        "ЦЕНА: [Suggest competitive retail price in EUR based on brand, product type and volume]\n\n"
        "ТЕГИ: [20 SEO-optimized tags in English: brand, product type, skin concern, skin type, "
        "key ingredients, key benefits, format - separated by commas]"
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
    for line in lines:
        if line.startswith('НАЗВАНИЕ:'):
            product_data['title'] = line.replace('НАЗВАНИЕ:', '').strip()
        elif line.startswith('ОПИСАНИЕ:'):
            product_data['description'] = line.replace('ОПИСАНИЕ:', '').strip()
        elif line.startswith('ЦЕНА:'):
            price_str = line.replace('ЦЕНА:', '').strip()
            price_str = ''.join(filter(lambda x: x.isdigit() or x == '.', price_str))
            product_data['price'] = price_str if price_str else '0'
        elif line.startswith('ТЕГИ:'):
            product_data['tags'] = line.replace('ТЕГИ:', '').strip()
    
    if 'title' in product_data:
        await create_shopify_product(update, product_data)
    else:
        await update.message.reply_text("Could not recognize the product. Please try another photo.")

async def create_shopify_product(update: Update, product_data: dict):
    await update.message.reply_text("Creating product in Shopify...")
    
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "product": {
            "title": product_data.get('title', 'New Product'),
            "body_html": product_data.get('description', ''),
            "tags": product_data.get('tags', ''),
            "variants": [
                {
                    "price": product_data.get('price', '0'),
                    "inventory_management": "shopify"
                }
            ],
            "status": "draft"
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 201:
        product = response.json()['product']
        product_id = product['id']
        product_url = f"https://{SHOPIFY_STORE}/admin/products/{product_id}"
        await update.message.reply_text(
            f"Product created in Shopify!\n"
            f"Title: {product_data.get('title')}\n"
            f"Price: {product_data.get('price')} EUR\n"
            f"Status: Draft\n"
            f"Link: {product_url}"
        )
    else:
        await update.message.reply_text(
            f"Error creating product: {response.status_code}\n{response.text}"
        )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
