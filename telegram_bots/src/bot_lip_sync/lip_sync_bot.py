#!/usr/bin/env python
import html
import json
import logging
import traceback

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler, ConversationHandler, MessageHandler, filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Define conversation states
CHOOSE_PERSON, CHOOSE_LANGUAGE, INPUT_TEXT = range(3)

# Define reply keyboards
reply_keyboard_people = [['Elon Musk', 'Mark Zuckerberg', 'Bill Gates']]
reply_keyboard_languages = [['English', 'Spanish', 'Polish']]

TOTAL_VOTER_COUNT = 3

dotenv = dotenv_values(os.path.join("..", ".lip_sync_swap.env"))
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inform user about what this bot can do"""
    keyboard = [
        [InlineKeyboardButton("Elon Musk", callback_data="celeb Elon Musk")],
        [InlineKeyboardButton("Donald Trump", callback_data="celeb Donald Trump")],
        [InlineKeyboardButton("Vladimir Putin", callback_data="celeb Vladimir Putin")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose:", reply_markup=reply_markup)
    return CHOOSE_PERSON


async def handle_person(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    await query.edit_message_text(text=f"Selected option: {query.data}")
    keyboard = [
        [InlineKeyboardButton("English", callback_data="lang English")],
        [InlineKeyboardButton("Spanish", callback_data="lang Spanish")],
        [InlineKeyboardButton("Polish", callback_data="lang Polish")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please choose a language: ",
        reply_markup=reply_markup
    )
    return CHOOSE_LANGUAGE


async def handle_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()
    await query.edit_message_text(text=f"Selected language: {query.data}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please provide input text : ",
    )
    return INPUT_TEXT


async def handle_input_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received input text: %s", update.message.text)
    await update.message.reply_text(f"Received input text: {update.message.text}")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=context.error)
    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)

    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    await context.bot.send_message(
        chat_id='66395090', text=message, parse_mode=ParseMode.HTML
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display a help message"""
    await update.message.reply_text("Use /quiz, /poll or /preview to test this bot.")


def main() -> None:
    """Run bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(dotenv.get('TG_BOT_TOKEN')).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_PERSON: [
                CallbackQueryHandler(handle_person, pattern="^celeb"),
            ],
            CHOOSE_LANGUAGE: [
                CallbackQueryHandler(handle_language, pattern="^lang"),
            ],
            INPUT_TEXT: [
                MessageHandler(filters.TEXT, handle_input_text),
            ]
            # END_ROUTES: [
            #     CallbackQueryHandler(start_over, pattern="^" + str(ONE) + "$"),
            #     CallbackQueryHandler(end, pattern="^" + str(TWO) + "$"),
            # ],
        },
        fallbacks=[CommandHandler("start", start)],

    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_error_handler(error_handler)
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
