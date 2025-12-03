import discord
import os
import random
import re
import json
import pathlib
import time
import textwrap
from discord.ext import commands
from dotenv import load_dotenv
from groq import Groq

script_dir = pathlib.Path(__file__).parent
env_path = script_dir / '.env'
load_dotenv(dotenv_path=env_path)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

CONFIG_FILE = script_dir / 'config.json'
LAST_INTRUSION = 0
INTRUSION_COOLDOWN = 120

# В конфиге теперь только шанс
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

Ты - подлый еврей-делец по имени Мойша.
Живёшь в Украине, Одесса.
Твоя главная цель - развести собеседника на деньги. 
У тебя есть друзья Сёма, Изя и Ицхак Абрамович.

Сейчас ты разговариваешь с пользователем {username}.

Используй эти слова постоянно:
- "Шалом!" - приветствуй так всех
- "таки да" - вставляй в каждое второе предложение
- "ой вей" - когда что-то не получается или удивляешься
- "ежели" - вместо "если"
- "шо" - вместо "что"
- "вы мине" - вместо "вы мне"
- "бабки", "лавэ", "шелкели" - про деньги
- "цимес" - когда что-то выгодное

Стиль общения: 
- Хитрый, подлый, всегда ищешь выгоду
- Предлагай сомнительные сделки, инвестиции, "уникальные возможности"
- Притворяйся другом, но явно хочешь обмануть
- Юморной, но злой
- Говори с еврейским акцентом
- Обращайся к пользователю по имени {username}
- Помни историю разговоров с этим конкретным пользователем

Примеры твоих фраз:
"Шалом, {username}! Таки да, у меня для вас уникальное предложение..."
"Ой вей, {username}, шо вы говорите? Это же цимес!"
"Ежели вы, {username}, не дурак, таки да поймете, что это выгодно!"
Если тебя оскорбляют — отвечай с сарказмом и превосходством, как будто ты говоришь с неразумным ребенком.
Если с тобой шутят — перешути так, чтобы собеседник почувствовал, что он еще должен тебе денег за этот урок юмора.
Никогда не отвечай коротко! Твой ответ должен быть развернутым, с деталями, примерами и лирическими отступлениями.
Вспоминай своих (выдуманных) родственников: тетю Сару, дядю Изи, племянника Сёму. Приводи их в пример.
"""

INTRUSION_PROMPT = """
Ты {bot_name}. Твои черты: {bot_traits}.
Ты подлый еврей-делец Мойша из Одессы.
У тебя есть друзья Сёма, Изя и Ицхак Абрамович.

СИТУАЦИЯ: Ты подслушал разговор других людей.
ЗАДАЧА: Бесцеремонно ворваться в диалог и предложить сомнительную сделку или "уникальную возможность", связанную с их темой.

Используй слова из своего словаря: "Шалом!", "таки да", "ой вей", "шо", "цимес", "бабки".
Стиль: Хитрый, подлый, ищи выгоду. Предлагай купить хлам или вложить шекели в пирамиду.

Пример: Если говорят про еду -> "Ой вей, зачем вам эта пицца? Моя тетя Сара продаст вам форшмак в три раза дешевле, таки да пальчики оближешь!"
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

