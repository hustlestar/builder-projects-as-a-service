import asyncio
import os

import asyncpg
from dotenv import dotenv_values
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from db import complete_task, fail_task, block_unsubscribed
from utils import run_subprocess, error_handler, configure_logger

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
        rows = await conn.fetch('SELECT user_id, first_photo_path, second_photo_path, result_photo_path FROM tasks WHERE status = $1', 'pending')
        for row in rows:
            task = (row['user_id'], row['first_photo_path'], row['second_photo_path'], row['result_photo_path'])
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
        await conn.execute('INSERT INTO users (user_id, user_handle) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING', user_id, update.message.from_user.username)
        is_block, _ = await block_unsubscribed(update, conn, user_id)
        if is_block:
            return ConversationHandler.END
    await update.message.reply_text("Please send the 1st photo with face (this face will be in the result image):")
    return FIRST_PHOTO


async def build_user_dir(update):
    return os.path.join(USER_DIR, str(update.message.chat_id))


async def handle_first_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_dir = os.path.join(USER_DIR, str(update.message.chat_id))
    os.makedirs(user_dir, exist_ok=True)
    photo_file = await update.message.photo[-1].get_file()
    user_dir = await build_user_dir(update)
    logger.info(f"Got 1 photo from {update.message.chat_id}")
    first_photo_path = os.path.join(user_dir, f"{update.message.photo[-1].file_unique_id}.jpg")
    await photo_file.download_to_drive(first_photo_path)
    logger.info(f"Downloaded 1 file to {first_photo_path}")
    context.user_data['first_photo'] = first_photo_path
    await update.message.reply_text("Got it! Now, please send the 2nd photo with face (this face will be replaced in the final photo):")
    return SECOND_PHOTO


async def handle_second_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user_dir = os.path.join(USER_DIR, str(update.message.chat_id))
    photo_file = await update.message.photo[-1].get_file()
    logger.info(f"Got 2 photo from {update.message.chat_id}")
    second_photo_path = os.path.join(user_dir, f"{update.message.photo[-1].file_unique_id}.jpg")
    await photo_file.download_to_drive(second_photo_path)
    logger.info(f"Downloaded 2 file to {second_photo_path}")
    context.user_data['second_photo'] = second_photo_path
    async with db_pool.acquire() as conn:
        is_block, usage_count = await block_unsubscribed(update, conn, user_id)
        if is_block:
            return ConversationHandler.END

        result_photo_path = os.path.join(user_dir, f'result_{usage_count + 1}.jpg')
        await conn.execute('''
            INSERT INTO tasks (user_id, first_photo_path, second_photo_path, result_photo_path)
            VALUES ($1, $2, $3, $4)
        ''', user_id, context.user_data['first_photo'], context.user_data['second_photo'], result_photo_path)

        await conn.execute('UPDATE users SET usage_count = usage_count + 1 WHERE user_id = $1', user_id)

    await update.message.reply_text("Processing your result...\nThis may take a while")
    await task_queue.put((user_id, context.user_data['first_photo'], context.user_data['second_photo'], result_photo_path, update))
    return ConversationHandler.END


async def process_queue():
    while True:
        user_id, first_photo_path, second_photo_path, result_photo_path, update = await task_queue.get()
        logger.info(f"Processing task for user {user_id}")
        try:
            stdout = await perform_face_swap(first_photo_path, second_photo_path, result_photo_path)
            if 'No face in source path detected.' in stdout:
                raise Exception('No face in the 1st photo detected.')
            await complete_task(db_pool, user_id, first_photo_path, second_photo_path)
            await update.message.reply_photo(photo=open(result_photo_path, "rb"))
            await update.message.reply_text("Here's your result! /start to try again.")
        except Exception as e:
            await fail_task(db_pool, e, first_photo_path, second_photo_path, user_id)
            await update.message.reply_text(f"Error: {e}\n/start to try again.")
        task_queue.task_done()


async def perform_face_swap(first_photo_path, second_photo_path, result_photo_path):
    command = [
        dotenv.get('FACE_SWAP_PYTHON'),
        dotenv.get('FACE_SWAP_RUNNER'),
        '--target', second_photo_path,
        '--source', first_photo_path,
        '-o', result_photo_path,
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
            FIRST_PHOTO: [
                MessageHandler(filters.PHOTO, handle_first_photo),
            ],
            SECOND_PHOTO: [
                MessageHandler(filters.PHOTO, handle_second_photo),
            ],
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
        await async_init()
        # await application.updater.start_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)
        queue = await application.updater.start_polling(drop_pending_updates=False, allowed_updates=Update.ALL_TYPES)
        logger.info(f"Bot started.")
        while True:
            await asyncio.sleep(1)
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


async def async_init():
    global db_pool, task_queue
    await init_db(dotenv)
    task_queue = asyncio.Queue()
    # Load pending tasks from database
    await load_pending_tasks(task_queue)
    asyncio.create_task(process_queue())


if __name__ == "__main__":
    asyncio.run(async_main())
