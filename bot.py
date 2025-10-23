import discord
import os
from discord.ext import commands
from dotenv import load_dotenv
from groq import Groq

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
    import re
    cleaned = re.sub(r'\([^)]*\)', '', username)
    cleaned = cleaned.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    first_part = cleaned.split()[0] if cleaned.strip() else username
    
    if len(first_part) > 12:
        first_part = first_part[:12]
    
    if first_part and first_part[-1].isdigit():
        first_part = first_part.rstrip('0123456789')
    
    result = first_part.strip() if first_part.strip() else "друг"
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

class QwenAPI:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        self.model = "qwen/qwen3-32b"
    
    def generate_response(self, message, conversation_history=None, username="Пользователь"):
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
            messages = [
                {"role": "system", "content": formatted_system_prompt}
            ]
            
            # Добавляем историю разговора (последние 10 сообщений)
            for msg in conversation_history[-10:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Добавляем текущее сообщение
            messages.append({
                "role": "user",
                "content": message
            })
            
            # Делаем запрос к Groq
            # Пробуем с reasoning_effort="none" для Qwen (убирает <think> теги)
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=1.0,
                    max_tokens=4000,
                    top_p=0.95,
                    reasoning_effort="none"
                )
            except Exception as e:
                # Если модель не поддерживает reasoning_effort, пробуем без него
                if "reasoning_effort" in str(e).lower() or "unsupported" in str(e).lower():
                    completion = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=1.0,
                        max_tokens=2048,
                        top_p=0.95
                    )
                else:
                    raise e
            
            response_text = completion.choices[0].message.content
            
            # Дополнительная очистка: убираем <think> теги если они остались
            import re
            response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
            response_text = response_text.strip()
            
            return response_text
                        
        except Exception as e:
            error_msg = str(e).lower()
            
            # Кастомные сообщения для разных ошибок
            if "rate limit" in error_msg or "429" in error_msg:
                return "Ой вей, слишком много запросов! Подожди таки немного... ⏳"
            elif "503" in error_msg or "unavailable" in error_msg:
                return "Ой вей, вы меня нагрузили, дайте таки передохнуть! 🥵"
            elif "500" in error_msg:
                return "Ай-ай-ай! Что-то сломалось на сервере! 🔧"
            elif "401" in error_msg or "403" in error_msg or "api key" in error_msg:
                return "Ой, нет доступа! Проверь таки API ключ! 🔑"
            else:
                print(f"Groq API Error: {str(e)}")
                return f"Произошла ошибка: {str(e)}"

# Инициализация API
qwen = QwenAPI(os.getenv('GROQ_API_KEY'))

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
    
    # Ограничиваем историю последними 10 сообщениями
    if len(conversation_histories[user_id]) > 10:
        conversation_histories[user_id] = conversation_histories[user_id][-10:]

@bot.event
async def on_ready():
    print(f'Бот {bot.user} запущен!')
    print(f'Модель: {qwen.model}')
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
            
            # Получаем историю разговора для этого пользователя
            user_id = message.author.id
            history = conversation_histories.get(user_id, [])
            
            # Генерируем ответ (синхронно, т.к. Groq SDK не асинхронный)
            raw_username = message.author.display_name or message.author.name
            smooth_name = smooth_username(raw_username)
            
            # Запускаем синхронную функцию в executor для неблокирующего выполнения
            loop = bot.loop
            response = await loop.run_in_executor(
                None, 
                qwen.generate_response, 
                clean_content, 
                history, 
                smooth_name
            )
            
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
    prompt_preview = SYSTEM_PROMPT[:500] + "..." if len(SYSTEM_PROMPT) > 500 else SYSTEM_PROMPT
    
    embed = discord.Embed(title="🤖 Информация о Мойше", color=0x00ff00)
    embed.add_field(name="Имя", value=BOT_PERSONALITY['name'], inline=True)
    embed.add_field(name="Черты", value=BOT_PERSONALITY['traits'], inline=True)
    embed.add_field(name="Стиль", value=BOT_PERSONALITY['style'], inline=False)
    embed.add_field(name="API & Модель", value=f"Groq ({qwen.model})", inline=True)
    embed.add_field(name="Текущая личность", value=f"```{prompt_preview}```", inline=False)
    embed.set_footer(text="Изменить личность: !personality [текст]")
    
    await ctx.send(embed=embed)

