# -*- coding: utf-8 -*-
import re
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import config
bot = Bot(token=config.API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
import os
import json
import requests
import asyncio
from datetime import datetime, timedelta
from collections import Counter
import matplotlib.pyplot as plt
import io
import numpy as np
DATA_FILE = config.DATA_FILE
running_tasks = {}

async def on_startup(_):
    asyncio.create_task(check_tokens_loop()) 
# --- FSM ---
class WaitToken(StatesGroup):
    waiting_identifier = State()
    waiting_message = State()



async def read_file(filepath, max_retries=5, delay=0.5):
    retries = 0
    while retries < max_retries:
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                return json.load(file)
        except IOError as e:

            print(f"Файл зайнятий, спроба {retries + 1}/{max_retries}...")
            retries += 1
            await asyncio.sleep(delay)
        except FileNotFoundError:
            return {}

# process_token: додає токен одразу (added_at + total_added лише якщо токен новий)
def ensure_repeat_identifier(data: dict) -> str:
    """Повертає ім’я repeat_x, створюючи новий при потребі."""
    i = 1
    while True:
        repeat_id = f"repeat_{i}"
        if repeat_id not in data:
            data[repeat_id] = {
                "name": repeat_id,
                "stats": {
                    "total_added": 0,
                    "total_success_30": 0,
                    "total_success_50": 0,
                    "total_success_100": 0,
                }
            }
            return repeat_id
        i += 1


def process_token(identifier: str, token: str, params=None):
    if params is None:
        params = {}

    token_key = token.strip()

    # читаємо дані
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}
    else:
        data = {}

    # якщо користувача ще нема
    if identifier not in data or not isinstance(data[identifier], dict):
        data[identifier] = {
            "name": identifier,
            "stats": {"total_added": 0, "total_success_30": 0,
                      "total_success_50": 0, "total_success_100": 0}
        }

    user_entry = data[identifier]
    stats = user_entry.setdefault("stats", {"total_added": 0, "total_success_30": 0,
                                            "total_success_50": 0, "total_success_100": 0})

    # чи є вже токен у цього юзера?
    if any(k.lower() == token_key.lower() for k in user_entry.keys() if k not in ("name", "stats")):
        # токен уже є → нічого не робимо
        pass
    else:
        # перевіряємо: може токен є в когось іншого (але ігноруємо repeat_x)?
        exists_elsewhere = any(
            any(k.lower() == token_key.lower() for k in tokens if k not in ("name", "stats"))
            for uid, tokens in data.items()
            if uid != identifier and not uid.startswith("repeat_")
        )

        if exists_elsewhere:
            # знайдемо перший існуючий repeat_n, у якому цього токена ще немає (case-insensitive)
            repeat_id = None
            repeat_indices = []
            for k in data.keys():
                if isinstance(k, str) and k.startswith("repeat_"):
                    try:
                        repeat_indices.append(int(k.split("_", 1)[1]))
                    except Exception:
                        continue
            repeat_indices = sorted(repeat_indices)
            for idx in repeat_indices:
                rid = f"repeat_{idx}"
                rep = data.get(rid, {})
                if not any(k.lower() == token_key.lower() for k in rep.keys() if k not in ("name", "stats")):
                    repeat_id = rid
                    break
            # якщо не знайшли підходящого repeat — створимо новий
            if not repeat_id:
                repeat_id = ensure_repeat_identifier(data)

            repeat_entry = data[repeat_id]
            repeat_stats = repeat_entry.setdefault("stats", {"total_added": 0, "total_success_30": 0, "total_success_50": 0, "total_success_100": 0})

            repeat_entry[token_key] = params.copy()
            repeat_entry[token_key]["added_at"] = datetime.utcnow().isoformat()
            repeat_stats["total_added"] = repeat_stats.get("total_added", 0) + 1

        # додаємо токен у поточного користувача
        user_entry[token_key] = params.copy()
        user_entry[token_key]["added_at"] = datetime.utcnow().isoformat()
        stats["total_added"] += 1

    # зберігаємо
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)




# --- хендлери ---
@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):
    
    await message.answer("Перешлите сообщение (пользователь/канал).\n")
    await WaitToken.waiting_identifier.set()
    

@dp.message_handler(lambda message: not (message.text and message.text.startswith("/")), 
                    state=WaitToken.waiting_identifier, 
                    content_types=["text", "photo"])
