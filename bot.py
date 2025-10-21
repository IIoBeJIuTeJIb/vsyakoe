import discord
import aiohttp
import json
import os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Конфигурация личности бота
BOT_PERSONALITY = {
    "name": "Мойша",
    "traits": "подлый, еврей, общительный",
    "style": "разговариваю неформально, использую эмодзи денег иногда"
}

def smooth_username(username):
    """Сглаживает никнейм для более естественного обращения"""
    # Убираем содержимое в скобках
    import re
    cleaned = re.sub(r'\([^)]*\)', '', username)  # Убирает (Мурзик)(Шмурзик)
    
    # Убираем лишние символы
    cleaned = cleaned.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    
    # Берем только первое слово из ника (до пробела)
    first_part = cleaned.split()[0] if cleaned.strip() else username
    
    # Ограничиваем длину
    if len(first_part) > 12:
        first_part = first_part[:12]
    
    # Убираем цифры в конце если они есть
    if first_part and first_part[-1].isdigit():
        first_part = first_part.rstrip('0123456789')
    
    # Если после обработки ничего не осталось, возвращаем "друг"
    result = first_part.strip() if first_part.strip() else "друг"
    
    # Убираем возможные оставшиеся скобки
    result = result.replace('(', '').replace(')', '')
    
    return result

# Системный промпт для задания личности
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
В случае, если тебя как-то оскорбляют, можешь использовать мат. Редко, но метко.

"""

class GeminiAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-001:generateContent"
    
    async def generate_response(self, message, conversation_history=None, username="Пользователь"):
        try:
            if conversation_history is None:
                conversation_history = []
            
            # Форматируем системный промпт с именем пользователя
            formatted_system_prompt = SYSTEM_PROMPT.format(
                bot_name=BOT_PERSONALITY['name'],
                bot_traits=BOT_PERSONALITY['traits'],
                bot_style=BOT_PERSONALITY['style'],
                username=username
            )
            
            # Формируем сообщения для API
            messages = []
            
            # Добавляем системный промпт как первое сообщение
            messages.append({
                "role": "user",
                "parts": [{"text": formatted_system_prompt}]
            })
            messages.append({
                "role": "model", 
                "parts": [{"text": f"Хорошо, я понял свою роль. Сейчас я разговариваю с {username} и буду вести себя соответственно."}]
            })
            
            # Добавляем историю разговора
            for msg in conversation_history[-9:]:  # Берем последние 4.5 пары
                role = "user" if msg["role"] == "user" else "model"
                messages.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
            
            # Добавляем текущее сообщение
            messages.append({
                "role": "user",
                "parts": [{"text": message}]
            })
            
            headers = {
                "Content-Type": "application/json"
            }
            
            payload = {
                "contents": messages,
                "generationConfig": {
                    "temperature": 1,
                    "maxOutputTokens": 4000,
                    "topP": 0.95,
                    "topK": 0
                }
            }
            
            url = f"{self.base_url}?key={self.api_key}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'candidates' in data and len(data['candidates']) > 0:
                            return data['candidates'][0]['content']['parts'][0]['text']
                        else:
                            return "Извини, не смог обработать ответ от AI."
                    else:
                        error_text = await response.text()
                        
                        # Кастомные сообщения для разных ошибок
                        if response.status == 503:
                            return "Ой вей, вы меня нагрузили, дайте таки передохнуть! 🥵"
                        elif response.status == 429:
                            return "Ой вей, слишком много запросов! Подожди таки немного... ⏳"
                        elif response.status == 500:
                            return "Ай-ай-ай! Что-то сломалось на сервере! 🔧"
                        elif response.status == 403:
                            return "Ой, нет доступа! Проверь таки API ключ! 🔑"
                        else:
                            return f"Ошибка API {response.status}: {error_text}"
                        
        except Exception as e:
            return f"Произошла ошибка: {str(e)}"

# Инициализация API
gemini = GeminiAPI(os.getenv('GEMINI_API_KEY'))

# Хранилище истории разговоров
conversation_histories = {}

def update_conversation_history(user_id, user_message, bot_response):
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []
    
    # Добавляем новое взаимодействие
    conversation_histories[user_id].extend([
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": bot_response}
    ])
    
    # Ограничиваем историю последними 9 сообщениями
    if len(conversation_histories[user_id]) > 9:
        conversation_histories[user_id] = conversation_histories[user_id][-9:]

@bot.event
async def on_ready():
    print(f'Бот {bot.user} запущен!')
    await bot.change_presence(activity=discord.Game(name="синагоге"))

@bot.event
async def on_message(message):
    # Игнорируем сообщения от ботов и пустые сообщения
    if message.author.bot or not message.content:
        return
    
    # Отвечаем только когда бота упоминают или в личных сообщениях
    if isinstance(message.channel, discord.DMChannel) or bot.user in message.mentions:
        async with message.channel.typing():
            # Убираем упоминание из сообщения
            clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
            
            # Получаем историю разговора для этого канала
            user_id = message.author.id
            history = conversation_histories.get(user_id, [])
            
            # Генерируем ответ
            raw_username = message.author.display_name or message.author.name
            smooth_name = smooth_username(raw_username)
            response = await gemini.generate_response(clean_content, history, smooth_name)            
            
            # Обновляем историю
            update_conversation_history(user_id, clean_content, response)
            
            # Отправляем ответ
            if len(response) > 2000:
                chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                for chunk in chunks:
                    await message.reply(chunk)
            else:
                await message.reply(response)
    
    await bot.process_commands(message)

@bot.command(name='personality')
async def set_personality(ctx, *, personality_text):
    """Изменить личность бота"""
    global SYSTEM_PROMPT, BOT_PERSONALITY
    
    # Обновляем системный промпт
    SYSTEM_PROMPT = f"{personality_text}\n\nОтвечай естественно, как будто ты реальный человек на сервере. Обращайся к пользователю по имени {{username}}."
    
    await ctx.send("✅ Личность бота обновлена! Используй `!info` чтобы посмотреть изменения.")

@bot.command(name='clear')
async def clear_history(ctx):
    """Очистить историю разговора"""
    user_id = ctx.author.id
    if user_id in conversation_histories:
        del conversation_histories[user_id]
    await ctx.send("🗑️ История разговора очищена!")

@bot.command(name='info')
async def bot_info(ctx):
    """Информация о боте"""
    # Берем первые 500 символов промпта для preview
    prompt_preview = SYSTEM_PROMPT[:500] + "..." if len(SYSTEM_PROMPT) > 500 else SYSTEM_PROMPT
    
    embed = discord.Embed(title="🤖 Информация о Мойше", color=0x00ff00)
    embed.add_field(name="Имя", value=BOT_PERSONALITY['name'], inline=True)
    embed.add_field(name="Черты", value=BOT_PERSONALITY['traits'], inline=True)
    embed.add_field(name="Стиль", value=BOT_PERSONALITY['style'], inline=False)
    embed.add_field(name="API", value="Google Gemini 2.0", inline=True)
    embed.add_field(name="Текущая личность", value=f"```{prompt_preview}```", inline=False)
    embed.set_footer(text="Изменить личность: !personality [текст]")
    
    await ctx.send(embed=embed)

if __name__ == "__main__":

    bot.run(os.getenv('DISCORD_TOKEN'))
