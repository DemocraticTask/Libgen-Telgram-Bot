import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from libgen_api_enhanced import LibgenSearch
from tabulate import tabulate
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import tempfile
import shutil
from telegram.error import BadRequest

# Configure logging to output to both console and file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()  # Outputs logs to console in real-time
    ]
)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")
BOT_USERNAME = os.getenv("BOT_USERNAME")  # e.g., @LibgenBot
if not BOT_USERNAME:
    raise ValueError("BOT_USERNAME not set in environment variables")
LIBGEN_MIRRORS = os.getenv("LIBGEN_MIRRORS", "gs").split(",")
EXPIRY_MINUTES = int(os.getenv("RESULT_EXPIRY_MINUTES", "10"))
MAX_QUERY_LENGTH = 100
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))  # Telegram bot file size limit
TEMP_DIR = os.getenv("TEMP_DIR", tempfile.gettempdir())  # Temporary directory for downloads
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "10"))  # Limit number of search results

# Ensure temporary directory exists
os.makedirs(TEMP_DIR, exist_ok=True)

# Store search results per user and chat with timestamps
user_search_results = {}  # {(user_id, chat_id): (results, timestamp)}

def cleanup_old_results():
    """Remove expired user search results."""
    now = datetime.now()
    for key in list(user_search_results.keys()):
        results, timestamp = user_search_results[key]
        if now - timestamp > timedelta(minutes=EXPIRY_MINUTES):
            user_id, chat_id = key
            logging.info(f"Cleaning up expired results for user {user_id} in chat {chat_id}")
            del user_search_results[key]

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uncaught errors and notify the user."""
    error = context.error
    logging.error(f"Update {update} caused error {error}")
    if update and update.message:
        if isinstance(error, BadRequest) and "Message is too long" in str(error):
            await update.message.reply_text(
                "Search results are too long to display. Please refine your query or try a more specific search term.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                "An error occurred. Please try again or contact support.",
                parse_mode="HTML"
            )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    logging.info(f"User {update.message.from_user.id} sent /start in chat {update.message.chat_id}")
    await update.message.reply_text(
        "📚 Welcome to Book Search Bot!\n\n"
        "🔍 How to search a book:\n"
        "➡️ Type: /search [book name]\n"
        "Example: /search Pride and Prejudice\n"
        "Note: Use correct spelling for better serach.\n"
        "⏳ Wait for a minute for results.\n\n"
        "📖 You will see a list of books with Book IDs.\n"
        "➡️ To get a book, just send the Book ID.\n"
        "Example: 5000278\n\n"
        f"✅ You will then receive the file instantly! (max {MAX_FILE_SIZE_MB} MB)",
        parse_mode="HTML"
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command to find books."""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    # Extract query, accounting for @BotUsername prefix
    command_text = update.message.text
    query = " ".join(context.args).strip()
    if not query and command_text.startswith(BOT_USERNAME):
        # Remove @BotUsername and /search to get query
        query = command_text[len(BOT_USERNAME + " /search"):].strip()

    # Validate query
    if not query:
        await update.message.reply_text("Please provide a book name after /search", parse_mode="HTML")
        return
    if len(query) > MAX_QUERY_LENGTH:
        await update.message.reply_text(
            f"Query is too long. Maximum length is {MAX_QUERY_LENGTH} characters.",
            parse_mode="HTML"
        )
        return
    if not re.match(r"^[a-zA-Z0-9\s\-\.,'\"()]+$", query):
        await update.message.reply_text("Invalid query. Use alphanumeric characters and basic punctuation.", parse_mode="HTML")
        return

    # Try each mirror
    results = None
    for mirror in LIBGEN_MIRRORS:
        try:
            s = LibgenSearch(mirror=mirror.strip())
            results = s.search_default(query)
            logging.info(f"User {user_id} searched for '{query}' in chat {chat_id} using mirror {mirror}")
            break
        except requests.exceptions.RequestException as e:
            logging.warning(f"Mirror {mirror} failed: {e}")
            continue
        except Exception as e:
            logging.error(f"Unexpected error with mirror {mirror}: {e}")
            continue

    if not results:
        await update.message.reply_text(
            f"No books found for query: {query} (all mirrors failed)",
            parse_mode="HTML"
        )
        return

    # Limit results to MAX_SEARCH_RESULTS
    results = results[:MAX_SEARCH_RESULTS]
    truncated = len(results) < len(s.search_default(query))  # Check if results were truncated

    # Store results with timestamp, keyed by (user_id, chat_id)
    user_search_results[(user_id, chat_id)] = (results, datetime.now())
    cleanup_old_results()

    # Prepare table data with sanitized titles
    table_data = [
        [book.id, (book.title if book.title else "N/A").replace("<", "&lt;").replace(">", "&gt;"), book.author, book.year, book.extension]
        for book in results
    ]
    headers = ["ID", "Title", "Author", "Year", "Extension"]

    # Format table and send
    table = tabulate(table_data, headers=headers, tablefmt="grid")
    message = f"<b>Search Results for '{query}' (showing up to {MAX_SEARCH_RESULTS}):</b>\n<pre>{table}</pre>\n"
    if truncated:
        message += f"More results were found. Refine your query to see others.\n"
    message += "Please reply with the ID of the book to download."
    await update.message.reply_text(message, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages to select a book by ID and send the file."""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    selected_id = update.message.text.strip()

    # Validate book ID
    if not re.match(r"^[a-zA-Z0-9_-]+$", selected_id):
        await update.message.reply_text("Invalid book ID format.", parse_mode="HTML")
        return

    # Check if user has search results in this chat
    if (user_id, chat_id) not in user_search_results:
        await update.message.reply_text(f"Please run /search or {BOT_USERNAME} /search first.", parse_mode="HTML")
        return

    results, _ = user_search_results[(user_id, chat_id)]
    selected_book = next((book for book in results if book.id == selected_id), None)

    if not selected_book:
        await update.message.reply_text(f"No book found with ID {selected_id}", parse_mode="HTML")
        logging.warning(f"User {user_id} provided invalid book ID {selected_id} in chat {chat_id}")
        return

    try:
        # Resolve download link
        selected_book.resolve_direct_download_link()
        if not selected_book.resolved_download_link:
            await update.message.reply_text(
                f"Failed to resolve download link for book ID {selected_id}",
                parse_mode="HTML"
            )
            logging.warning(f"Failed to resolve download link for book ID {selected_id} in chat {chat_id}")
            return

        # Download the file
        response = requests.get(selected_book.resolved_download_link, stream=True)
        response.raise_for_status()

        # Check file size
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_FILE_SIZE_MB * 1024 * 1024:
            await update.message.reply_text(
                f"File is too large (>{MAX_FILE_SIZE_MB} MB). Cannot send via Telegram.",
                parse_mode="HTML"
            )
            logging.warning(f"File for book ID {selected_id} exceeds {MAX_FILE_SIZE_MB} MB in chat {chat_id}")
            return

        # Determine file extension for saving
        file_ext = selected_book.extension.lower() if selected_book.extension else "bin"
        file_name = f"{selected_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_ext}"
        temp_file_path = os.path.join(TEMP_DIR, file_name)

        # Save file to temporary location
        with open(temp_file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logging.info(f"Downloaded file for book ID {selected_id} to {temp_file_path} for chat {chat_id}")

        # Use book ID for file name and caption if title is None or empty
        book_title = (selected_book.title or selected_id).replace("<", "&lt;").replace(">", "&gt;")
        with open(temp_file_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"{book_title}.{file_ext}",
                caption=f"<b>{book_title}</b>",
                parse_mode="HTML"
            )
        logging.info(f"Sent file for book ID {selected_id} to user {user_id} in chat {chat_id}")

        # Clean up temporary file
        try:
            os.remove(temp_file_path)
            logging.info(f"Deleted temporary file {temp_file_path}")
        except Exception as e:
            logging.error(f"Failed to delete temporary file {temp_file_path}: {e}")

    except requests.exceptions.RequestException as e:
        await update.message.reply_text("Network error while downloading file.", parse_mode="HTML")
        logging.error(f"Network error for book ID {selected_id} in chat {chat_id}: {e}")
    except Exception as e:
        await update.message.reply_text(f"Error processing download: {e}", parse_mode="HTML")
        logging.error(f"Unexpected error for book ID {selected_id} in chat {chat_id}: {e}")

def main():
    """Main function to start the bot."""
    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Add handlers with updated filters
        application.add_handler(CommandHandler("start", start, filters=filters.Regex(rf"^(?:/start|{BOT_USERNAME}\s*/start)$")))
        application.add_handler(CommandHandler("search", search, filters=filters.Regex(rf"^(?:/search|{BOT_USERNAME}\s*/search)\s*(.*)$")))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)  # Add global error handler

        # Start the bot
        logging.info("Starting bot")
        application.run_polling()
    except KeyboardInterrupt:
        logging.info("Bot stopped gracefully")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()