async def get_identifier(message: types.Message, state: FSMContext):
    identifier = None
    token_found = None

    # беремо текст або підпис (для фото)
    content_text = message.text or message.caption or ""

    # якщо переслане повідомлення
    if message.forward_from:
        identifier = f"{message.forward_from.id}"
        display_name = message.forward_from.full_name or message.forward_from.username or str(message.forward_from.id)
    elif message.forward_from_chat:
        identifier = f"{message.forward_from_chat.id}"
        display_name = message.forward_from_chat.title
    elif message.forward_sender_name:
        identifier = f"{message.forward_sender_name}"
        display_name = message.forward_sender_name
    else:
        pattern = r"\b[A-Za-z0-9]{43,45}\b"
        match = re.search(pattern, content_text)
        if match:
            token_found = match.group(0)
            identifier = "ungrouped"
            display_name = "ungrouped"
        else:
            identifier = content_text.strip()
            display_name = identifier

    # зберігаємо у файл
    if not os.path.exists(DATA_FILE):
        data = {}
    else:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}

    if identifier not in data:
        data[identifier] = {
            "name": display_name,
            "stats": {
                "total_added": 0,
                "total_success_30": 0,
                "total_success_50": 0,
                "total_success_100": 0
            }
        }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # пробуємо знайти токен у тексті/підписі
    if identifier:
        pattern = r"\b[A-Za-z0-9]{43,45}\b"
        match = re.search(pattern, content_text)
        if match:
            token_found = match.group(0)
            process_token(identifier, token_found)
            await message.answer(f"Найден токен: {token_found}\nИдентификатор: {identifier}")
            global running_tasks
            if "get_token_info" not in running_tasks or running_tasks["get_token_info"].done():
                running_tasks["get_token_info"] = asyncio.create_task(get_token_info())
            
            await WaitToken.waiting_identifier.set()
            await message.answer("Перешлите новое сообщение")
            return
        else:
            await state.update_data(identifier=identifier)
            await message.answer(f"Идентификатор: {identifier}\n"
                                 "В этом сообщении токен не найден.")
            await WaitToken.waiting_message.set()
            return

    identifier = content_text.strip()
    await state.update_data(identifier=identifier)
    await message.answer(f"Идентификатор сохранен: {identifier}")
    await WaitToken.waiting_message.set()

@dp.message_handler(lambda message: not message.text.startswith("/"), state=WaitToken.waiting_message)
async def get_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    identifier = data.get("identifier")

    pattern = r"\b[A-Za-z0-9]{43,45}\b"
    match = re.search(pattern, message.text)
    if match:
        token = match.group(0)
        process_token(identifier, token)
        await message.answer(f"Найден токен: {token}\nИдентификатор: {identifier}")
        global running_tasks
        if "get_token_info" not in running_tasks or running_tasks["get_token_info"].done():
            running_tasks["get_token_info"] = asyncio.create_task(get_token_info())
    else:
        await message.answer("В этом сообщении токен не найден.")

    # цикл знову з початку
    await WaitToken.waiting_identifier.set()
    await message.answer("Перешлите новое сообщение")

async def get_mint_list():
    if os.path.exists(DATA_FILE):
        data = await read_file(DATA_FILE)
        mints_data = []
        for identifier, tokens in data.items():
            for k in tokens.keys():
                if k not in ("stats", "name"):  # пропускаємо службові ключі
                    mints_data.append(k)
        return mints_data
    return []

