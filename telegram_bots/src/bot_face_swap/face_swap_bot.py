import asyncio
import os

import asyncpg
from dotenv import dotenv_values
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from db import block_unsubscribed, complete_task, fail_task, create_new_user, get_pending_tasks, create_new_task, start_processing_task
from utils import error_handler, configure_logger, run_subprocess, get_video_duration, is_image, is_video, is_image_doc, is_video_doc

LESS_THAN_15_SEC = 'The video must be shorter than 15 seconds. Please trim and send again.'
LESS_THAN_15_SEC_AND_200_MB = 'The video must be shorter than 15 seconds and less than 200 megabytes. Please trim and send again.'
_200_MB = 200 * 1024 * 1024
_5_MB = 5 * 1024 * 1024

dotenv = dotenv_values(os.path.join("..", "..", ".face_swap.env"))
USER_DIR = dotenv.get('USER_DIR')
logger = configure_logger(__name__)

FIRST_PHOTO, SECOND_PHOTO = range(2)

# Global variables to store the database pool and task queue
db_pool: asyncpg.pool.Pool = None
task_queue: asyncio.Queue = None


async def init_db(dotenv):
    global db_pool
    db_pool = await asyncpg.create_pool(dsn=dotenv.get('DATABASE_URL'))


async def load_pending_tasks(queue):
    tasks = []
    logger.info("Loading pending tasks")
    async with db_pool.acquire() as conn:
        rows = await get_pending_tasks(conn)
        for row in rows:
            task = (row['task_id'], row['user_id'], row['first_source_photo_path'], row['second_target_file_path'], row['result_file_path'])
            await queue.put(task)
            logger.info(f"Loaded task for user {row['user_id']}")
    logger.info(f"All pending tasks were loaded. {queue.qsize()} tasks in queue")
    return tasks


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_dir = await build_user_dir(update)
    os.makedirs(user_dir, exist_ok=True)
    logger.info(f"/start command received from {update.message.chat_id}")
    user_id = update.message.from_user.id
    async with db_pool.acquire() as conn:
        await create_new_user(conn, update, user_id)
        is_block, _ = await block_unsubscribed(update, conn, user_id)
        if is_block:
            return ConversationHandler.END
    await update.message.reply_text("Please send the 1st photo with face (this face will be in the result image):")
    return FIRST_PHOTO


async def build_user_dir(update):
    return os.path.join(USER_DIR, str(update.message.chat_id))


async def handle_1st_source_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_dir = await build_user_dir(update)
    if update.message.photo:
        # For compressed photo
        photo_file = await update.message.photo[-1].get_file()
        first_source_photo_path = os.path.join(user_dir, f"{update.message.photo[-1].file_unique_id}.jpg")
    elif is_image_doc(update):
        # For uncompressed photo
        if update.message.document.file_size > _5_MB:  # 5 MB limit
            await update.message.reply_text('The first photo must be less than 5 megabytes.')
            return FIRST_PHOTO
        photo_file = await update.message.document.get_file()
        first_source_photo_path = os.path.join(user_dir, f"{update.message.document.file_unique_id}.jpg")
    else:
        await update.message.reply_text('Please send a photo or an uncompressed image file.')
        return FIRST_PHOTO

    logger.info(f"Got 1 photo from {update.message.chat_id}")
    await photo_file.download_to_drive(first_source_photo_path)
    logger.info(f"Downloaded 1 file to {first_source_photo_path}")
    context.user_data['first_source_photo'] = first_source_photo_path
    await update.message.reply_text("Got it! Now, please send the 2nd photo with face (this face will be replaced in the final photo):")
    return SECOND_PHOTO


