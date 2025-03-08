
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardRemove, \
    ReplyKeyboardMarkup, KeyboardButton, \
    InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import websockets
import json
from datetime import datetime, timedelta
from collections import defaultdict
import requests
import os
import markups
import config
from db import Database
db = Database("database.db")
operations = defaultdict(list)
last_operation_time = {}
used_mints = []
bot = Bot(token=config.API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)  # Підключаємо сховище до Dispatcher
dp.middleware.setup(LoggingMiddleware())
last_operation_time = defaultdict(lambda: datetime.utcnow())
MINTS_FILE = config.MINTS_FILE
running_tasks = {}
background_tasks = {}
class CreateSignal(StatesGroup):
    WaitingForSignalName = State()
    WaitingForPriceGrowth = State()
    WaitingForAge = State()
    WaitingForLiquidity = State()
    WaitingForVolume = State()
    WaitingForMarketCap = State()
    WaitingForBoosts = State()
    WaitingForVolumeGrowth = State()

# Обробка стартової команди
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if message.chat.type=='private':
        
        if not db.user_exists(message.from_user.id):
            db.add_user(message.from_user.id)
        main_menu = markups.GenMenu
        await message.answer("Вітаю! Ось головне меню:", reply_markup=main_menu)

# Обробка кнопки "Мої сигнали"
@dp.message_handler(lambda message: message.text == "🙎‍♂ Мої сигнали")
async def my_signals(message: types.Message):
    user_signals_menu = markups.create_signal_menu(message.from_user.id)
    await message.answer("Список ваших сигналів:", reply_markup=user_signals_menu)

@dp.callback_query_handler(lambda c: c.data.startswith('signal_'))
async def signal_info(callback_query: types.CallbackQuery):
    signal_name = callback_query.data[len('signal_'):]  # Отримуємо назву сигналу
    info = db.select_signal_info(user_id = callback_query.from_user.id, signal_name = signal_name)
    name, growth, age, market_cap, volume, liquidity, boosts, volume_growth, time = info
    status = db.check_signal_status(callback_query.from_user.id, name)
    signal_info = f"Інформація про сигнал: {signal_name}\nАктивний: {status}\n\nНазва: {name}\nВідсоток: {growth}\nКапіталізація: {market_cap}\nОб'єм: {volume}\nЛіквідність: {liquidity}\nМінімальна кількість бустів: {boosts}\nБажаний volume_growth: {volume_growth}% за час {time} хвилин"  # Тут виводимо всю інформацію про сигнал

    # Кнопки для видалення або повернення
    keyboard = InlineKeyboardMarkup()
    delete_button = InlineKeyboardButton("Видалити сигнал", callback_data=f"delete_{signal_name}")
    back_button = InlineKeyboardButton("Назад", callback_data="back_to_signals")
    if not status:
        activate_button = InlineKeyboardButton("Активувати сигнал", callback_data=f"activate_signal_{signal_name}")
        keyboard.add(delete_button, back_button, activate_button)
    else:
        deactivate_button = InlineKeyboardButton("Деактивувати сигнал", callback_data=f"deactivate_signal_{signal_name}")
        keyboard.add(delete_button, back_button, deactivate_button)
    
    

    # Відповідь користувачу з інформацією про сигнал та кнопками
    await bot.send_message(callback_query.from_user.id, signal_info, reply_markup=keyboard)
    await callback_query.answer()  # Відповідаємо на callback, щоб зняти індикатор наведеності

@dp.callback_query_handler(lambda c: c.data.startswith('delete_'))
async def delete_signal(callback_query: types.CallbackQuery):
    signal_name = callback_query.data[len('delete_'):]  # Отримуємо назву сигналу для видалення
    db.delete_signal(user_id = callback_query.from_user.id, signal_name = signal_name)
    # Тут треба реалізувати видалення сигналу з бази даних
    # Наприклад: db.delete_signal(signal_name)

    # Повідомлення, що сигнал видалено
    await bot.send_message(callback_query.from_user.id, f"Сигнал '{signal_name}' успішно видалено!")
    
    user_signals_menu = markups.create_signal_menu(callback_query.from_user.id)
    await bot.send_message(callback_query.from_user.id, "Список ваших сигналів:", reply_markup=user_signals_menu)
    await callback_query.answer() 

