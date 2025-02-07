import telebot
import fitz  # PyMuPDF for PDFs
from PIL import Image, ImageDraw, ImageFont
import io
import os
from dotenv import load_dotenv
import csv
import pandas as pd
from docx import Document
from ebooklib import epub
import time

# Load the .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BOOKS_DIR = os.getenv("BOOKS_DIR")
LOG_FILE = "logs.csv"

bot = telebot.TeleBot(BOT_TOKEN)

# Ensure log file exists
if not os.path.exists(LOG_FILE):
    pd.DataFrame(columns=["Book Name", "Size (KB)", "Status"]).to_csv(LOG_FILE, index=False)


def log_status(book_name, size, status):
    """Logs the book processing status to a CSV file."""
    with open(LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([book_name, round(size / 1024, 2), status])


def get_text_first_page(file_path):
    """Reads the first few lines from TXT, EPUB, or DOCX and renders them as an image."""
    text = ""
    ext = file_path.split(".")[-1].lower()

    try:
        if ext == "txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = "".join(f.readlines()[:10])  # Read first 10 lines
        elif ext == "docx":
            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs[:5]])  # First 5 paragraphs
        elif ext == "epub":
            book = epub.read_epub(file_path)
            for item in book.get_items():
                if item.get_type() == 9:  # First chapter
                    text = item.get_body_content().decode("utf-8")[:500]  # First 500 chars
                    break
    except Exception as e:
        return None

    if not text.strip():
        return None

    img = Image.new("RGB", (800, 400), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 20)  # Use Arial if available
    except IOError:
        font = ImageFont.load_default()

    draw.text((10, 10), text, fill="black", font=font)

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    return img_byte_arr


def get_first_page_image(pdf_path):
    """Extracts first page of a PDF as an image."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        pix = page.get_pixmap()

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)

        return img_byte_arr
    except Exception as e:
        return None

def send_with_retry(file_path, file_name, file_size, chat_id, reply_to=None, retries=1, delay=5):
    """Retries sending a document if it times out."""
    attempt = 0
    while attempt < retries:
        try:
            with open(file_path, "rb") as book:
                bot.send_document(chat_id, book, reply_to_message_id=reply_to)
            return True  # Success
        except Exception as e:
            print(f"⚠️ Error sending {file_name}: {e}")
            attempt += 1
            time.sleep(delay)  # Wait before retrying

    bot.send_message(CHANNEL_ID, f"❌ Error sending file *{file_name}*, size *{file_size:.2f}MB*", parse_mode="Markdown")
    return False  # Failed after retries


@bot.message_handler(commands=['sendbooks'])
def send_books(message):
    books = [f for f in os.listdir(BOOKS_DIR) if os.path.isfile(os.path.join(BOOKS_DIR, f))]

    if not books:
        bot.send_message(message.chat.id, "No books found in the directory.")
        return

    for book_name in books:
        book_path = os.path.join(BOOKS_DIR, book_name)
        file_size = os.path.getsize(book_path) / (1024 * 1024)
        ext = book_name.split(".")[-1].lower()

        if ext == "pdf":
            img = get_first_page_image(book_path)
        else:
            img = get_text_first_page(book_path)

        if img:
            msg = bot.send_photo(CHANNEL_ID, img, caption=f"📖 *{book_name}* - First Page", parse_mode="Markdown")
        else:
            bot.send_message(CHANNEL_ID, f"❌ Error extracting first page of *{book_name}*", parse_mode="Markdown")
            msg = None

        # Send book with retry
        success = send_with_retry(book_path, book_name, file_size, CHANNEL_ID, reply_to=msg.message_id if msg else None)

        log_status(book_name, file_size, "Success" if success else "Error: Sending Failed")

bot.polling()
