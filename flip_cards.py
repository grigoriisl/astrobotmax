import os
from PIL import Image

# Пути к папкам
upright_dir = r"C:\tarot-bot\cards_images\upright"
reversed_dir = r"C:\tarot-bot\cards_images\reversed"

# Создаем папку, если её вдруг нет
if not os.path.exists(reversed_dir):
    os.makedirs(reversed_dir)

print("Начинаю переворачивать карты...")

for filename in os.listdir(upright_dir):
    # Работаем только с jpg файлами
    if filename.lower().endswith(".jpg"):
        file_path = os.path.join(upright_dir, filename)

        try:
            # Открываем изображение
            with Image.open(file_path) as img:
                # Поворачиваем на 180 градусов
                inverted_img = img.rotate(180)
                # Сохраняем в папку reversed с тем же именем
                inverted_img.save(os.path.join(reversed_dir, filename))
                print(f"Готово: {filename}")
        except Exception as e:
            print(f"Ошибка с файлом {filename}: {e}")

print("\nВсе карты успешно перевернуты!")