@dp.callback_query_handler(lambda c: c.data == 'back_to_signals')
async def back_to_signals(callback_query: types.CallbackQuery):

    user_signals_menu = markups.create_signal_menu(callback_query.from_user.id)
    
    # Відправляємо повідомлення з кнопками
    await bot.send_message(callback_query.from_user.id, "Ось ваші сигнали:", reply_markup=user_signals_menu)
    await callback_query.answer()  # Відповідаємо на callback

# Обробка кнопки "Створити сигнал"
@dp.message_handler(lambda message: message.text == "💻 Створити сигнал")
async def create_signal(message: types.Message):
    await CreateSignal.WaitingForSignalName.set()  # Переходимо в стан очікування назви сигналу
    await message.answer("Введіть назву сигналу:")

@dp.callback_query_handler(lambda c: c.data == 'back')
async def back_to_menu(callback_query: types.CallbackQuery):
    # Обробка натискання кнопки "Повернутися до меню"
    await bot.send_message(callback_query.from_user.id, "Ви повернулися до головного меню.",
                           reply_markup=markups.GenMenu)  # Заміни на свою функцію для головного меню
    await callback_query.answer()  # Відповідаємо на callback

# Отримання назви сигналу
@dp.message_handler(state=CreateSignal.WaitingForSignalName, content_types=types.ContentTypes.TEXT)
async def get_signal_name(message: types.Message, state: FSMContext):
    signal_name = message.text
    await state.update_data(signal_name=signal_name)  # Зберігаємо назву сигналу у FSM
    # Додаємо запис у базу (зробіть інтеграцію тут)
    signals = db.select_signals(message.from_user.id)
    if signal_name not in signals:
        db.add_signal(user_id=message.from_user.id, signal_name=signal_name)
        signal_menu = markups.Signal_menu  # Меню для налаштування сигналу
        await message.answer(f"Сигнал '{signal_name}' створено! Тепер оберіть параметри:", reply_markup=signal_menu)
        await state.finish()  # Виходимо зі стану
    else:
        await message.answer(f"Сигнал '{signal_name}' вже існує. Спробуйте іншу назву:")

   

# Обробка кнопок створення сигналу
@dp.message_handler(lambda message: message.text in ["Time", "Market Cap", "Liquidity", "Price Growth", "Volume", "Boosts", "Volume Growth", "Markers Growth", "Txn Growth", "⬅️ Назад"])
async def handle_create_signal(message: types.Message):
    if message.text == "⬅️ Назад":
        main_menu = markups.GenMenu  # Якщо назад, повертаємось до головного меню
        await message.answer("Вітаю! Ось головне меню:", reply_markup=main_menu)
    elif message.text == "Price Growth":
        await CreateSignal.WaitingForPriceGrowth.set()  # Переходимо в стан введення відсотка зростання
        await message.answer("Введіть бажаний відсоток зростання ціни за 5 останніх хвилин (лише число):")
        
    elif message.text == "Time":
        await CreateSignal.WaitingForAge.set()  # Переходимо в стан введення часу спостереження
        await message.answer("Введіть час для спостереження (в годинах):")
        
    elif message.text == "Liquidity":
        await CreateSignal.WaitingForLiquidity.set()  
        await message.answer("Введіть ліквідність яка цікавить (в доларах):")
    elif message.text == "Volume":
        await CreateSignal.WaitingForVolume.set()  
        await message.answer("Введіть мінімальний об'єм за 24 години (в доларах):")
    elif message.text == "Market Cap":
        await CreateSignal.WaitingForMarketCap.set()  
        await message.answer("Введіть мінімальну капіталізацію (в доларах):")
    elif message.text == "Boosts":
        await CreateSignal.WaitingForBoosts.set()  
        await message.answer("Введіть бажану мінімальну кількість бустів:")
    elif message.text == "Volume Growth":
        await CreateSignal.WaitingForVolumeGrowth.set()  
        await message.answer("Введіть бажаний відсоток зростання об'єму з час у форматі xx(відсотків)/yy(хвилин):")
    else:
        signal_menu = markups.Signal_menu  # Показуємо меню створення сигналу
        await message.answer(f"Ви вибрали: {message.text}", reply_markup=signal_menu)


