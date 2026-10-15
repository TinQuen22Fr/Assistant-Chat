import os

from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"], tz_aware=True)
db = client[os.environ["DB_NAME"]]


async def create_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.conversations.create_index([("user_id", 1), ("updated_at", -1)])
    await db.conversations.create_index("id", unique=True)
    await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await db.messages.create_index("id", unique=True)
    await db.files.create_index("id", unique=True)
    await db.files.create_index([("conversation_id", 1), ("user_id", 1)])
    await db.memories.create_index("id", unique=True)
    await db.memories.create_index([("user_id", 1), ("updated_at", -1)])
    await db.user_settings.create_index("user_id", unique=True)
    await db.messages.create_index([("user_id", 1), ("import_key", 1)], sparse=True)
    await db.import_jobs.create_index("id", unique=True)