async def handle_target_2nd_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user_dir = os.path.join(USER_DIR, str(update.message.chat_id))
    if is_image(update):
        target_file = await update.message.photo[-1].get_file()
        second_target_file_path = os.path.join(user_dir, f"{update.message.photo[-1].file_unique_id}.jpg")
    elif is_image_doc(update):
        if update.message.document.file_size > _5_MB:  # 5 MB limit
            await update.message.reply_text('The second photo must be less than 5 megabytes.')
            return SECOND_PHOTO
        target_file = await update.message.document.get_file()
        second_target_file_path = os.path.join(user_dir, f"{update.message.document.file_unique_id}.jpg")
    elif update.message.document and is_video_doc(update):
        if update.message.document.file_size > _200_MB:  # 200 MB limit
            await update.message.reply_text(LESS_THAN_15_SEC_AND_200_MB)
            return SECOND_PHOTO
        target_file = await update.message.document.get_file()
        second_target_file_path = os.path.join(user_dir, f"{update.message.document.file_unique_id}.mp4")
        video_duration = await get_video_duration(second_target_file_path)
        if video_duration > 15:  # 15 seconds limit
            await update.message.reply_text(LESS_THAN_15_SEC)
            return SECOND_PHOTO
    elif is_video(update):
        target_file = await update.message.video.get_file()
        second_target_file_path = os.path.join(user_dir, f"{update.message.video.file_unique_id}.mp4")
        if update.message.video.file_size > _200_MB:  # 200 MB limit
            await update.message.reply_text(LESS_THAN_15_SEC_AND_200_MB)
            return SECOND_PHOTO
        video_duration = await get_video_duration(second_target_file_path)
        if video_duration > 15:  # 15 seconds limit
            await update.message.reply_text(LESS_THAN_15_SEC)
            return SECOND_PHOTO
    else:
        await update.message.reply_text("Received unknown file from you. Please provide correct data")
        return ConversationHandler.END
    logger.info(f"Got 2 photo from {update.message.chat_id}")
    await target_file.download_to_drive(second_target_file_path)
    logger.info(f"Downloaded 2 file to {second_target_file_path}")
    context.user_data['second_target_file'] = second_target_file_path
    async with db_pool.acquire() as conn:
        is_block, usage_count = await block_unsubscribed(update, conn, user_id)
        if is_block:
            return ConversationHandler.END

        result_file_path = os.path.join(user_dir, f'result_{usage_count + 1}.jpg')
        task_id = await create_new_task(conn, context, result_file_path, user_id)

        await conn.execute('UPDATE users SET usage_count = usage_count + 1 WHERE user_id = $1', user_id)

    await update.message.reply_text("Processing your result...\nThis may take a while")
    await task_queue.put((task_id, user_id, context.user_data['first_source_photo'], context.user_data['second_target_file'], result_file_path))
    return ConversationHandler.END


async def process_queue(app):
    while True:
        task_id, user_id, first_source_photo_path, second_target_file_path, result_file_path = await task_queue.get()
        logger.info(f"Processing task for user {user_id}")
        async with db_pool.acquire() as conn:
            await start_processing_task(conn, task_id)
            try:
                stdout = await perform_face_swap(first_source_photo_path, second_target_file_path, result_file_path)
                if 'No face in source path detected.' in stdout:
                    raise Exception('No face in the 1st photo detected.')
                await complete_task(conn, task_id)
                await app.bot.send_document(chat_id=user_id, document=open(result_file_path, "rb"))
                await app.bot.send_message(chat_id=user_id, text="Here's your result! /start to try again.")
                logger.info(f"Task completed for user {user_id}")
            except Exception as e:
                logger.info(f"Task failed for user {user_id}: {e}")
                await fail_task(conn, e, task_id)
                await app.bot.send_message(chat_id=user_id, text=f"Error: {e}\nRun /start to try again.")
            task_queue.task_done()


async def perform_face_swap(first_source_photo_path, second_target_file_path, result_file_path):
    command = [
        dotenv.get('FACE_SWAP_PYTHON'),
        dotenv.get('FACE_SWAP_RUNNER'),
        '--target', second_target_file_path,
        '--source', first_source_photo_path,
        '-o', result_file_path,
        '--execution-provider', 'cuda',
        '--keep-fps',
        '--output-video-quality', '1',
        '--frame-processor', 'face_swapper',
    ]
    command_str = '\n'.join(command)
    logger.info(f"Running command: {command_str}")
    stdout = await run_subprocess(command)
    logger.debug(f"Command output: {stdout}")
    return stdout


def prepare_application():
    application = Application.builder().token(dotenv.get('TG_BOT_TOKEN')).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FIRST_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_1st_source_photo)],
            SECOND_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.IMAGE | filters.VIDEO | filters.Document.VIDEO, handle_target_2nd_file)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_error_handler(error_handler)
    return application


async def async_main():
    application = prepare_application()
    async with application:
        await application.initialize()
        await application.start()
        await async_init(application)
        # await application.updater.start_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)
        _ = await application.updater.start_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)
        logger.info(f"Bot is started.")
        while True:
            await asyncio.sleep(1)
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


async def async_init(app):
    global db_pool, task_queue
    await init_db(dotenv)
    task_queue = asyncio.Queue()
    # Load pending tasks from database
    await load_pending_tasks(task_queue)
    asyncio.create_task(process_queue(app))


if __name__ == "__main__":
    asyncio.run(async_main())
