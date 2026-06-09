import random
import os

CARD_FILE_MAP = {
    "Шут": "shut.jpg", "Маг": "mag.jpg", "Верховная Жрица": "zhrica.jpg",
    "Императрица": "impress.jpg", "Император": "imperor.jpg", "Иерофант": "hierofant.jpg",
    "Влюбленные": "lovers.jpg", "Колесница": "chariot.jpg", "Сила": "strenghch.jpg",
    "Отшельник": "hermit.jpg", "Колесо Фортуны": "fortune.jpg", "Справедливость": "justise.jpg",
    "Повешенный": "hanged_men.jpg", "Смерть": "death.jpg", "Умеренность": "temperam.jpg",
    "Дьявол": "devil.jpg", "Башня": "tower.jpg", "Звезда": "stare.jpg",
    "Луна": "moon.jpg", "Солнце": "sun.jpg", "Суд": "sud.jpg", "Мир": "world.jpg",

    "Туз Кубков": "cups01.jpg", "Двойка Кубков": "cups02.jpg", "Тройка Кубков": "cups03.jpg",
    "Четверка Кубков": "cups04.jpg", "Пятерка Кубков": "cups05.jpg", "Шестерка Кубков": "cups06.jpg",
    "Семерка Кубков": "cups07.jpg", "Восьмерка Кубков": "cups08.jpg", "Девятка Кубков": "cups09.jpg",
    "Десятка Кубков": "cups10.jpg", "Паж Кубков": "cups11.jpg", "Рыцарь Кубков": "cups12.jpg",
    "Королева Кубков": "cups13.jpg", "Король Кубков": "cups14.jpg",

    "Туз Пентаклей": "pents01.jpg", "Двойка Пентаклей": "pents02.jpg", "Тройка Пентаклей": "pents03.jpg",
    "Четверка Пентаклей": "pents04.jpg", "Пятерка Пентаклей": "pents05.jpg", "Шестерка Пентаклей": "pents06.jpg",
    "Семерка Пентаклей": "pents07.jpg", "Восьмерка Пентаклей": "pents08.jpg", "Девятка Пентаклей": "pents09.jpg",
    "Десятка Пентаклей": "pents10.jpg", "Паж Пентаклей": "pents11.jpg", "Рыцарь Пентаклей": "pents12.jpg",
    "Королева Пентаклей": "pents13.jpg", "Король Пентаклей": "pents14.jpg",

    "Туз Мечей": "swords01.jpg", "Двойка Мечей": "swords02.jpg", "Тройка Мечей": "swords03.jpg",
    "Четверка Мечей": "swords04.jpg", "Пятерка Мечей": "swords05.jpg", "Шестерка Мечей": "swords06.jpg",
    "Семерка Мечей": "swords07.jpg", "Восьмерка Мечей": "swords08.jpg", "Девятка Мечей": "swords09.jpg",
    "Десятка Мечей": "swords10.jpg", "Паж Мечей": "swords11.jpg", "Рыцарь Мечей": "swords12.jpg",
    "Королева Мечей": "swords13.jpg", "Король Мечей": "swords14.jpg",

    "Туз Жезлов": "wands01.jpg", "Двойка Жезлов": "wands02.jpg", "Тройка Жезлов": "wands03.jpg",
    "Четверка Жезлов": "wands04.jpg", "Пятерка Жезлов": "wands05.jpg", "Шестерка Жезлов": "wands06.jpg",
    "Семерка Жезлов": "wands07.jpg", "Восьмерка Жезлов": "wands08.jpg", "Девятка Жезлов": "wands09.jpg",
    "Десятка Жезлов": "wands10.jpg", "Паж Жезлов": "wands11.jpg", "Рыцарь Жезлов": "wands12.jpg",
    "Королева Жезлов": "wands13.jpg", "Король Жезлов": "wands14.jpg",
}

def get_zodiac(date_str: str) -> str:
    try:
        d, m, _ = map(int, date_str.split('.'))
        if (m == 3 and d >= 21) or (m == 4 and d <= 19): return "Овен"
        if (m == 4 and d >= 20) or (m == 5 and d <= 20): return "Телец"
        if (m == 5 and d >= 21) or (m == 6 and d <= 20): return "Близнецы"
        if (m == 6 and d >= 21) or (m == 7 and d <= 22): return "Рак"
        if (m == 7 and d >= 23) or (m == 8 and d <= 22): return "Лев"
        if (m == 8 and d >= 23) or (m == 9 and d <= 22): return "Дева"
        if (m == 9 and d >= 23) or (m == 10 and d <= 22): return "Весы"
        if (m == 10 and d >= 23) or (m == 11 and d <= 21): return "Скорпион"
        if (m == 11 and d >= 22) or (m == 12 and d <= 21): return "Стрелец"
        if (m == 12 and d >= 22) or (m == 1 and d <= 19): return "Козерог"
        if (m == 1 and d >= 20) or (m == 2 and d <= 18): return "Водолей"
        if (m == 2 and d >= 19) or (m == 3 and d <= 20): return "Рыбы"
    except:
        return "Неизвестно"
    return "Неизвестно"

def get_random_cards(count: int = 1):
    names = list(CARD_FILE_MAP.keys())
    selected = random.sample(names, count)
    result = []
    for name in selected:
        is_reversed = random.random() > 0.5
        result.append({
            "name": name,
            "is_reversed": is_reversed,
            "position": "Перевернутая" if is_reversed else "Прямая"
        })
    return result

def get_card_path(card_name: str, is_reversed: bool = False):
    filename = CARD_FILE_MAP.get(card_name, "shut.jpg")
    folder = "reversed" if is_reversed else "upright"
    return os.path.join("cards_images", folder, filename)