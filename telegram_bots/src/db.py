from typing import Tuple

from utils import configure_logger

logger = configure_logger(__name__)


async def complete_task(db_pool, user_id, first_photo_path, second_photo_path):
    async with db_pool.acquire() as conn:
        await conn.execute(
            'UPDATE tasks SET status = $1 WHERE user_id = $2 AND first_source_photo_path = $3 AND second_target_file_path = $4',
            'completed', user_id, first_photo_path, second_photo_path
        )


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