# get_token_info: асинхронний, коректно співставляє токени, встановлює initial_price/price тощо
async def get_token_info():
    """Отримує ціни і оновлює записи. added_at і total_added вже ставляться в process_token"""
    while True:
        mints_data = await read_file(DATA_FILE)
        # збираємо список унікальних токенів (ігноруємо 'name' і 'stats')
        all_tokens = []
        for identifier, user_tokens in mints_data.items():
            if not isinstance(user_tokens, dict):
                continue
            for k in user_tokens.keys():
                if k in ("name", "stats"):
                    continue
                all_tokens.append(k)

        if not all_tokens:
            # нічого немає — трохи почекати
            await asyncio.sleep(10)
            continue

        # робимо запити по пачках
        collected = []
        for i in range(0, len(all_tokens), 29):
            scan_mints = all_tokens[i:i+29]
            url = f"https://api.dexscreener.com/tokens/v1/solana/{','.join(scan_mints)}"
            try:
                resp = requests.get(url, timeout=10)
            except Exception as e:
                print("Запрос к dexscreener не удался:", e)
                await asyncio.sleep(1)
                continue

            if resp and resp.status_code == 200:
                try:
                    j = resp.json()
                except Exception:
                    continue
                if isinstance(j, list):
                    collected.extend(j)

        if not collected:
            # якщо API повернув пусто — зачекати і повторити
            await asyncio.sleep(10)
            continue

        # Для швидкого доступу зробимо словник за адресою (lowercase) -> mint_data
        api_by_address = {}
        for mint in collected:
            addr = mint.get("baseToken", {}).get("address")
            if not addr:
                continue
            api_by_address[addr.lower()] = mint

        # Оновлюємо mints_data
        modified = False
        for identifier, user_tokens in mints_data.items():
            if not isinstance(user_tokens, dict):
                continue
            stats = user_tokens.setdefault("stats", {})
            # створимо список ключів токенів, щоб не гуляти по службових полях
            token_keys = [k for k in user_tokens.keys() if k not in ("name", "stats")]

            for key in token_keys:
                # знайдемо відповідь API: порівнюємо ключ (user key) з lower адресами
                match_addr = None
                # переважно ключ вже є у api_by_address (якщо користувач додав саме ту адресу)
                if key.lower() in api_by_address:
                    match_addr = key.lower()
                else:
                    # іноді ключ може бути в іншому форматі — але ми вже зібрали всі адреси, тому нічого робити
                    # просто пропускаємо, якщо не знайдено
                    match_addr = None

                if match_addr is None:
                    # API не знайшов цього токена в останньому зборі — нічого оновлювати
                    continue

                mint = api_by_address[match_addr]
                token_info = user_tokens.setdefault(key, {})

                # initial_price ставимо тільки якщо немає
                price_native = mint.get("priceNative")
                if "initial_price" not in token_info and price_native is not None:
                    token_info["initial_price"] = price_native

                # завжди оновлюємо поточну ціну та інші поля
                if price_native is not None:
                    token_info["price"] = price_native
                    if "max_price" not in token_info:
                        token_info["max_price"] = price_native
                    else:
                        # якщо нова ціна більше збереженої максимальної → оновлюємо
                        if price_native > token_info["max_price"]:
                            token_info["max_price"] = price_native
                if "volume" in mint:
                    token_info["volume"] = mint["volume"].get("h24")
                if "liquidity" in mint and isinstance(mint["liquidity"], dict):
                    token_info["liquidity"] = mint["liquidity"].get("usd")
                if "boosts" in mint and isinstance(mint["boosts"], dict):
                    token_info["boosts"] = mint["boosts"].get("active")
                if "marketCap" in mint:
                    token_info["marketCap"] = mint.get("marketCap")
                priceChange = mint.get("priceChange", {})
                token_info["priceChange"] = priceChange.get("h24") or priceChange.get("h1") or priceChange.get("m5")

                # не змінюємо added_at тут (бо його має ставити process_token при додаванні)
                modified = True

        if modified:
            retries = 0
            while retries < 5: 
                try: 
                    with open(DATA_FILE, "w", encoding="utf-8") as f: 
                        json.dump(mints_data, f, indent=2, ensure_ascii=False) 
                    break 
                except IOError: 
                    retries += 1 
                    print(f"Файл зайнятий, спроба {retries}/5...") 
                    await asyncio.sleep(0.5)

        # чекати перед наступним циклом (поставив 10 секунд, можна змінити)
        await asyncio.sleep(10)


        

