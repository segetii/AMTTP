from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def test():
    c = AsyncIOMotorClient('mongodb://localhost:27017', serverSelectionTimeoutMS=5000)
    await c.admin.command('ping')
    print('MongoDB OK via Motor')

asyncio.run(test())
