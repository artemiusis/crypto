from telethon import TelegramClient, events
import config
# створюєш сесію
api_id = 22423718        # свій api_id з https://my.telegram.org
api_hash = "ca25e46782c6f612e3f1d81fc6a268f3"
client = TelegramClient("userbot", api_id, api_hash)

# список груп, які слухати
SOURCE_CHATS = config.IDS  # id груп (можна дістати через @userinfobot або telethon)
# id або юзернейм бота/чату, куди пересилати
TARGET_CHAT = "@tester123124Bot"

@client.on(events.NewMessage(chats=SOURCE_CHATS))
async def handler(event):
    # пересилаємо повідомлення в бота
    await client.forward_messages(TARGET_CHAT, event.message)

print("Userbot running...")
client.start()
client.run_until_disconnected()