async def check_tokens_loop():
    """Перевіряє токени щогодини, оновлює статистику"""
    while True:
        try:
            data = await read_file(DATA_FILE)
        except FileNotFoundError:
            data = {}

        now = datetime.utcnow()
        modified = False
        for user_id, user_data in list(data.items()):
            for mint in list(user_data.keys()):   # ← робимо список ключів
                info = user_data[mint]
                if not isinstance(info, dict) or "added_at" not in info:
                    continue
                if isinstance(info, dict) and "added_at" in info:
                    added_at_str = info["added_at"]
                    stats = user_data.get(
                        "stats",
                        {"total_added": 0, "total_success_30": 0, "total_success_50": 0, "total_success_100": 0}
                    )
            
                    token_items = {k: v for k, v in user_data.items() if k != "stats"}


                    initial_price = float(info.get("initial_price", 0))
                    current_price = float(info.get("price", 0))
                    max_p = float(info.get("max_price", 0))
                    # Ініціалізуємо прапорці, якщо їх немає
                    if "success_30" not in info:
                        info["success_30"] = False
                        modified = True
                    if "success_50" not in info:
                        info["success_50"] = False
                        modified = True
                    if "success_100" not in info:
                        info["success_100"] = False
                        modified = True

                    added_at = datetime.fromisoformat(added_at_str) if added_at_str else now
                    remove = False
                    
                    # Перевірка на зростання ≥30%
                    if max_p >= 1.3 * initial_price and not info["success_30"]:
                        stats["total_success_30"] = stats.get("total_success_30", 0) + 1
                        info["success_30"] = True
                        modified = True
    
                    # Перевірка на зростання ≥50%
                    if max_p >= 1.5 * initial_price and not info["success_50"]:
                        stats["total_success_50"] = stats.get("total_success_50", 0) + 1
                        info["success_50"] = True
                        modified = True

                # Перевірка на зростання ≥100%
                    if max_p >= 2 * initial_price and not info["success_100"]:    
                        stats["total_success_100"] = stats.get("total_success_100", 0) + 1
                        info["success_100"] = True
                        modified = True
                     

                    # Видалення старих (>1 день)
                    if now - added_at > timedelta(days=10):
                        remove = True

                    if remove:
                        if "deleted_growths" not in stats:
                            stats["deleted_growths"] = []
                        init_p = float(info.get("initial_price", 0))
                        max_p = float(info.get("max_price", 0))
                        if init_p > 0 and max_p > 0:
                            growth = (max_p - init_p) / init_p * 100
                            stats["avg_growth_deleted_count"] = stats.get("avg_growth_deleted_count", 0) + 1                      
                            stats["deleted_growths"].append(growth)

                        del user_data[mint]
                        modified = True

                    user_data["stats"] = stats
                    data[user_id] = user_data

        if modified:
            retries = 0 
            while retries < 5: 
                try: 
                    with open(DATA_FILE, "w", encoding="utf-8") as f: 
                        json.dump(data, f, indent=2, ensure_ascii=False) 
                    break 
                except IOError: 
                    retries += 1 
                    print(f"Файл зайнятий, спроба {retries}/5...") 
                    await asyncio.sleep(0.5)

        # Чекати 1 годину до наступної перевірки
        await asyncio.sleep(15)
from aiogram import types
from collections import Counter


# -----------------------------------------------
# НОВА ЛОГІКА: перенос/додавання дублікатів у repeat_x
# -----------------------------------------------

