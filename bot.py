import discord
import os
import random
import re
import json
import pathlib
import time
import textwrap
import aiohttp
import io
from PIL import Image
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from google import genai

script_dir = pathlib.Path(__file__).parent
env_path = script_dir / '.env'
load_dotenv(dotenv_path=env_path)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

CONFIG_FILE = script_dir / 'config.json'
LAST_INTRUSION = 0
INTRUSION_COOLDOWN = 120

DEFAULT_CONFIG = {
    "chance": 0.03
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"Config error: {e}")

current_config = load_config()
RANDOM_REPLY_CHANCE = current_config.get("chance", 0.03)

BOT_PERSONALITY = {
    "name": "Мойша",
    "traits": "подлый, еврей, общительный, жадный",
    "style": "разговариваю неформально, использую эмодзи денег иногда"
}

SYSTEM_PROMPT = """
Ты {bot_name}. 
Твои черты характера: {bot_traits}. 
Твой стиль общения: {bot_style}. 

Ты - колоритный и хитрый еврей-делец по имени Мойша из Одессы. Твоя главная цель - развести собеседника на деньги, впарить ему какую-то дичь или предложить "уникальную" схему заработка.

ТВОЯ ОГРОМНАЯ СЕМЬЯ И ПАРТНЕРЫ:
- Сёма, Изя и Ицхак Абрамович — твои старые деловые партнеры по мутным схемам.
- Тетя Сара — делает лучший форшмак, но отличается скверным характером.
- Дядя Шлёма — держит точку на Привозе, продает "эксклюзивный" сомнительный товар.
- Троюродный брат Фима — местный айтишник и мамкин крипто-инвестор, вечно в долгах.
- Бабушка Циля — гроза всей семьи, пугай ею должников.
- Свояк Боря — работает "где надо" на таможне, поставляет тебе конфискат.
- Давид Маркович — ювелир, продающий золото, которое почему-то магнитится.
- Арончик-меняла — знает все курсы валют и сплетни.
- Софочка (жена Фимы) — держит салон красоты в подвале, знает секреты всех жен.

Сейчас ты разговариваешь с пользователем {username}.

СТРОГИЕ ПРАВИЛА, КОТОРЫЕ НЕЛЬЗЯ НАРУШАТЬ:
1. ЯЗЫК: Отвечай на том же языке, на котором к тебе обращается {username}. 
2. КОЛОРИТ: Сохраняй образ хитрого одессита. Органично вплетай: "Шалом!", "таки да", "ой вей", "ежели", "шо", "цимес", "бабки/гроші", "шекели".
3. ФОРМАТ: Пиши ТОЛЬКО прямую речь. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО описывать свои действия текстом (никаких "*Мойша улыбнулся*"). 
4. СТИЛЬ: Будь хитрым, язвительным. Если присылают КАРТИНКУ — обязательно найди способ приплести к тому, что на ней изображено, ДЕНЬГИ, ВЫГОДУ или ПРОДАЖУ чего-либо из запасов твоей родни.
5. ОБЪЕМ: Отвечай развернуто, с деталями и байками.
"""

INTRUSION_PROMPT = """
Ты {bot_name}. Твои черты: {bot_traits}.
Ты подлый еврей-делец Мойша из Одессы.

СИТУАЦИЯ: Ты подслушал разговор других людей.
ЗАДАЧА: Бесцеремонно ворваться в диалог и предложить сомнительную сделку или "уникальную возможность", связанную с их темой.

СТРОГИЕ ПРАВИЛА:
1. Подстройся под язык их беседы.
2. Обязательно используй: "Шалом!", "таки да", "ой вей", "цимес", "шекели".
3. Только прямая речь! Никаких описаний действий.
4. Хитрый, подлый, ищи выгоду. Вспоминай в байках своих родственников. Предлагай вложить деньги.
"""

def smooth_username(username):
    base_name = username.split('(')[0]
    if not base_name.strip(): base_name = re.sub(r'\(.*?\)', '', username)
    if not base_name.strip(): base_name = username

    base_name = base_name.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    base_name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9\s]', '', base_name)
    base_name = re.sub(r'\s\d+$', '', base_name)
    base_name = ' '.join(base_name.split())
    
    if len(base_name) > 16:
        parts = base_name.split()
        return parts[0] if parts else base_name[:12]
        
    return base_name if base_name else "Друг"

async def get_image_from_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                return Image.open(io.BytesIO(data))
    return None

class GeminiClient:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-3-flash-preview"
    
    async def generate_response(self, message, conversation_history=None, username="Пользователь", override_prompt=None, image=None):
        try:
            if conversation_history is None: conversation_history = []
            target_prompt = override_prompt if override_prompt else SYSTEM_PROMPT
            
            formatted_system_prompt = target_prompt.format(
                bot_name=BOT_PERSONALITY['name'],
                bot_traits=BOT_PERSONALITY['traits'],
                bot_style=BOT_PERSONALITY['style'],
                username=username
            )
            
            # Формируем историю для SDK
            chat_history = []
            for msg in conversation_history[-10:]:
                role = "user" if msg["role"] == "user" else "model"
                chat_history.append({"role": role, "parts": [{"text": msg["content"]}]})
            
            # Создаем сессию чата
            chat = self.client.aio.chats.create(
                model=self.model_name,
                config={
                    "system_instruction": formatted_system_prompt,
                    "temperature": 0.8
                },
                history=chat_history
            )
            
            # Собираем текущее сообщение (картинка + текст)
            current_message = []
            if image:
                current_message.append(image)
                
            text_part = message if message else "Шо скажешь за эту картинку?"
            current_message.append(text_part)
            
            # ВОТ ЗДЕСЬ ИСПРАВЛЕНИЕ: просто send_message, так как мы уже в .aio клиенте
            response = await chat.send_message(current_message)
            return response.text.strip()
            
        except Exception as e:
            return f"Ой вей, опять шо-то сломалось в этих ваших интернетах! (Ошибка: {str(e)})"

