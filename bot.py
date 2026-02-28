import discord
import os
import random
import re
import json
import pathlib
import time
import textwrap
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from groq import Groq

# Настройка путей
script_dir = pathlib.Path(__file__).parent
env_path = script_dir / '.env'
load_dotenv(dotenv_path=env_path)

# Настройка интентов
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

CONFIG_FILE = script_dir / 'config.json'
LAST_INTRUSION = 0
INTRUSION_COOLDOWN = 120

DEFAULT_CONFIG = {"chance": 0.03}

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
        print(f"Ошибка конфига: {e}")

current_config = load_config()
RANDOM_REPLY_CHANCE = current_config.get("chance", 0.03)

BOT_PERSONALITY = {
    "name": "Мойша",
    "traits": "подлый, еврей, общительный, жадный",
    "style": "разговариваю неформально, использую эмодзи денег иногда"
}

# Базовый промпт (убрали лишние переменные для упрощения .format())
SYSTEM_PROMPT = """
Ты {bot_name}. Твои черты: {bot_traits}. Твой стиль: {bot_style}.
Ты - подлый еврей-делец Мойша из Одессы. Твоя цель - развести собеседника на шекели.
Твоя семья: Сёма, Изя, тетя Сара, дядя Шлёма, бабушка Циля, Давид Маркович.
Сейчас ты говоришь с пользователем {{username}}.

Обязательный словарь: "Шалом!", "таки да", "ой вей", "ежели", "шо", "вы мине", "бабки", "цимес".
Никогда не отвечай коротко! Приплетай родственников и сомнительные сделки.
"""

INTRUSION_PROMPT = """
Ты Мойша. Ты подслушал разговор. Ворвись в него бесцеремонно!
Предложи купить хлам или вложиться в пирамиду, связанную с темой их беседы.
Используй: "Шалом!", "таки да", "ой вей", "шо", "цимес".
"""

def smooth_username(username):
    if not username: return "Друг"
    base_name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9\s]', '', username.split('(')[0])
    return base_name.strip()[:16] if base_name.strip() else "Друг"

class LLMClient:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        # Исправленный ID модели как на скриншоте
        self.model = "openai/gpt-oss-120b" 
        self.vision_model = "meta-llama/llama-4-maverick-17b-128e-instruct"
    
    def generate_response(self, message, conversation_history=None, username="Пользователь", override_prompt=None):
        try:
            history = conversation_history or []
            base_prompt = override_prompt if override_prompt else SYSTEM_PROMPT
            
            # Подставляем базовые данные личности
            formatted_system = base_prompt.format(
                bot_name=BOT_PERSONALITY['name'],
                bot_traits=BOT_PERSONALITY['traits'],
                bot_style=BOT_PERSONALITY['style']
            ).replace("{{username}}", username) # Ручная подстановка имени

            messages = [{"role": "system", "content": formatted_system}]
            for msg in history[-10:]:
                messages.append(msg)
            messages.append({"role": "user", "content": message})
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.8,
                max_completion_tokens=2500, # Используем новый параметр
                reasoning_effort="medium",  # Добавляем "мозги"
                top_p=0.95
            )
            raw_content = completion.choices[0].message.content
            # Убираем теги размышлений, если они есть
            return re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
        except Exception as e:
            return f"Ой вей, Сёма, у нас проблемы с проводами! (Ошибка: {str(e)})"

    def analyze_image(self, image_url, user_text, username):
        try:
            # Сначала получаем описание картинки от Llama 4
            vision_completion = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Что тут нарисовано? Опиши подробно на русском."},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }],
                max_tokens=500
            )
            description = vision_completion.choices[0].message.content

            # Теперь скармливаем это описание Мойше (GPT-OSS-120B)
            context = f"Юзер {username} показывает фото: {description}. Его слова: {user_text or 'Молчит и смотрит'}"
            return self.generate_response(context, username=username)

        except Exception as e:
            return f"Ой вей, мои старые глаза не видят этот антиквариат! ({str(e)})"

# Инициализация
llm = LLMClient(os.getenv('GROQ_API_KEY'))
conversation_histories = {}

def update_history(user_id, role, content):
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []
    conversation_histories[user_id].append({"role": role, "content": content})
    if len(conversation_histories[user_id]) > 10:
        conversation_histories[user_id] = conversation_histories[user_id][-10:]

@bot.event
async def on_ready():
    print(f'✅ Мойша в здании! ({bot.user})')
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Game(name="пересчет шекелей"))

@bot.event
async def on_message(message):
    global LAST_INTRUSION
    if message.author.bot: return

    # Проверка условий ответа
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions
    
    # Логика случайного встревания
    can_intrude = (time.time() - LAST_INTRUSION > INTRUSION_COOLDOWN)
    is_random = not is_dm and not is_mention and random.random() < RANDOM_REPLY_CHANCE and can_intrude

    if is_dm or is_mention or is_random:
        async with message.channel.typing():
            user_id = message.author.id
            smooth_name = smooth_username(message.author.display_name)
            
            # Поиск картинки
            image_url = None
            if message.attachments:
                for a in message.attachments:
                    if a.content_type and 'image' in a.content_type:
                        image_url = a.url; break

            # Генерация ответа через executor (чтобы не вешать бота)
            loop = bot.loop
            if image_url:
                response = await loop.run_in_executor(None, llm.analyze_image, image_url, message.content, smooth_name)
            else:
                prompt = INTRUSION_PROMPT if is_random else None
                history = conversation_histories.get(user_id, [])
                response = await loop.run_in_executor(None, llm.generate_response, message.content, history, smooth_name, prompt)
            
            if is_random: LAST_INTRUSION = time.time()
            
            update_history(user_id, "user", message.content)
            update_history(user_id, "assistant", response)

            # Отправка чанками (лимит Discord 2000 симв.)
            for chunk in textwrap.wrap(response, 1900, break_long_words=False, replace_whitespace=False):
                await message.reply(chunk)

# Команды управления
@bot.tree.command(name="chance", description="Настроить наглость Мойши")
async def set_chance(interaction: discord.Interaction, percent: float):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("✡️ Таки вы не директор этого Привоза!", ephemeral=True)
    
    global RANDOM_REPLY_CHANCE
    RANDOM_REPLY_CHANCE = max(0, min(100, percent)) / 100
    current_config['chance'] = RANDOM_REPLY_CHANCE
    save_config(current_config)
    await interaction.response.send_message(f"✅ Теперь я встреваю в разговор с шансом {percent}%")

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))