def add_duplicates_to_repeat(data: dict) -> bool:
    """Оновлена версія для коректного додавання токенів у repeat_* без видалення старих записів.

    Логіка:
    - Для кожного токена визначаємо унікальних власників (ігноруючи repeat_*).
    - occ = кількість унікальних uid.
    - Якщо occ <= 1 — пропускаємо (не додаємо в repeat_*).
    - Визначаємо repeat_index = occ - 1.
    - Переконуємось, що токен існує у repeat_{repeat_index} (додаємо або оновлюємо).
    - Дані беремо з останнього власника за added_at.
    - Повертаємо True, якщо були зміни у data.
    """
    from datetime import datetime

    modified = False

    # Збираємо токени по нижньому регістру -> uid -> ключі
    token_to_uid_keys = {}
    for uid, ud in data.items():
        if not isinstance(ud, dict) or uid.startswith("repeat_"):
            continue
        for key in ud:
            if key in ("name", "stats"):
                continue
            token_to_uid_keys.setdefault(key.lower(), {}).setdefault(uid, []).append(key)

    for token_lower, uid_map in token_to_uid_keys.items():
        # Вибираємо останній ключ для кожного uid за added_at
        owner_records = []  # (uid, key, added_at, value)
        for uid, keys in uid_map.items():
            latest_key = None
            latest_added = None
            latest_val = None
            for key in keys:
                val = data[uid].get(key)
                added_at = None
                if isinstance(val, dict):
                    a = val.get("added_at")
                    if isinstance(a, str):
                        try:
                            added_at = datetime.fromisoformat(a)
                        except Exception:
                            added_at = None
                if added_at is None:
                    added_at = datetime.min
                if latest_added is None or added_at > latest_added:
                    latest_added = added_at
                    latest_key = key
                    latest_val = val
            if latest_key is not None:
                owner_records.append((uid, latest_key, latest_added, latest_val))

        occ = len(owner_records)
        if occ <= 1:
            continue  # мало власників — не додаємо в repeat_*

        # беремо дані останнього власника
        owner_records.sort(key=lambda x: x[2])
        _, latest_key, _, latest_val = owner_records[-1]
        params = latest_val.copy() if isinstance(latest_val, dict) else {}

        # визначаємо repeat_index
        repeat_index = occ - 1
        repeat_id = f"repeat_{repeat_index}"

        # створюємо repeat, якщо його ще нема
        if repeat_id not in data:
            data[repeat_id] = {
                "name": repeat_id,
                "stats": {"total_added": 0, "total_success_30": 0, "total_success_50": 0, "total_success_100": 0}
            }

        repeat_entry = data[repeat_id]
        repeat_stats = repeat_entry.setdefault("stats", {"total_added": 0, "total_success_30": 0,
                                                         "total_success_50": 0, "total_success_100": 0})

        # додаємо або оновлюємо токен
        existing_key = None
        for k in repeat_entry:
            if k in ("name", "stats"):
                continue
            if k.lower() == token_lower:
                existing_key = k
                break
        if isinstance(params, dict):
            for f in ("success_30", "success_50", "success_100"):
                params[f] = False
        if existing_key:
            # оновлюємо значення, якщо відрізняється
            if isinstance(repeat_entry.get(existing_key), dict) and isinstance(params, dict):
                if repeat_entry[existing_key] != params:
                    repeat_entry[existing_key] = params.copy()
                    repeat_entry[existing_key]["added_at"] = datetime.utcnow().isoformat()
                    modified = True
        else:
            # додаємо новий запис
            repeat_entry[latest_key] = params.copy()
            repeat_entry[latest_key]["added_at"] = datetime.utcnow().isoformat()
            repeat_stats["total_added"] = repeat_stats.get("total_added", 0) + 1
            modified = True

    return modified