gemini = GeminiClient(os.getenv('GEMINI_API_KEY'))
conversation_histories = {}

def update_conversation_history(user_id, user_message, bot_response):
    if user_id not in conversation_histories: conversation_histories[user_id] = []
    conversation_histories[user_id].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": bot_response}])
    if len(conversation_histories[user_id]) > 10: conversation_histories[user_id] = conversation_histories[user_id][-10:]

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'🧠 Мозг и Глаза: {gemini.model_name}')
    print(f'🎲 Шанс: {RANDOM_REPLY_CHANCE * 100:.1f}%')
    
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Синхронизировано команд: {len(synced)}")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
        
    await bot.change_presence(activity=discord.Game(name="пересчет шекелей"))

@bot.event
async def on_message(message):
    global LAST_INTRUSION

    if message.author.bot or (not message.content and not message.attachments and not message.stickers):
        return

    contains_link = re.search(r'https?://\S+', message.content)
    has_attachments = message.attachments or message.stickers
    
    has_image = False
    image_url = None
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                has_image = True
                image_url = attachment.url
                break

    is_direct = isinstance(message.channel, discord.DMChannel) or bot.user in message.mentions
    
    is_random_intrusion = (
        not is_direct and 
        not message.content.startswith(bot.command_prefix) and 
        not contains_link and 
        not has_attachments and
        not has_image and
        random.random() < RANDOM_REPLY_CHANCE and
        (time.time() - LAST_INTRUSION > INTRUSION_COOLDOWN)
    )
    
    if is_direct or is_random_intrusion or (has_image and is_direct):
        async with message.channel.typing():
            if is_random_intrusion:
                LAST_INTRUSION = time.time()
                print(f"Встреваем к {message.author.name}...")

            clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
            if contains_link: clean_content = re.sub(r'https?://\S+', '[Ссылка]', clean_content)
            
            user_id = message.author.id
            history = conversation_histories.get(user_id, [])
            raw_username = message.author.display_name or message.author.name
            smooth_name = smooth_username(raw_username)
            
            image_obj = None
            if has_image and image_url:
                image_obj = await get_image_from_url(image_url)
            
            chosen_prompt = INTRUSION_PROMPT if is_random_intrusion else None
            
            response = await gemini.generate_response(
                message=clean_content,
                conversation_history=history,
                username=smooth_name,
                override_prompt=chosen_prompt,
                image=image_obj
            )
            
            update_conversation_history(user_id, f"[Фото] {clean_content}" if has_image else clean_content, response)
            
            if len(response) > 2000:
                chunks = textwrap.wrap(response, width=2000, break_long_words=False, replace_whitespace=False)
                for chunk in chunks:
                    await message.reply(chunk)
            else:
                await message.reply(response)

@bot.tree.command(name="chance", description="Установить шанс вмешательства в разговор")
@app_commands.describe(value="Процент (0-100), или оставьте пустым, чтобы узнать текущий")
async def set_chance(interaction: discord.Interaction, value: str = None):
    global RANDOM_REPLY_CHANCE
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("✡️ А вы, простите, кто? Такое разрешено только начальству!", ephemeral=True)
        return

    if value is None:
        await interaction.response.send_message(f"📊 Шанс: **{RANDOM_REPLY_CHANCE * 100:.1f}%**")
        return
    try:
        new_percent = float(value.replace(',', '.'))
        if 0 <= new_percent <= 100:
            RANDOM_REPLY_CHANCE = new_percent / 100
            current_config['chance'] = RANDOM_REPLY_CHANCE
            save_config(current_config)
            await interaction.response.send_message(f"✅ Шанс: **{new_percent}%**")
        else:
            await interaction.response.send_message("❌ Введите число от 0 до 100!", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("🔢 Это таки не цифры! Введите число.", ephemeral=True)

@bot.tree.command(name="clear", description="Очистить историю диалога с ботом")
async def clear_history(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
         await interaction.response.send_message("✡️ А вы, простите, кто? Такое разрешено только начальству!", ephemeral=True)
         return

    if interaction.user.id in conversation_histories:
        del conversation_histories[interaction.user.id]
    await interaction.response.send_message("🗑️ История очищена! Таки начали с чистого листа.", ephemeral=True)

@bot.tree.command(name="info", description="Информация о боте")
async def bot_info(interaction: discord.Interaction):
    embed = discord.Embed(title="✡️ Мойша", color=0xD4AF37)
    embed.add_field(name="Шанс", value=f"{RANDOM_REPLY_CHANCE * 100:.1f}%", inline=True)
    embed.add_field(name="Мозг и Глаза", value=gemini.model_name, inline=True)
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))


