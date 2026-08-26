"""
Конфигурация вёрстки PDF квитанции.

Правьте значения здесь — код (build_receipt_pdf в app.py) подставит их.
Цвета задаются строками вида "#RRGGBB" или "black". Размеры — в пунктах (pt).
"""

# --- Шрифты и тексты ---
FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
FONT_REGULAR_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Размеры шрифтов
TITLE_SIZE = 14          # «Квитанция»
BRAND_SIZE = 14          # «Family Townhouse»
PERIOD_SIZE = 10         # месяц/год
HEAD_SIZE = 10           # «Квартира № …»
TABLE_SIZE = 8           # размер текста таблицы

# --- Тексты шапки ---
TEXT_TITLE = "Квитанция"
TEXT_BRAND = "Family Townhouse"

# --- Логотип ---
LOGO_PATH = "assets/FTH.png"   # относительно backend/ (или абсолютный путь)
LOGO_WIDTH = 34.0              # ширина логотипа, pt
LOGO_HEIGHT = None              # None = пропорционально (по пропорциям файла)

# --- Отступы и поля листа ---
PAGE_TOP_MARGIN = 0
PAGE_BOTTOM_MARGIN = 40
PAGE_LEFT_MARGIN = 20
PAGE_RIGHT_MARGIN = 20
HEADER_SPACER = 10        # пустое пространство над шапкой (для вертикального центрирования бренда)

# Ширина колонок данных (сумма должна быть <= ширины листа минус боковые поля)
COL_WIDTHS = [88, 48, 48, 55, 55, 72, 55, 58, 66]

# --- Цвета (задаются "#RRGGBB") ---
# Фоны
COLOR_TABLE_GRID = "#b8b8b8"       # серые границы таблицы
COLOR_HEADER_BG = "#e6ffea"        # фон шапки таблицы
COLOR_ROW_EVEN = "#ffffff"         # фон чётных строк
COLOR_ROW_ODD = "#f2fff4"          # фон нечётных строк (чередование)
COLOR_TOTAL_BG = "#e6ffea"         # фон итоговой строки

# Тексты
COLOR_TEXT_TITLE = "#666666"       # «Квитанция»
COLOR_TEXT_PERIOD = "#666666"      # месяц/год
COLOR_TEXT_HEAD = "#666666"        # «Квартира № …»
COLOR_BRAND_TEXT = "#7ed98b"       # «Family Townhouse» (основной цвет логотипа)
COLOR_TEXT_HEADER_TABLE = "#666666"  # заголовки столбцов таблицы
COLOR_TEXT_CELL = "#444444"        # текст ячеек данных
COLOR_TEXT_TOTAL = "#666666"       # текст итоговой строки
COLOR_STAMP = "#666666"            # дата формирования внизу

# --- Подписи таблицы ---
COL_Услуга = "Услуга"
COL_Показания = "Показания"
COL_Пред = "Пред."
COL_Послед = "Текущ."
COL_Колво = "Кол-во"
COL_Тариф = "Тариф"
COL_Сумма = "Сумма"
COL_Долг = "Долг"
COL_Переплата = "Переплата"
COL_Коплате = "К оплате"
COL_Итого = "Итого"

# --- Паддинги ячеек таблицы (pt) ---
CELL_TOP_PADDING = 5
CELL_BOTTOM_PADDING = 3