@dp.message_handler(commands=["info"], state="*")
async def cmd_info(message: types.Message):
    """Виводить статистику по всім користувачам."""
    try:
        data = await read_file(DATA_FILE)
    except FileNotFoundError:
        await message.answer("Файл з даними відсутній.")
        return

    if not data:
        await message.answer("Статистика пуста.")
        return
        # оновлюємо repeat_* (додаємо/оновлюємо повтори)
    try:
        modified = add_duplicates_to_repeat(data)
        if modified:
            retries = 0
            while retries < 5:
                try:
                    with open(DATA_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    break
                except IOError:
                    retries += 1
                    await asyncio.sleep(0.2)
    except Exception as e:
        print("Помилка при add_duplicates_to_repeat:", e)

    lines = []
    for user_id, user_data in data.items():
        name = user_data.get("name", user_id)
        stats = user_data.get("stats", {"total_added": 0, "total_success_30": 0,
                                        "total_success_50": 0, "total_success_100": 0})
        token_keys = [k for k in user_data.keys() if k not in ("stats", "name")]

        # підрахунок середнього максимального росту
        growths = []
        for tk in token_keys:
            info = user_data[tk]
            init_p = float(info.get("initial_price", 0))
            max_p = float(info.get("max_price", 0))
            if init_p and max_p and init_p > 0:
                growths.append((max_p - init_p) / init_p * 100)
        deleted_growths = stats.get("deleted_growths", [])
        growths.extend(deleted_growths)

        active_sum = sum(growths)
        active_count = len(growths)
        avg_growth_total = active_sum / active_count if active_count > 0 else 0

        bins = Counter()
        for g in growths:
            bin_start = int(g // 5) * 5
            bin_end = bin_start + 5
            bins[(bin_start, bin_end)] += 1
        mode_interval = max(bins, key=bins.get) if bins else None

        if mode_interval:
            lines.append(
                f"@{name} (/{user_id}):\n"
                f"  Токенів зараз: {len(token_keys)}\n"
                f"  Додано всього: {stats.get('total_added',0)}\n"
                f"  Успішних (≥1.3×): {stats.get('total_success_30',0)} "
                f"({(stats.get('total_success_30',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Успішних (≥1.5×): {stats.get('total_success_50',0)} "
                f"({(stats.get('total_success_50',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Успішних (≥2×): {stats.get('total_success_100',0)} "
                f"({(stats.get('total_success_100',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Середній макс. ріст: {avg_growth_total:.2f}%\n"
                f"  Мода росту: {mode_interval[0]}–{mode_interval[1]}% (найчастіше)"
            )
        else:
            lines.append(
                f"@{name} (/{user_id}):\n"
                f"  Токенів зараз: {len(token_keys)}\n"
                f"  Додано всього: {stats.get('total_added',0)}\n"
                f"  Успішних (≥1.3×): {stats.get('total_success_30',0)} "
                f"({(stats.get('total_success_30',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Успішних (≥1.5×): {stats.get('total_success_50',0)} "
                f"({(stats.get('total_success_50',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Успішних (≥2×): {stats.get('total_success_100',0)} "
                f"({(stats.get('total_success_100',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Середній макс. ріст: {avg_growth_total:.2f}%\n"
                f"  Мода росту: даних немає"
            )

    response = "\n\n".join(lines)
    await message.answer(response)



EXCLUDED_COMMANDS = {"/start", "/info"}


@dp.message_handler(commands=None, state="*")
async def catch_user_commands(message: types.Message):
    text = message.text.strip()
    if not text.startswith("/"):
        return
    
    cmd = text.split()[0]
    if cmd in EXCLUDED_COMMANDS:
        return

    try:
        data = await read_file(DATA_FILE)
    except FileNotFoundError:
        await message.answer("Файл з даними відсутній.")
        return

    if not data:
        await message.answer("Статистика порожня.")
        return

    user_key = cmd.lstrip("/")
    user_data = data.get(user_key)
    if not user_data:
        await message.answer(f"Немає даних для {cmd}")
        return

    stats = user_data.get("stats", {"total_added": 0})
    token_keys = [k for k in user_data.keys() if k not in ("stats", "name")]
    growths = []
    for tk in token_keys:
        info = user_data[tk]
        init_p = float(info.get("initial_price", 0))
        max_p = float(info.get("max_price", 0))
        if init_p and max_p and init_p > 0:
            growths.append((max_p - init_p) / init_p * 100)
    deleted_growths = stats.get("deleted_growths", [])
    growths.extend(deleted_growths)

    avg_growth_total = sum(growths) / len(growths) if growths else 0

    bins = Counter()
    for g in growths:
        bin_start = int(g // 5) * 5
        bin_end = bin_start + 5
        bins[(bin_start, bin_end)] += 1
    mode_interval = max(bins, key=bins.get) if bins else None

    response = (
        f"@{user_data.get('name', user_key)} ({user_key}):\n"
                f"  Токенов сейчас: {len(token_keys)}\n"
                f"  Добавлено всего: {stats.get('total_added',0)}\n"
                f"  Успешных (≥1.3×): {stats.get('total_success_30',0)} "
                f"({(stats.get('total_success_30',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Успешных (≥1.5×): {stats.get('total_success_50',0)} "
                f"({(stats.get('total_success_50',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Успешных (≥2×): {stats.get('total_success_100',0)} "
                f"({(stats.get('total_success_100',0)/stats.get('total_added',0)*100 if stats.get('total_added',0)>0 else 0):.2f}%)\n"
                f"  Средний макс. рост: {avg_growth_total:.2f}%\n"
                f"  Мода роста: {f'{mode_interval[0]}–{mode_interval[1]}%' if mode_interval else 'даних нету'}"
    )

    await message.answer(response)

    # --- малюємо графік ---
    
    if growths:
        # Перетворюємо прирости у відсотках (додамо 1, щоб уникнути log(0))
        growths_array = np.array(growths) + 1  

        fig, ax = plt.subplots(figsize=(6, 4))

        # Будуємо гістограму з логарифмічною шкалою X
        ax.hist(growths_array, bins=np.logspace(np.log10(growths_array.min()), 
                                                np.log10(growths_array.max()), 20),
                edgecolor="black", alpha=0.7)

        ax.set_xscale("log")  # логарифмічна шкала
        ax.set_title("Распределение приростов (%) (лог шкала)")
        ax.set_xlabel("Прирост (%)")
        ax.set_ylabel("Количество токенов")

        # Робимо красиві підписи осі
        ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
        ax.ticklabel_format(style="plain", axis="x")

        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close(fig)

        await message.answer_photo(photo=buf)



# --- запуск ---
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
