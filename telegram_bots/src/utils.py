import asyncio
import html
import json
import logging
import traceback

import httpx
import telegram
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


def configure_logger(name):
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
    )
    # set higher logging level for httpx to avoid all GET and POST requests being logged
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(name)


logger = configure_logger(__name__)


async def run_subprocess(command):
    """Run a subprocess command asynchronously."""
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        return stdout.decode()
    else:
        raise Exception(f"Subprocess failed with exit code {process.returncode}: {stderr.decode()}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Check if the error is an httpx.RemoteProtocolError
    if isinstance(context.error, (httpx.RemoteProtocolError, telegram.error.NetworkError)):
        return

    # Log the error before we do anything else
    logger.error("Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)

    # Build the message with some markup and additional information about what happened.
    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False)[:300])}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data)[:300])}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data)[:300])}</pre>\n\n"
        f"<pre>{html.escape(tb_string[:2800])}</pre>"
    )

    await context.bot.send_message(
        chat_id='66395090', text=message, parse_mode=ParseMode.HTML
    )


async def get_video_duration(file_path):
    from moviepy.editor import VideoFileClip
    clip = VideoFileClip(file_path)
    duration = clip.duration
    clip.close()
    return duration


def is_image(update):
    return bool(update.message.photo)


def is_video(update):
    return bool(update.message.video)


def is_video_or_image_doc(update):
    return is_video_doc(update) or is_image_doc(update)


def is_image_doc(update):
    return update.message.document and update.message.document.mime_type.startswith('image/')


def is_video_doc(update):
    return update.message.document and update.message.document.mime_type.startswith('video/')
