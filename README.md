# Telegram Book Search Bot

A Telegram bot for searching and downloading books using Libgen.

## Setup Instructions

1. **Clone the Repository**

   ```bash
   git clone https://github.com/DemocraticTask/Libgen-Telegram-Bot.git
   cd Libgen-Telgram-Bot
   ```

2. **Create a Virtual Environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   Note: `requirements.txt` installs the latest versions of dependencies. Test for compatibility.

4. **Set Up Environment Variables**

   - Copy the `.env.example` file to `.env`:

     ```bash
     cp .env.example .env
     ```
   - Edit `.env` with a text editor and provide the following values:
     - `BOT_TOKEN`: Your Telegram bot token from BotFather.
     - `BOT_USERNAME`: Your bot’s Telegram username (e.g., `@YourBotName`).
     - `LIBGEN_MIRRORS`: Comma-separated Libgen mirror codes (default: `gs`).
     - `RESULT_EXPIRY_MINUTES`: Time (in minutes) before search results expire (default: `10`).
     - `MAX_FILE_SIZE_MB`: Maximum file size for downloads in MB (default: `50`).
     - `TEMP_DIR`: Directory for temporary files (default: `/tmp` on Linux/Mac, `%TEMP%` on Windows).
     - `MAX_SEARCH_RESULTS`: Maximum number of search results to display (default: `10`).

5. **Run the Bot**

   ```bash
   python main.py
   ```

## Usage

- Start the bot: `/start`
- Search for a book: `/search book name` (e.g., `/search Pride and Prejudice`)
- Reply with the book ID (e.g., `5000278`) to download the file.

## Notes

- Bot uses Libgen_api_enhanced API from https://github.com/onurhanak/libgen-api-enhanced which is also in active development, which might break this program.
- There are currenlty a lot of Issues which i have identified but won't be continuing/developing/maintaing with the project.
- Ensure a stable internet connection for downloading files.
- The bot respects Telegram’s file size limit (default: 50 MB).
- Log files (`bot.log`) and temporary files are created in `TEMP_DIR` and excluded from the repository via `.gitignore`.
- Some times all mirrors maybe down.

If you encounter issues with package versions, consider pinning specific versions in `requirements.txt`.