@dp.message_handler(state=CreateSignal.WaitingForVolumeGrowth, content_types=types.ContentTypes.TEXT)
async def get_volume_growth(message: types.Message, state: FSMContext):
    try:
        volume_growth = float(message.text.split("/")[0])
        time = message.text.split("/")[1]
        if volume_growth <= 0 and time <=0:
            await message.answer("Будь ласка, введіть числа більше 0.")
            return
        # Зберігаємо параметр у базу (зробіть інтеграцію тут)
        db.update_signal_volume_growth(user_id=message.from_user.id, volume =volume_growth, time = time)

        signal_menu = markups.Signal_menu  # Повертаємося до меню сигналів
        await message.answer(f"Бажаний  volume_growth: {volume_growth} за час {time} хвилин збережено!", reply_markup=signal_menu)
        await state.finish()  # Завершуємо стан

    except:
        await message.answer("Будь ласка, введіть коректне число у форматі xx/yy.")
@dp.message_handler(state=CreateSignal.WaitingForBoosts, content_types=types.ContentTypes.TEXT)
async def get_boosts(message: types.Message, state: FSMContext):
    try:
        
        boosts = float(message.text)  # Перетворюємо введений текст на число
        if boosts <= 0:
            await message.answer("Будь ласка, введіть число більше 0.")
            return

        # Зберігаємо параметр у базу (зробіть інтеграцію тут)
        db.update_signal_boosts(user_id=message.from_user.id, boosts =boosts)

        signal_menu = markups.Signal_menu  # Повертаємося до меню сигналів
        await message.answer(f"Бажану кількість: {boosts} збережено!", reply_markup=signal_menu)
        await state.finish()  # Завершуємо стан

    except ValueError:
        await message.answer("Будь ласка, введіть коректне число.")
@dp.message_handler(state=CreateSignal.WaitingForLiquidity, content_types=types.ContentTypes.TEXT)
async def get_liquidity(message: types.Message, state: FSMContext):
    try:
        
        liq = float(message.text)  # Перетворюємо введений текст на число
        if liq <= 0:
            await message.answer("Будь ласка, введіть число більше 0.")
            return

        # Зберігаємо параметр у базу (зробіть інтеграцію тут)
        db.update_signal_liquidity(user_id=message.from_user.id, liquidity =liq)

        signal_menu = markups.Signal_menu  # Повертаємося до меню сигналів
        await message.answer(f"Бажану ліквідність: {liq} доларів збережено!", reply_markup=signal_menu)
        await state.finish()  # Завершуємо стан

    except ValueError:
        await message.answer("Будь ласка, введіть коректне число.")

@dp.message_handler(state=CreateSignal.WaitingForVolume, content_types=types.ContentTypes.TEXT)
async def get_volume(message: types.Message, state: FSMContext):
    try:
        
        volume = float(message.text)  # Перетворюємо введений текст на число
        if volume <= 0:
            await message.answer("Будь ласка, введіть число більше 0.")
            return

        # Зберігаємо параметр у базу (зробіть інтеграцію тут)
        db.update_signal_volume(user_id=message.from_user.id, volume =volume)

        signal_menu = markups.Signal_menu  # Повертаємося до меню сигналів
        await message.answer(f"Бажаний об'єм: {volume} доларів збережено!", reply_markup=signal_menu)
        await state.finish()  # Завершуємо стан

    except ValueError:
        await message.answer("Будь ласка, введіть коректне число.")
@dp.message_handler(state=CreateSignal.WaitingForMarketCap, content_types=types.ContentTypes.TEXT)
async def get_cap(message: types.Message, state: FSMContext):
    try:
        
        cap = float(message.text)  # Перетворюємо введений текст на число
        if cap <= 0:
            await message.answer("Будь ласка, введіть число більше 0.")
            return

        # Зберігаємо параметр у базу (зробіть інтеграцію тут)
        db.update_signal_cap(user_id=message.from_user.id, cap =cap)

        signal_menu = markups.Signal_menu  # Повертаємося до меню сигналів
        await message.answer(f"Бажану капіталізацію: {cap} доларів збережено!", reply_markup=signal_menu)
        await state.finish()  # Завершуємо стан

    except ValueError:
        await message.answer("Будь ласка, введіть коректне число.")
