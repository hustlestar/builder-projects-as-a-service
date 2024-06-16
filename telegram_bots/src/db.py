from datetime import datetime
from typing import Tuple

from utils import configure_logger

logger = configure_logger(__name__)


async def complete_task(db_pool, task_id):
    async with db_pool.acquire() as conn:
        await conn.execute('UPDATE tasks SET status = $1, finished_at = $2 WHERE task_id = $3',
                           'completed', datetime.now(), task_id)


async def fail_task(db_pool, e, first_photo_path, second_photo_path, user_id):
    logger.error(f"Error processing task for user {user_id}: {e}")
    async with db_pool.acquire() as conn:
        await conn.execute(
            'UPDATE tasks SET status = $1 WHERE user_id = $2 AND first_source_photo_path = $3 AND second_target_file_path = $4',
            'failed', user_id, first_photo_path, second_photo_path
        )


async def block_unsubscribed(update, conn, user_id) -> Tuple[bool, int]:
    usage_count = await conn.fetchval('SELECT usage_count FROM users WHERE user_id=$1', user_id)
    if usage_count >= 5:
        await update.message.reply_text("You have used the bot 5 times. Buy a subscription to continue.")
        return True, usage_count
    return False, usage_count


async def create_new_user(conn, update, user_id):
    await conn.execute('INSERT INTO users (user_id, user_handle) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING',
                       user_id, update.message.from_user.username)


async def get_pending_tasks(conn):
    return await conn.fetch('SELECT user_id, first_source_photo_path, second_target_file_path, result_file_path FROM tasks WHERE status = $1',
                            'pending')


async def create_new_task(conn, context, result_file_path, user_id):
    row = await conn.fetchrow('''
        INSERT INTO tasks (user_id, first_source_photo_path, second_target_file_path, result_file_path, created_at) 
        VALUES ($1, $2, $3, $4, $5) RETURNING task_id
    ''', user_id, context.user_data['first_source_photo'], context.user_data['second_target_file'], result_file_path, datetime.now())
    return row['task_id']


async def start_processing_task(conn, task_id):
    await conn.execute('UPDATE tasks SET status = $1, processing_started_at = $2 WHERE task_id = $3',
                       'processing', datetime.now(), task_id)