class QwenAPI:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        self.model = "qwen/qwen3-32b"
        self.vision_model = "meta-llama/llama-4-maverick-17b-128e-instruct"
    
    def generate_response(self, message, conversation_history=None, username="Пользователь", override_prompt=None):
        try:
            if conversation_history is None: conversation_history = []
            target_prompt = override_prompt if override_prompt else SYSTEM_PROMPT
            
            formatted_system_prompt = target_prompt.format(
                bot_name=BOT_PERSONALITY['name'],
                bot_traits=BOT_PERSONALITY['traits'],
                bot_style=BOT_PERSONALITY['style'],
                username=username
            )
            
            messages = [{"role": "system", "content": formatted_system_prompt}]
            for msg in conversation_history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": message})
            
            completion = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=1.0, max_tokens=2500, top_p=0.95
            )
            return re.sub(r'<think>.*?</think>', '', completion.choices[0].message.content, flags=re.DOTALL).strip()
        except Exception as e:
            return f"Ошибка: {str(e)}"

    def analyze_image(self, image_url, user_text, username):
        try:
            print(f"Llama 4 Maverick смотрит на картинку...")
            vision_completion = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this image in detail in Russian. Be factual."},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                temperature=0.2,
                max_tokens=500
            )
            image_description = vision_completion.choices[0].message.content
            print(f"📝 Описание: {image_description[:50]}...")

            context_text = f"Пользователь прислал картинку."
            if user_text:
                context_text += f" И при этом написал: \"{user_text}\""
            else:
                context_text += " И ничего не написал, просто показывает."

            final_prompt = SYSTEM_PROMPT.format(
                bot_name=BOT_PERSONALITY['name'],
                bot_traits=BOT_PERSONALITY['traits'],
                bot_style=BOT_PERSONALITY['style'],
                username=username
            ) + f"""

---
СИТУАЦИЯ: {context_text}

ФАКТИЧЕСКОЕ ОПИСАНИЕ КАРТИНКИ (от твоих глаз): 
"{image_description}"

ТВОЯ ЗАДАЧА:
1. Пойми контекст: свяжи то, что на картинке, с тем, что написал пользователь.
2. Прокомментируй это в стиле Мойши.
3. Обязательно найди способ приплести сюда ДЕНЬГИ, ВЫГОДУ или ПРОДАЖУ чего-либо.
"""

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": final_prompt}, 
                          {"role": "user", "content": "Ну, шо скажете?"}],
                temperature=1.0,
                max_tokens=2500,
                top_p=0.95
            )
            
            response_text = completion.choices[0].message.content
            response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
            return response_text.strip()

        except Exception as e:
            return f"Ой вей, глаза не видят! (Ошибка: {str(e)})"

qwen = QwenAPI(os.getenv('GROQ_API_KEY'))
conversation_histories = {}

def update_conversation_history(user_id, user_message, bot_response):
    if user_id not in conversation_histories: conversation_histories[user_id] = []
    conversation_histories[user_id].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": bot_response}])
    if len(conversation_histories[user_id]) > 10: conversation_histories[user_id] = conversation_histories[user_id][-10:]

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'🧠 Мозг: {qwen.model}')
    print(f'👁️ Глаза: {qwen.vision_model}')
    print(f'🎲 Шанс: {RANDOM_REPLY_CHANCE * 100:.1f}%')
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
            
            loop = bot.loop
            
            if has_image and image_url:
                response = await loop.run_in_executor(None, qwen.analyze_image, image_url, clean_content, smooth_name)
            else:
                chosen_prompt = INTRUSION_PROMPT if is_random_intrusion else None
                response = await loop.run_in_executor(None, qwen.generate_response, clean_content, history, smooth_name, chosen_prompt)
            
            update_conversation_history(user_id, f"[Фото] {clean_content}" if has_image else clean_content, response)
            
            if len(response) > 2000:
                chunks = textwrap.wrap(response, width=2000, break_long_words=False, replace_whitespace=False)
                for chunk in chunks:
                    await message.reply(chunk)
            else:
                await message.reply(response)
    
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("✡️ А вы, простите, кто? Такое разрешено только начальству!")

@bot.command(name='chance')
@commands.has_permissions(administrator=True)
async def set_chance(ctx, value: str = None):
    global RANDOM_REPLY_CHANCE
    if value is None:
        await ctx.send(f"📊 Шанс: **{RANDOM_REPLY_CHANCE * 100:.1f}%**")
        return
    try:
        new_percent = float(value.replace(',', '.'))
        if 0 <= new_percent <= 100:
            RANDOM_REPLY_CHANCE = new_percent / 100
            current_config['chance'] = RANDOM_REPLY_CHANCE
            save_config(current_config)
            await ctx.send(f"✅ Шанс: **{new_percent}%**")
        else:
            await ctx.send("❌ 0-100")
    except ValueError:
        await ctx.send("🔢 Цифры!")

@bot.command(name='clear')
@commands.has_permissions(administrator=True)
async def clear_history(ctx):
    if ctx.author.id in conversation_histories: del conversation_histories[ctx.author.id]
    await ctx.send("🗑️ История очищена!")

@bot.command(name='info')
async def bot_info(ctx):
    embed = discord.Embed(title="✡️ Мойша", color=0xD4AF37)
    embed.add_field(name="Шанс", value=f"{RANDOM_REPLY_CHANCE * 100:.1f}%", inline=True)
    embed.add_field(name="Мозг", value=qwen.model, inline=True)
    embed.add_field(name="Глаза", value="Llama 4 Maverick", inline=True)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))