@dp.message_handler(state=CreateSignal.WaitingForAge, content_types=types.ContentTypes.TEXT)
async def get_age(message: types.Message, state: FSMContext):
    try:
        
        age = float(message.text)  # Перетворюємо введений текст на число
        if age <= 0:
            await message.answer("Будь ласка, введіть число більше 0.")
            return

        # Зберігаємо параметр у базу (зробіть інтеграцію тут)
        db.update_signal_age(user_id=message.from_user.id, age =age)

        signal_menu = markups.Signal_menu  # Повертаємося до меню сигналів
        await message.answer(f"Бажаний час моніторингу: {age} хвилин збережено!", reply_markup=signal_menu)
        await state.finish()  # Завершуємо стан

    except ValueError:
        await message.answer("Будь ласка, введіть коректне число.")
# Отримання бажаного відсотка зростання ціни
@dp.message_handler(state=CreateSignal.WaitingForPriceGrowth, content_types=types.ContentTypes.TEXT)
async def get_price_growth(message: types.Message, state: FSMContext):
    try:
        
        price_growth = float(message.text)  # Перетворюємо введений текст на число
        if price_growth <= 0:
            await message.answer("Будь ласка, введіть число більше 0.")
            return

        # Зберігаємо параметр у базу (зробіть інтеграцію тут)
        db.update_signal_price_growth(user_id=message.from_user.id, price_growth =price_growth)

        signal_menu = markups.Signal_menu  # Повертаємося до меню сигналів
        await message.answer(f"Бажаний відсоток зростання ціни: {price_growth}% збережено!", reply_markup=signal_menu)
        await state.finish()  # Завершуємо стан

    except ValueError:
        await message.answer("Будь ласка, введіть коректне число.")
# Обробка кнопок створення сигналу
@dp.message_handler(lambda message: message.text in ["Time", "Market Cap", "Liquidity", "Price Growth", "Volume", "Volume Growth", "Markers", "Markers Growth", "Txn Growth", "Back"])
async def handle_create_signal(message: types.Message):
    if message.text == "Back":
        main_menu = markups.GenMenu   # Якщо назад, повертаємось до головного меню
        await message.answer("Вітаю! Ось головне меню:", reply_markup=main_menu)
    else:
        signal_menu = markups.Signal_menu  # Показуємо меню створення сигналу
        await message.answer(f"Ви вибрали: {message.text}", reply_markup=signal_menu)

async def read_file(filepath, max_retries=5, delay=0.5):
    retries = 0
    while retries < max_retries:
        try:
            with open(filepath, "r") as file:
                return json.load(file)
        except IOError as e:

            print(f"Файл зайнятий, спроба {retries + 1}/{max_retries}...")
            retries += 1
            await asyncio.sleep(delay)

async def update_mints():
    """Оновлює список токенів у файлі."""
    while True:
        if os.path.exists(MINTS_FILE):
            mints_data = await read_file(MINTS_FILE)
        else:
            print("fuck")
            mints_data = {}
        if len(mints_data) < 150:


            url = "https://api.dexscreener.com/token-profiles/latest/v1"
            response = requests.get(url)
            data = response.json()
    
            new_mints =[]
            for token in data:
                if token["chainId"] == "solana":
                    if "links" in token:
                        links = token["links"]
                    else:
                        links = None
                    mint = token["tokenAddress"]
                    url = token["url"]
                    if mint not in mints_data:
                        mints_data[mint] = {"added": datetime.utcnow().isoformat(), "prices":[], "volume": 0, "liquidity":0, "marketCap": 0,"boosts":0, "links": links, "url": url, "priceChange": 0, "price": 0}
 

    
            
 

            retries = 0
            while retries < 5:
                try:                    
                    with open(MINTS_FILE, "w") as f:
                        json.dump(mints_data, f, indent=2) 
                    break
                except IOError as e:

                    print(f"Файл зайнятий, спроба {retries + 1}/5...")
                    retries += 1
                    asyncio.sleep(0.5)
        await asyncio.sleep(60)
    
async def get_mint_list():
    """Завантажує список токенів з файлу."""
    if os.path.exists(MINTS_FILE):
        data = await read_file(MINTS_FILE)
        mints_data = list(data.keys())
        return mints_data
    return []