@bot.command(name='model')
async def change_model(ctx, model_name: str = None):
    """Изменить модель AI или показать список доступных моделей"""
    global qwen
    
    # Список поддерживаемых моделей
    AVAILABLE_MODELS = {
        "qwen/qwen3-32b": "Qwen 3 32B - Быстрая модель с reasoning",
        "moonshotai/kimi-k2-instruct-0905": "Kimi K2 - Мощная китайская модель",
        "meta-llama/llama-4-maverick-17b-128e-instruct": "Llama 4 Maverick - Новейшая от Meta"
    }
    
    # Если модель не указана - показываем список с кнопками
    if model_name is None:
        embed = discord.Embed(
            title="🤖 Доступные модели AI",
            description="Выбери модель, нажав на кнопку ниже:",
            color=0x00ff00
        )
        embed.add_field(
            name="Текущая модель", 
            value=f"`{qwen.model}`", 
            inline=False
        )
        
        # Добавляем описание каждой модели
        for model, desc in AVAILABLE_MODELS.items():
            embed.add_field(
                name=f"{'✅' if model == qwen.model else '🔘'} `{model}`",
                value=desc,
                inline=False
            )
        
        embed.set_footer(text="Используй кнопки ниже для выбора модели")
        
        # Создаем кнопки (Discord поддерживает до 5 кнопок в ряду, до 25 всего)
        view = discord.ui.View(timeout=180)  # 3 минуты на выбор
        
        # Создаем кнопки для каждой модели
        for model_key in AVAILABLE_MODELS.keys():
            button = discord.ui.Button(
                label=model_key.split('/')[-1][:20],  # Короткое имя для кнопки
                style=discord.ButtonStyle.primary if model_key == qwen.model else discord.ButtonStyle.secondary,
                custom_id=model_key
            )
            
            async def button_callback(interaction: discord.Interaction, selected_model=model_key):
                # Сразу отвечаем на interaction (до 3 секунд!)
                try:
                    old_model = qwen.model
                    qwen.model = selected_model
                    
                    # Обновляем embed
                    new_embed = discord.Embed(
                        title="🤖 Модель изменена!",
                        description=f"✅ `{old_model}` → `{selected_model}`",
                        color=0x00ff00
                    )
                    new_embed.add_field(
                        name="Текущая модель", 
                        value=f"`{selected_model}`", 
                        inline=False
                    )
                    
                    # Отвечаем и обновляем сообщение одновременно
                    await interaction.response.edit_message(embed=new_embed, view=None)
                except Exception as e:
                    print(f"Button callback error: {e}")
                    # Если interaction истек, пробуем через followup
                    try:
                        await interaction.followup.send(
                            f"✅ Модель изменена: `{old_model}` → `{selected_model}`",
                            ephemeral=True
                        )
                    except:
                        pass
            
            button.callback = button_callback
            view.add_item(button)
        
        await ctx.send(embed=embed, view=view)
        return
    
    # Если модель указана в команде - меняем напрямую
    if model_name not in AVAILABLE_MODELS:
        models_list = "\n".join([f"• `{m}`" for m in AVAILABLE_MODELS.keys()])
        await ctx.send(
            f"❌ Модель `{model_name}` не найдена!\n\n**Доступные модели:**\n{models_list}\n\n"
            f"Используй `!model` без параметров для интерактивного выбора."
        )
        return
    
    old_model = qwen.model
    qwen.model = model_name
    await ctx.send(f"✅ Модель изменена: `{old_model}` → `{model_name}`")

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))

