import os
import logging
import anthropic
import requests
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Keys from environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN")

# Claude client
claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для создания товаров в Shopify.\n"
        "Отправь мне фото товара и я автоматически создам карточку товара!"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Фото получено! Анализирую...")
    
    # Get photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    
    # Download photo
    photo_bytes = await file.download_as_bytearray()
    photo_base64 = base64.standard_b64encode(photo_bytes).decode("utf-8")
    
    # Send to Claude
    message = claude_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
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
                        "text": """Ты помощник для интернет-магазина косметики Beauté Magasin.
                        Посмотри на это фото косметического продукта и создай карточку товара.
                        Ответь ТОЛЬКО в таком формате без лишнего текста:
                        НАЗВАНИЕ: [название товара]
                        ОПИСАНИЕ: [описание 2-3 предложения]
                        ЦЕНА: [предложи цену в EUR]
                        ТЕГИ: [теги через запятую]"""
                    }
                ],
            }
        ],
    )
    
    response_text = message.content[0].text
    await update.message.reply_text(f"Результат анализа:\n\n{response_text}")
    
    # Parse response
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
        await update.message.reply_text("Не удалось распознать товар. Попробуй другое фото.")

async def create_shopify_product(update: Update, product_data: dict):
    await update.message.reply_text("Создаю товар в Shopify...")
    
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-01/products.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "product": {
            "title": product_data.get('title', 'Новый товар'),
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
            f"✅ Товар создан в Shopify!\n"
            f"Название: {product_data.get('title')}\n"
            f"Цена: {product_data.get('price')} EUR\n"
            f"Статус: Черновик\n"
            f"Ссылка: {product_url}"
        )
    else:
        await update.message.reply_text(
            f"❌ Ошибка создания товара: {response.status_code}\n{response.text}"
        )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