async def get_token_prices():
    """Отримує ціни всіх моніторених токенів."""
    while True:
        data = []
        if os.path.exists(MINTS_FILE):
            mints_data = await read_file(MINTS_FILE)
            mints = await get_mint_list()
                
        else:
            mints_data = {}
 
        if not mints:

            return []

        for i in range(int(len(mints)//30)+1):
        


            scan_mints = mints[(i)*30:(i+1)*30]

            url = f"https://api.dexscreener.com/tokens/v1/solana/{','.join(scan_mints)}"
            response = requests.get(url)

            data = data + response.json()


            

    
        for mint in data:
            address = mint["baseToken"]["address"]
            
 
            if address in mints_data:

                mints_data[address]["volume"] = mint["volume"]["h24"]
                if "liquidity" in mint:
                    mints_data[address]["liquidity"] = mint["liquidity"]["usd"]
                if "boosts" in mint:
                    mints_data[address]["boosts"] = mint["boosts"]["active"]
                if "marketCap" in mint:
                    mints_data[address]["marketCap"] = mint["marketCap"]
                if "priceNative" in mint:
                    mints_data[address]["price"] = mint["priceNative"]
                if "priceChange" in mint and "m5" in mint["priceChange"]:
                    mints_data[address]["priceChange"] = mint["priceChange"]["m5"]
                elif "priceChange" in mint and "h1" in mint["priceChange"]:
                    mints_data[address]["priceChange"] = mint["priceChange"]["h1"]
                
                elif "priceChange" in mint and "h24" in mint["priceChange"]:
                    mints_data[address]["priceChange"] = mint["priceChange"]["h24"]
                info = {"time": datetime.utcnow().isoformat(), "volume": mint["volume"]["m5"]}
                mints_data[address]["prices"].append(info)    
                
                        
        retries = 0
        while retries < 5:
            try:                    
                with open(MINTS_FILE, "w") as f:
                    json.dump(mints_data, f, indent=2) 
                break
            except IOError as e:

                print(f"Файл зайнятий, спроба {retries + 1}/5...")
                retries += 1
                await asyncio.sleep(0.5)
        await asyncio.sleep(10)

async def update_prices(growth, age, user_id, name, market_cap, volume, liquidity, boosts,volume_growth, time_growth):
    """Моніторить ціни й аналізує зміни для всіх користувачів."""
    used_mints = []

    while True:

        if not db.check_signal_status(user_id, name):
            
            return
        if os.path.exists(MINTS_FILE):
            mints_data = await read_file(MINTS_FILE)

        else:
            mints_data = {}
        mints = list(mints_data.keys())
        for mint in mints:
            if os.path.exists(MINTS_FILE):
                mints_data = await read_file(MINTS_FILE)
            else:
                mints_data = {}

            time_to_growth = int(time_growth*2)
            price_growth = float(mints_data[mint]["priceChange"])
            volumes = [float(op["volume"]) for op in mints_data[mint]["prices"][-time_to_growth:-1]]
            token_boosts = 0
            if mints_data[mint]["boosts"]:
                token_boosts  = float(mints_data[mint]["boosts"])
            if len(volumes) > 2:


                max_volume = max(volumes)         
                min_volume = min(volumes)

                token_market_cap = float(mints_data[mint]["marketCap"])
                token_volume = float(mints_data[mint]["volume"])
    
                token_liquidity = float(mints_data[mint]["liquidity"])
                

                if mint not in used_mints and price_growth/100 >  float(growth) / 100 and max_volume >= min_volume * (volume_growth + 100) / 100 and token_market_cap >= market_cap and token_volume >= volume and token_liquidity >= liquidity and token_boosts >= boosts:
                    url = mints_data[mint]["url"]

                    message = f"🚀 Сигнал {name}\nЦіна {url} зросла мінімум на {growth}%!\n"
                    links = mints_data[mint]["links"]
                    if links:
                        for link in links:
                            if "label" in link:
                                label = link["label"]
                            elif "type" in link:
                                label = link["type"]
                            else:
                                label = ""
                            link_url = link["url"]
                            message += f"Назва ресурсу: {label}\nПосилання: {link_url}\n"
                    await bot.send_message(user_id, message)

                    used_mints.append(mint)
            elif token_boosts > 400:
                token_market_cap = float(mints_data[mint]["marketCap"])
                token_volume = float(mints_data[mint]["volume"])
    
                token_liquidity = float(mints_data[mint]["liquidity"])
                if mint not in used_mints:
                    url = mints_data[mint]["url"]

                    message = f"🚀 Сигнал {name}\nЦіна {url} зросла мінімум на {growth}%!\n"
                    links = mints_data[mint]["links"]
                    if links:
                        for link in links:
                            if "label" in link:
                                label = link["label"]
                            elif "type" in link:
                                label = link["type"]
                            else:
                                label = ""
                            link_url = link["url"]
                            message += f"Назва ресурсу: {label}\nПосилання: {link_url}\n"
                    await bot.send_message(user_id, message)

                    used_mints.append(mint)

                    '''
                    del mints_data[mint]
                    retries = 0
                    while retries < 5:
                        try:                    
                            with open(MINTS_FILE, "w") as f:
                                json.dump(mints_data, f, indent=2) 
                                break
                        except IOError as e:

                            print(f"Файл зайнятий, спроба {retries + 1}/5...")
                            retries += 1
                            await asyncio.sleep(0.5)
                        '''

        await asyncio.sleep(30)  # Перевірка кожні 30 секунд

    

    


        
async def remove_inactive():
    while True:
        if os.path.exists(MINTS_FILE):
            mints_data = await read_file(MINTS_FILE)
        else:
            print("fuck")
            mints_data = {}
        to_delete = []

        for mint in mints_data:
            if len(mints_data[mint]["prices"])>2:
                volume = mints_data[mint]["prices"][-1]["volume"]
                price_growth = float(mints_data[mint]["priceChange"])
                boosts = float(mints_data[mint]["boosts"])
                if datetime.fromisoformat(mints_data[mint]["added"]) < datetime.utcnow() - timedelta(hours=24) or (volume < 70000 and mints_data[mint]["volume"] < 1000000) or (mints_data[mint]["volume"] > 1000000 and volume < 8000):
                    to_delete.append(mint)


        for mint in to_delete:
            del mints_data[mint]
        retries = 0
        while retries < 5:
            try:                    
                with open(MINTS_FILE, "w") as f:
                    json.dump(mints_data, f, indent=2) 
                break
            except IOError as e:

                print(f"Файл зайнятий, спроба {retries + 1}/5...")
                retries += 1
                await asyncio.sleep(0.5)
        await asyncio.sleep(180)
@dp.callback_query_handler(lambda c: c.data.startswith('activate_signal_'))
async def activate_signal(callback_query: types.CallbackQuery):
    signal_name = callback_query.data[len('activate_signal_'):]
    info = db.select_signal_info(user_id=callback_query.from_user.id, signal_name=signal_name)
    
    name, growth, age, market_cap, volume, liquidity, boosts,volume_growth, time_growth = info

    await bot.send_message(callback_query.from_user.id, f"Сигнал {name} активовано.")
    await callback_query.answer() 
    global running_tasks
    if "remove_inactive" not in running_tasks or running_tasks["remove_inactive"].done():
        running_tasks["remove_inactive"] = asyncio.create_task(remove_inactive())
    if "update_mints" not in running_tasks or running_tasks["update_mints"].done():
        running_tasks["update_mints"] = asyncio.create_task(update_mints())
    await asyncio.sleep(1)
    if "get_token_prices" not in running_tasks or running_tasks["get_token_prices"].done():
        running_tasks["get_token_prices"] = asyncio.create_task(get_token_prices())
    await asyncio.sleep(1)
    
    await asyncio.sleep(1)
    db.change_signal_status(callback_query.from_user.id, name, True)
    await asyncio.sleep(0.5)
    await update_prices(growth, age, callback_query.from_user.id, name, market_cap, volume, liquidity, boosts,volume_growth, time_growth)

    
        
        
    
    
@dp.callback_query_handler(lambda c: c.data.startswith('deactivate_signal_'))
async def deactivate_signal(callback_query: types.CallbackQuery):
    signal_name = callback_query.data[len('deactivate_signal_'):]
    info = db.select_signal_info(user_id=callback_query.from_user.id, signal_name=signal_name)
    
    name, growth, age, market_cap, volume, liquidity, boosts,volume_growth, time_growth = info
    db.change_signal_status(callback_query.from_user.id, name, False)
    await callback_query.answer() 
    await bot.send_message(callback_query.from_user.id, f"Сигнал {name} деактивовано.")
    


    


  

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

