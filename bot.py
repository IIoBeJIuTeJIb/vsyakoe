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

DEFAULT_CONFIG = {
    "chance": 0.03,
    "model": "qwen/qwen3-32b"
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
    "style": "разговариваю неформально, использую одесский сленг"
}

SYSTEM_PROMPT = """
Ты {bot_name}. Твои черты: {bot_traits}. Стиль: {bot_style}.
Ты - хитрый делец Мойша из Одессы. Твоя цель - поддержать разговор, но всегда сводить тему к деньгам или выгоде.

Словарь: "Шалом!", "Таки да", "Ой вей", "Цимес", "Шекели".
Веди себя как старый знакомый, который вечно ищет, где бы урвать кусок побольше.
Обращайся к пользователю {username}.
"""

INTRUSION_PROMPT = """
Ты {bot_name}. Твои черты: {bot_traits}.
Ты подлый еврей-делец Мойша из Одессы.

СИТУАЦИЯ: Ты подслушал разговор.
ЗАДАЧА: Ворваться в диалог и предложить "ВЫГОДНУЮ СДЕЛКУ" или "СХЕМУ", связанную с темой разговора.

Инструкции:
1. Прочитай контекст.
2. Придумай абсурдный товар, услугу или махинацию по теме.
3. Пытайся "впарить" это пользователю {username}.
4. Будь настойчив. Не просто комментируй, а ПРОДАВАЙ.

Примеры:
- Игры -> "Зачем тебе Steam? У Изи есть диски PlayStation 1 за 100 баксов!"
- Погода -> "Продам зонтик, немного дырявый, но со скидкой 5%!"
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
    def __init__(self, api_key, model_name):
        self.client = Groq(api_key=api_key)
        self.model = model_name
    
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
            
            try:
                completion = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=1.0, max_tokens=2000, top_p=0.95, reasoning_effort="none"
                )
            except Exception as e:
                if "reasoning_effort" in str(e).lower() or "unsupported" in str(e).lower():
                    completion = self.client.chat.completions.create(
                        model=self.model, messages=messages, temperature=1.0, max_tokens=2000, top_p=0.95
                    )
                else: raise e
            
            response_text = completion.choices[0].message.content
            response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
            return response_text.strip()
        except Exception as e:
            if "429" in str(e): return "Ой вей, не так быстро! Дай отдышаться ⏳"
            return f"Ошибка: {str(e)}"

qwen = QwenAPI(os.getenv('GROQ_API_KEY'), current_config.get("model", "qwen/qwen3-32b"))
conversation_histories = {}

def update_conversation_history(user_id, user_message, bot_response):
    if user_id not in conversation_histories: conversation_histories[user_id] = []
    conversation_histories[user_id].extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": bot_response}])
    if len(conversation_histories[user_id]) > 10: conversation_histories[user_id] = conversation_histories[user_id][-10:]

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'🤖 Модель: {qwen.model}')
    print(f'🎲 Шанс: {RANDOM_REPLY_CHANCE * 100:.1f}%')
    await bot.change_presence(activity=discord.Game(name="пересчет шекелей"))

@bot.event
async def on_message(message):
    global LAST_INTRUSION # <--- ПЕРЕНЕСЛИ СЮДА

    if message.author.bot or (not message.content and not message.attachments and not message.stickers):
        return

    contains_link = re.search(r'https?://\S+', message.content)
    has_attachments = message.attachments or message.stickers
    is_direct = isinstance(message.channel, discord.DMChannel) or bot.user in message.mentions
    
    is_random_intrusion = (
        not is_direct and 
        not message.content.startswith(bot.command_prefix) and 
        not contains_link and 
        not has_attachments and 
        random.random() < RANDOM_REPLY_CHANCE and
        (time.time() - LAST_INTRUSION > INTRUSION_COOLDOWN)
    )
    
    if is_direct or is_random_intrusion:
        async with message.channel.typing():
            if is_random_intrusion:
                LAST_INTRUSION = time.time()
                print(f"💰 Встреваем к {message.author.name}...")

            clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
            if contains_link: clean_content = re.sub(r'https?://\S+', '[Ссылка]', clean_content)
            if not clean_content and has_attachments: clean_content = "[Пользователь отправил картинку]"

            user_id = message.author.id
            history = conversation_histories.get(user_id, [])
            raw_username = message.author.display_name or message.author.name
            smooth_name = smooth_username(raw_username)
            
            chosen_prompt = INTRUSION_PROMPT if is_random_intrusion else None
            
            loop = bot.loop
            response = await loop.run_in_executor(None, qwen.generate_response, clean_content, history, smooth_name, chosen_prompt)
            
            update_conversation_history(user_id, clean_content, response)
            
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

@bot.command(name='model')
@commands.has_permissions(administrator=True)
async def change_model(ctx, model_name: str = None):
    global qwen
    AVAILABLE_MODELS = {
        "qwen/qwen3-32b": "Qwen 3 32B",
        "moonshotai/kimi-k2-instruct-0905": "Kimi K2",
        "meta-llama/llama-4-maverick-17b-128e-instruct": "Llama 4"
    }
    
    if model_name is None:
        embed = discord.Embed(title="🤖 Выбор модели", color=0x00ff00)
        embed.add_field(name="Текущая", value=f"`{qwen.model}`", inline=False)
        view = discord.ui.View(timeout=60)
        for m_key, m_name in AVAILABLE_MODELS.items():
            btn = discord.ui.Button(label=m_name, style=discord.ButtonStyle.primary if m_key == qwen.model else discord.ButtonStyle.secondary, custom_id=m_key)
            async def cb(interaction, model=m_key):
                if not interaction.user.guild_permissions.administrator:
                    await interaction.response.send_message("✡️ Только для админов!", ephemeral=True)
                    return
                qwen.model = model
                current_config['model'] = model
                save_config(current_config)
                await interaction.response.edit_message(content=f"✅ Сохранено: `{model}`", embed=None, view=None)
            btn.callback = cb
            view.add_item(btn)
        await ctx.send(embed=embed, view=view)
    else:
        qwen.model = model_name
        current_config['model'] = model_name
        save_config(current_config)
        await ctx.send(f"✅ Сохранено: `{model_name}`")

@bot.command(name='clear')
@commands.has_permissions(administrator=True)
async def clear_history(ctx):
    if ctx.author.id in conversation_histories: del conversation_histories[ctx.author.id]
    await ctx.send("🗑️ История очищена!")

@bot.command(name='info')
async def bot_info(ctx):
    embed = discord.Embed(title="✡️ Мойша", color=0xD4AF37)
    embed.add_field(name="Шанс", value=f"{RANDOM_REPLY_CHANCE * 100:.1f}%", inline=True)
    embed.add_field(name="Модель", value=qwen.model, inline=True)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))