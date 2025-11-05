from playwright.sync_api import sync_playwright
import time
import random
import json
import os
import re
from datetime import datetime
import hashlib
import shutil

# --- НАСТРОЙКИ ---
OUTPUT_DIR = "output"
PROGRESS_FILE = os.path.join(OUTPUT_DIR, "progress.json")
YML_FILE = os.path.join(OUTPUT_DIR, "paomma_catalog_price.xml")
TEMP_YML_FILE = YML_FILE + ".tmp"

os.makedirs(OUTPUT_DIR, exist_ok=True)

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# --- КОЛЛЕКЦИИ: ID и имя ---
COLLECTIONS = {
    "poilniki": {"name": "Поильники", "id": "952113747654"},
    "prorezyvateli": {"name": "Прорезыватели", "id": "206682998845"},
    "soski": {"name": "Соски", "id": "169064286158"},
    "pustyshki": {"name": "Пустышки", "id": "897379413064"},
    "derzhateli": {"name": "Держатели", "id": "41033353415"},
    "futlyary": {"name": "Футляры", "id": "571209369666"},
    "smesi": {"name": "Контейнеры для смеси", "id": "952891154747"},
    "molokootsosy": {"name": "Молокоотсосы", "id": "918219204990"},
    "butylochki": {"name": "Бутылочки и молокоотсос", "id": "876147046474"}
}

# --- ФИЛЬТРЫ ---
FILTERS = [
    {"name": "Поильники", "url": "https://paomma.ru/catalog/poilniki", "collection": "poilniki"},
    {"name": "Прорезыватели", "url": "https://paomma.ru/catalog/prorezyvateli", "collection": "prorezyvateli"},
    {"name": "Соски", "url": "https://paomma.ru/catalog/antikolikovye-soski", "collection": "soski"},
    {"name": "Пустышки", "url": "https://paomma.ru/catalog/pustyshki", "collection": "pustyshki"},
    {"name": "Держатели", "url": "https://paomma.ru/catalog/derzhateli-dlya-pustyshek", "collection": "derzhateli"},
    {"name": "Футляры", "url": "https://paomma.ru/catalog/konteyner-dlya-pustyshek", "collection": "futlyary"},
    {"name": "Контейнеры для смеси", "url": "https://paomma.ru/catalog/konteynery-dlya-smesi", "collection": "smesi"},
    {"name": "Бутылочки и молокоотсос", "url": "https://paomma.ru/catalog/butylochki-dlya-kormleniya", "collection": "butylochki"},
    {"name": "Молокоотсосы", "url": "https://paomma.ru/catalog/molokootsos", "collection": "molokootsosy"}
]

# --- ПЕРЕВОД ЦВЕТОВ ---
COLOR_TRANSLATION = {
    'Light grey': 'Светло-серый', 'Taupe': 'Тауп', 'Sage': 'Шалфей', 'Zephyr': 'Зефир',
    'Buttercream': 'Сливочный', 'Almond milk': 'Молоко миндаля', 'Navy': 'Темно-синий',
    'Mushroom': 'Грибной', 'Black': 'Черный', 'Hazelnut': 'Лесной орех', 'Cream': 'Кремовый',
    'Beige': 'Бежевый', 'Pink': 'Розовый', 'Grey': 'Серый'
}

def translate_color(en_color):
    ru_color = COLOR_TRANSLATION.get(en_color.strip(), '')
    if ru_color:
        return f"{en_color.strip()} ({ru_color})"
    return en_color.strip()

# --- ЛОГИКА ---
def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'products' in data and isinstance(data['products'], list):
                    log(f"✅ Прогресс загружен: {len(data['products'])} товаров")
                    return data
                else:
                    log("⚠️ Неверный формат файла progress.json — создан пустой прогресс")
                    return {"products": []}
        except (json.JSONDecodeError, Exception) as e:
            log(f"❌ Ошибка чтения progress.json: {e}. Создаём новый файл.")
            return {"products": []}
    return {"products": []}

def save_progress(products):
    try:
        clean = [p for p in products if p.get('vendorCode') and p.get('name') and p.get('link')]
        seen = set()
        unique = []
        for p in clean:
            link = p['link'].strip().split('#')[0]
            if not link or '#order' in link or '#catalog' in link or '#popup-buy' in link or link.endswith('/'):
                continue
            if link not in seen:
                seen.add(link)
                unique.append(p)
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"products": unique}, f, ensure_ascii=False, indent=4)
        log(f"✅ Прогресс сохранён: {len(unique)} товаров")
    except Exception as e:
        log(f"❌ Ошибка сохранения: {e}")

def parse_product_page(page, url):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            log(f"  🔄 Открываем: {url}")
            page.goto(url.strip(), wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)

            result = {
                'name': '', 'price': '0', 'vendorCode': '', 'image': '',
                'additional_images': [], 'color': '', 'material': '', 'age': '',
                'size': '', 'volume': '', 'composition': '', 'handle': '', 'description': '',
                'category_hint': ''
            }

            base = page.evaluate("""(url) => {
                const data = {};
                const nameEl = document.querySelector('h1') || 
                               document.querySelector('.t-store__t-product__title') ||
                               document.querySelector('.t-product__title') ||
                               document.querySelector('.t706__title');
                let name = nameEl ? nameEl.innerText.trim() : '';

                let categoryHint = '';
                if (url.includes('/steklyannaya-gb')) {
                    categoryHint = 'butylochka';
                } else if (url.includes('/molokootsos')) {
                    categoryHint = 'molokootsos';
                } else if (url.includes('/antikolikovye-soski')) {
                    categoryHint = 'soska';
                } else if (url.includes('/pustyshki')) {
                    categoryHint = 'pustyshka';
                } else if (url.includes('/prorezyvateli')) {
                    categoryHint = 'prorezyvatel';
                } else if (url.includes('/poilniki')) {
                    categoryHint = 'poilnik';
                }

                // --- ГЕНЕРАЦИЯ НАЗВАНИЯ ДЛЯ БЕЗЫМЯННЫХ ТОВАРОВ ---
                if (!name || 
                    name.toLowerCase().includes('glass') || 
                    name.toLowerCase().includes('gb') || 
                    name === 'Товары для новорожденных' || 
                    name.toLowerCase().includes('chehol') ||
                    /^\\w+\\s+\\d{3}$/.test(name) ||  // "Zephyr 180"
                    /^Glass\\s+[\\w\\s]+\\d{3}$/.test(name)  // "Glass Almond milk 240"
                ) {
                    if (url.includes('/steklyannaya-gb')) {
                        const match = url.match(/gb(\\d+)/i);
                        const size = match ? match[1] : '300';
                        name = `Стеклянная бутылочка ${size} мл`;
                    } else if (url.includes('/molokootsos')) {
                        name = 'Молокоотсос электрический беспроводной';
                    } else if (url.includes('/antikolikovye-soski')) {
                        name = 'Антиколиковая соска для бутылочки';
                    } else if (url.includes('/pustyshki')) {
                        name = 'Пустышка для новорождённых';
                    } else if (url.includes('/prorezyvateli')) {
                        name = 'Прорезыватель для детей';
                    } else if (url.includes('/poilniki')) {
                        name = 'Поильник для детей';
                    } else if (url.includes('/silikonovyy-chehol') || name.toLowerCase().includes('chehol')) {
                        name = 'Силиконовый чехол для бутылочки';
                    } else if (/^Glass\\s+([\\w\\s]+)\\s+(\\d{3})$/.test(name)) {
                        const match = name.match(/^Glass\\s+([\\w\\s]+)\\s+(\\d{3})$/);
                        const color = match[1].trim();
                        const volume = match[2];
                        name = `Стеклянная бутылочка ${color}, ${volume} мл`;
                    } else if (/^\\w+\\s+\\d{3}$/.test(name)) {
                        const parts = name.trim().split(/\\s+/);
                        const volume = parts.pop();
                        const color = parts.join(' ');
                        if (volume && volume.match(/^\\d{3}$/)) {
                            name = `Пластиковая бутылочка ${color}, ${volume} мл`;
                        }
                    } else if (name.toLowerCase().includes('glass')) {
                        name = 'Стеклянная бутылочка';
                    }
                }

                data.name = name;
                data.categoryHint = categoryHint;

                const skuEl = document.querySelector('.js-store-prod-sku');
                data.vendorCode = skuEl ? skuEl.innerText.replace(/Артикул[:\\s]*/i, '').trim() : '';
                const mainImg = document.querySelector('.t-slds__item_active img');
                data.image = mainImg ? (mainImg.src || mainImg.dataset.original || '') : '';
                const colorBtn = document.querySelector('.t-product__option-item_active [name="Цвет"]');
                data.color = colorBtn ? colorBtn.value.trim().split(':')[0].split('/catalog')[0] : 'Не указан';
                const materialBtn = document.querySelector('.t-product__option-item_active [name="Материал"]');
                data.material = materialBtn ? materialBtn.value.trim() : '';
                const descEl = document.querySelector('.t-text, .t-store__t-product__desc');
                data.description = descEl ? descEl.innerText.trim() : '';

                // --- ПАРСИНГ ЦЕНЫ СО СТРАНИЦЫ ТОВАРА ---
                const priceEl = document.querySelector('.t762__price-value.js-store-prod-price-val');
                data.price = priceEl ? priceEl.getAttribute('data-product-price-def') || priceEl.innerText.replace(/[^\\d]/g, '') : '0';

                data.additional_images = Array.from(document.querySelectorAll('.t-slds__item img'))
                    .map(img => img.src || img.dataset.original || '').filter(src => src && src.endsWith('.jpg'));
                return data;
            }""", url)

            result.update({k: v for k, v in base.items() if v})

            tabs = page.evaluate("""() => {
                const res = {};
                const buttons = document.querySelectorAll('.t-store__tabs__item-button');
                const contents = document.querySelectorAll('.t-store__tabs__content');
                buttons.forEach((btn, i) => {
                    const title = btn.getAttribute('data-tab-title')?.trim();
                    if (title && i < contents.length) {
                        res[title.toLowerCase()] = contents[i].innerText.trim();
                    }
                });
                return res;
            }""")

            if 'состав' in tabs or 'материал' in tabs:
                text = tabs.get('состав') or tabs.get('материал')
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                comp = []
                for line in lines:
                    if 'бутылочка' in line.lower() or 'трубочка' in line.lower():
                        val = ':'.join(line.split(':')[1:]).strip()
                        if val:
                            comp.append(val)
                if comp:
                    result['composition'] = ', '.join(comp)

            if 'возраст' in tabs:
                match = re.search(r'\b(\d[+–\-]?\d*\+?)\b', tabs['возраст'])
                if match:
                    age = match.group(1).strip()
                    if 'категория' not in age.lower():
                        result['age'] = age

            if 'размер' in tabs or 'габариты' in tabs:
                text = tabs.get('размер') or tabs.get('габариты')
                dims = {}
                for line in text.split('\n'):
                    line = line.strip()
                    if 'длина' in line.lower():
                        m = re.search(r'\d+[,.]?\d*', line)
                        if m: dims['length'] = m.group(0).replace(',', '.')
                    elif 'ширина' in line.lower():
                        m = re.search(r'\d+[,.]?\d*', line)
                        if m: dims['width'] = m.group(0).replace(',', '.')
                    elif 'высота' in line.lower():
                        m = re.search(r'\d+[,.]?\d*', line)
                        if m: dims['height'] = m.group(0).replace(',', '.')
                if dims:
                    size_parts = []
                    if dims.get('length'):
                        size_parts.append(f"Длина: {dims['length']} см")
                    if dims.get('width'):
                        size_parts.append(f"Ширина: {dims['width']} см")
                    if dims.get('height'):
                        size_parts.append(f"Высота: {dims['height']} см")
                    result['size'] = ', '.join(size_parts)

            if not result['age'] or not result['size']:
                options = page.evaluate("""() => {
                    const opts = {};
                    document.querySelectorAll('.js-product-edition-option').forEach(block => {
                        const id = block.getAttribute('data-edition-option-id')?.trim();
                        const active = block.querySelector('.t-product__option-item_active');
                        if (id && active) opts[id] = active.innerText.trim();
                    });
                    return opts;
                }""")
                if 'Возраст' in options and not result['age']:
                    result['age'] = options['Возраст']
                if 'Объем' in options and not result['volume']:
                    result['volume'] = options['Объем']
                if 'Ручки' in options and not result['handle']:
                    result['handle'] = options['Ручки']

            # --- ИЗВЛЕЧЕНИЕ ОБЪЁМА ИЗ URL, ЕСЛИ НЕТ НА СТРАНИЦЕ ---
            if not result['volume'] or not result['volume'].strip():
                url_match = re.search(r'gb(\d+)', url, re.IGNORECASE)
                if url_match:
                    result['volume'] = f"{url_match.group(1)} мл"

            if not result['vendorCode']:
                hash_input = f"{result['name']}_{url}"
                short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:6].upper()
                result['vendorCode'] = f"PAO_{short_hash}"
                log(f"🔧 Сгенерирован артикул: {result['vendorCode']}")

            if not result['name']:
                log(f"⚠️ Пропущен: {url} — нет названия")
                return None

            log(f"✅ Успешно: {result['name']} | Арт: {result['vendorCode']} | Цена: {result['price']} ₽ | Цвет: {result['color']}")
            return result

        except Exception as e:
            log(f"❌ Ошибка (попытка {attempt+1}): {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(3)
    return None

def parse_catalog_page(page):
    log("🔄 Начинаем парсинг по фильтрам...")
    all_products = []

    for filt in FILTERS:
        try:
            log(f"🔍 Переходим к фильтру: {filt['name']} ({filt['url']})")
            page.goto(filt['url'], timeout=30000)
            page.wait_for_timeout(3000)

            for _ in range(10):
                try:
                    load_more = page.locator("div.js-store-load-more-btn:has-text('Загрузить еще')")
                    if load_more.count() == 0 or not load_more.is_visible():
                        break
                    before_count = len(page.query_selector_all('.js-product, .t-store__card, .t-product'))
                    load_more.click()
                    page.wait_for_timeout(3000)
                    after_count = len(page.query_selector_all('.js-product, .t-store__card, .t-product'))
                    if after_count <= before_count:
                        break
                except Exception as e:
                    log(f"  ⚠️ Ошибка при подгрузке: {e}")
                    break

            collection_id = filt['collection']

            products = page.evaluate("""(collectionId) => {
                const cards = document.querySelectorAll('.js-product, .t-store__card, .t-product');
                const result = [];
                
                for (let i = 0; i < cards.length; i++) {
                    const card = cards[i];
                    
                    const nameEl = card.querySelector('.js-product-name, .t-store__card__title, h3, .t-product__title');
                    const skuEl = card.querySelector('.js-store-prod-sku, .t-store__card__sku');
                    const linkEl = card.querySelector('a');
                    const imgEl = card.querySelector('.js-product-img, img');

                    if (!nameEl || !linkEl) continue;

                    let name = nameEl ? nameEl.innerText.trim() : '';

                    // --- ГЕНЕРАЦИЯ НАЗВАНИЯ В КАТАЛОГЕ ---
                    if (name && /^Glass\\s+[\\w\\s]+\\d{3}$/.test(name)) {
                        const match = name.match(/^Glass\\s+([\\w\\s]+)\\s+(\\d{3})$/);
                        if (match) {
                            const color = match[1].trim();
                            const volume = match[2];
                            name = `Стеклянная бутылочка ${color}, ${volume} мл`;
                        }
                    } else if (name && /^\\w+\\s+\\d{3}$/.test(name)) {
                        const parts = name.trim().split(/\\s+/);
                        const volume = parts.pop();
                        const color = parts.join(' ');
                        if (volume && volume.match(/^\\d{3}$/)) {
                            name = `Пластиковая бутылочка ${color}, ${volume} мл`;
                        }
                    }

                    let vendorCode = skuEl ? skuEl.innerText.replace(/Артикул[:\\s]*/i, '').trim() : '';
                    const link = linkEl.href.trim();
                    const image = imgEl ? (imgEl.dataset.original || imgEl.src || '') : '';

                    // --- ПАРСИНГ ЦЕНЫ: приоритет — data-product-price-def ---
                    let price = '0';
                    const priceValEl = card.querySelector('.js-product-price.js-store-prod-price-val');
                    if (priceValEl) {
                        // Пытаемся получить из data-атрибута
                        const dataPrice = priceValEl.getAttribute('data-product-price-def');
                        if (dataPrice && dataPrice !== '0') {
                            price = dataPrice;
                        } else {
                            // Если data нет — пробуем текст
                            const text = priceValEl.innerText.trim();
                            const match = text.match(/\\d+/);
                            if (match) price = match[0];
                        }
                    }

                    // Если цена всё ещё 0 — пробуем парсить из <strong> от 465 ₽
                    if (price === '0') {
                        const descrEl = card.querySelector('.js-store-prod-descr');
                        if (descrEl) {
                            const strongEl = descrEl.querySelector('strong');
                            if (strongEl) {
                                const text = strongEl.innerText.trim();
                                const match = text.match(/\\d+/);
                                if (match) {
                                    price = match[0];
                                }
                            }
                        }
                    }

                    // --- ФИЛЬТР ДУБЛЕЙ И ЯКОРЕЙ ---
                    if (!link || 
                        link.includes('#order') || 
                        link.includes('#catalog') || 
                        link.includes('#popup-buy') || 
                        link.endsWith('#')) {
                        continue;
                    }

                    let final_collection = collectionId;
                    if (name.toLowerCase().includes('молокоотсос')) {
                        final_collection = 'molokootsosy';
                        if (!vendorCode) {
                            vendorCode = 'MOLOKOOSC_001';
                        }
                    }

                    // --- ПЕРЕДАЧА ОБЪЁМА ИЗ НАЗВАНИЯ ---
                    let volume = '';
                    const vol_match = name.match(/(\\d{3})\\s*мл|(\\d{3})$/);
                    if (vol_match) {
                        volume = vol_match[1] || vol_match[2];
                        if (volume) volume += ' мл';
                    }

                    result.push({
                        name,
                        vendorCode,
                        price,
                        link,
                        image,
                        collection: final_collection,
                        volume: volume
                    });
                }
                return result;
            }""", collection_id)

            log(f"  ✅ Найдено {len(products)} товаров в категории {filt['name']}")
            all_products.extend(products)

        except Exception as e:
            log(f"❌ Ошибка при парсинге фильтра {filt['name']}: {e}")
            continue

    log(f"📦 Всего найдено {len(all_products)} товаров по всем фильтрам")
    return all_products

def get_collection_images(products):
    coll_images = {}
    for coll_key in COLLECTIONS.keys():
        for prod in products:
            if prod.get('collection') == coll_key and coll_key not in coll_images:
                if prod.get('image'):
                    coll_images[coll_key] = prod['image'].strip()
                break
    return coll_images

def get_collection_description(collection_id, products):
    key_features = {
        "poilniki": "Поильники Paomma с защитой от протекания, силиконовой ручкой и антисорбционным клапаном. Подходят для детей от 6 месяцев. Без БФА и фталатов.",
        "prorezyvateli": "Прорезыватели Paomma из 100% пищевого силикона. Анатомическая форма, мягкие текстуры, безопасные красители. Помогают при прорезывании зубов.",
        "soski": "Соски для бутылочек Paomma с антиколиковой системой, потоками S/M/L. Из 100% пищевого силикона. Подходят для новорождённых.",
        "pustyshki": "Пустышки Paomma из силикона и латекса. Анатомическая форма, вентиляционные отверстия, гипоаллергенный материал. Подходят с рождения.",
        "derzhateli": "Держатели для пустышек Paomma с безопасным замком, регулируемой длиной. Из гипоаллергенных материалов. Не теряются.",
        "futlyary": "Футляры для пустышек Paomma герметичные, компактные. Защищают от загрязнений. Удобны в поездках.",
        "smesi": "Контейнеры для смеси Paomma с герметичными отсеками, маркировкой. Удобны для хранения и транспортировки.",
        "molokootsosy": "Молокоотсосы Paomma с эргономичным дизайном, мягкими вставками. Безопасны для кожи. Эффективны и комфортны.",
        "butylochki": "Бутылочки Paomma с антиколиковой системой, широким горлышком. Из полипропилена. Без БФА. Подходят с рождения."
    }
    return key_features.get(collection_id, f"Коллекция: {COLLECTIONS.get(collection_id, {}).get('name', 'Товары')}")

def is_feed_valid(lines):
    """Проверяет, что фид имеет базовую структуру"""
    content = '\n'.join(lines)
    required = ['<yml_catalog', '<shop>', '<name>Paomma</name>', '<offers>', '</yml_catalog>']
    for req in required:
        if req not in content:
            return False
    return True

def generate_yml(products):
    log("📝 Генерация YML-фида...")

    real_urls = {}
    for filt in FILTERS:
        coll_id = filt.get('collection')
        if coll_id and coll_id in COLLECTIONS:
            real_urls[COLLECTIONS[coll_id]['name']] = filt['url'].strip()

    if 'Молокоотсосы' not in real_urls:
        real_urls['Молокоотсосы'] = "https://paomma.ru/catalog/molokootsos"

    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    header_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<yml_catalog date="{current_date}">',
        '  <shop>',
        '    <name>Paomma</name>',
        '    <company>Paomma</company>',
        '    <url>https://paomma.ru</url>',
        '    <platform>Tilda</platform>',
        '    <currencies>',
        '      <currency id="RUB" rate="1"/>',
        '    </currencies>',
        '    <categories>'
    ]

    cat_map = {
        "Поильники": "952113747654",
        "Прорезыватели": "206682998845",
        "Соски": "169064286158",
        "Пустышки": "897379413064",
        "Держатели": "41033353415",
        "Футляры": "571209369666",
        "Контейнеры для смеси": "952891154747",
        "Молокоотсосы": "918219204990",
        "Бутылочки и молокоотсос": "876147046474"
    }

    for name, cat_id in cat_map.items():
        header_lines.append(f'      <category id="{cat_id}">{name}</category>')

    header_lines += [
        '    </categories>',
        '    <offers>'
    ]

    footer_lines = [
        '    </offers>',
        '    <collections>'
    ]

    coll_images = get_collection_images(products)

    for coll_key, coll_data in COLLECTIONS.items():
        footer_lines.append(f'      <collection id="{coll_key}">')
        footer_lines.append(f'        <name>{coll_data["name"]}</name>')
        
        real_url = real_urls.get(coll_data["name"])
        if not real_url:
            log(f"⚠️ Не найдена ссылка для коллекции: {coll_data['name']}")
            real_url = f"https://paomma.ru/{coll_key}"
        
        url_cdata = f"<![CDATA[{real_url}]]>"
        footer_lines.append(f'        <url>{url_cdata}</url>')
        
        if coll_images.get(coll_key):
            footer_lines.append(f'        <picture>{coll_images[coll_key]}</picture>')
        
        coll_desc = get_collection_description(coll_key, products)
        footer_lines.append(f'        <description>{coll_desc}</description>')
        footer_lines.append('      </collection>')

    footer_lines += [
        '    </collections>',
        '  </shop>',
        '</yml_catalog>'
    ]

    # --- Сборка фида ---
    offer_lines = []
    used_ids = set()

    for prod in products:
        try:
            if not prod.get('vendorCode') or not prod.get('name'):
                continue

            category_id = "876147046474"
            if "поильник" in prod['name'].lower():
                category_id = "952113747654"
            elif "прорезыватель" in prod['name'].lower():
                category_id = "206682998845"
            elif "соска" in prod['name'].lower():
                category_id = "169064286158"
            elif "пустышка" in prod['name'].lower():
                category_id = "897379413064"
            elif "держатель" in prod['name'].lower():
                category_id = "41033353415"
            elif "футляр" in prod['name'].lower() or "контейнер для пустышек" in prod['name'].lower():
                category_id = "571209369666"
            elif "смеси" in prod['name'].lower():
                category_id = "952891154747"
            elif "молокоотсос" in prod['name'].lower():
                category_id = "918219204990"

            base_id = prod["vendorCode"]
            color_part = ""
            if prod.get('color') and prod['color'] != 'Не указан':
                clean_color = prod['color'].split(':')[0].split('/catalog')[0].strip()
                clean_color = re.sub(r'[^a-z0-9]', '', clean_color.lower())
                color_part = f"_{clean_color}"

            unique_id = base_id + color_part

            if unique_id in used_ids:
                suffix = 1
                temp_id = f"{unique_id}_{suffix}"
                while temp_id in used_ids:
                    suffix += 1
                    temp_id = f"{unique_id}_{suffix}"
                unique_id = temp_id

            used_ids.add(unique_id)

            # --- ПРОВЕРКА ЦЕНЫ ---
            try:
                price_val = int(prod.get('price', '0').strip())
                if price_val <= 0:
                    price_val = 1
            except (ValueError, TypeError):
                price_val = 1

            offer = [
                f'      <offer id="{unique_id}" available="true">',
                f'        <name>{prod["name"]}</name>',
                f'        <vendor>Paomma</vendor>',
                f'        <vendorCode>{prod["vendorCode"]}</vendorCode>',
                f'        <model>{prod["vendorCode"]}</model>',
                f'        <price>{price_val}</price>',
                f'        <currencyId>RUB</currencyId>',
                f'        <categoryId>{category_id}</categoryId>'
            ]

            url_cdata = f"<![CDATA[{prod['link'].strip()}]]>"
            offer.append(f'        <url>{url_cdata}</url>')

            if prod.get('image'):
                offer.append(f'        <picture>{prod["image"].strip()}</picture>')
            for img in prod.get('additional_images', []):
                if img and img != prod.get('image'):
                    offer.append(f'        <picture>{img.strip()}</picture>')

            if prod.get('color') and prod['color'] != 'Не указан':
                clean_color = prod['color'].split(':')[0].strip()
                offer.append(f'        <param name="Цвет">{translate_color(clean_color)}</param>')
            if prod.get('size'):
                offer.append(f'        <param name="Размер">{prod["size"]}</param>')
            if prod.get('volume'):
                offer.append(f'        <param name="Объём">{prod["volume"]}</param>')
            if prod.get('material'):
                offer.append(f'        <param name="Материал">{prod["material"]}</param>')
            if prod.get('age'):
                offer.append(f'        <param name="Возраст">{prod["age"]}</param>')
            if prod.get('handle'):
                offer.append(f'        <param name="Ручки">{prod["handle"]}</param>')
            if prod.get('composition'):
                offer.append(f'        <param name="Состав">{prod["composition"]}</param>')

            coll_id = prod.get('collection')
            if coll_id and coll_id in COLLECTIONS:
                offer.append(f'        <param name="collection">{coll_id}</param>')
                offer.append(f'        <collectionId>{coll_id}</collectionId>')

            # --- DESCRIPTION: обработка по ключевым словам ---
            desc_parts = []
            name = prod.get('name', '').lower()

            if prod.get('description') and prod['description'].strip():
                raw_desc = prod['description'].strip()
                clean_desc = re.sub(r'Артикул[:\s]+[A-Z0-9]+[\s]*', '', raw_desc, flags=re.IGNORECASE)
                clean_desc = re.sub(r'[\t\n\r]+', '. ', clean_desc)

                keywords = sorted([
                    'Диаметр горлышка', 'Диаметр широкой части бутылочки', 'Диаметр соски',
                    'Особенности', 'Высота', 'Поток', 'Материал соски', 'Материал бутылочки',
                    'Объем', 'Питание', 'Материал изделия', 'Тип сцеживания', 'Аккумулятор',
                    'Длина упаковки', 'Высота упаковки', 'Ширина упаковки', 'размер'
                ], key=len, reverse=True)

                escaped = [re.escape(kw) for kw in keywords]
                pattern = r'(' + '|'.join(escaped) + r')\.\s*([^.]*)'

                def replace_match(m):
                    key = m.group(1)
                    value = m.group(2).strip()
                    return f"{key}: {value}"

                clean_desc = re.sub(pattern, replace_match, clean_desc)

                raw_params = [p.strip() for p in re.split(r'[.]', clean_desc) if p.strip()]
                for param in raw_params:
                    if 'артикул' in param.lower():
                        continue
                    if ':' in param and param.count(':') == 1:
                        desc_parts.append(param)
                    elif param.strip():
                        desc_parts.append(param)
            else:
                volume = prod.get('volume', '')
                if "стеклянная бутылочка" in name:
                    desc = f"Стеклянная бутылочка Paomma объёмом {volume}. Изготовлена из прочного стекла, подходит для новорождённых. Антиколиковая система. Подходит для стерилизации."
                elif "пластиковая бутылочка" in name or "бутылочка" in name:
                    desc = f"Пластиковая бутылочка Paomma объёмом {volume}. Изготовлена из 100% полипропилена, подходит для новорождённых. Антиколиковая система. Удобна в уходе."
                else:
                    desc = f"Качественный товар для детей от бренда Paomma. Подходит с рождения."
                desc_parts.append(desc)

            description = ". ".join(desc_parts).strip()
            if description and not description.endswith('.'):
                description += "."
            description = re.sub(r'\.{2,}', '.', description)
            description = description.replace('&', '&amp;').replace('<', '<').replace('>', '>')
            offer.append(f'        <description>{description}</description>')

            # --- SALES_NOTES ---
            sales_notes_parts = []
            if prod.get('color') and prod['color'] != 'Не указан':
                clean_color = prod['color'].split(':')[0].strip()
                sales_notes_parts.append(f"Цвет: {translate_color(clean_color)}")
            if prod.get('volume'):
                sales_notes_parts.append(f"Объём: {prod['volume']}")
            if prod.get('age'):
                sales_notes_parts.append(f"Возраст: {prod['age']}")
            if prod.get('material'):
                sales_notes_parts.append(f"Материал: {prod['material']}")
            if not sales_notes_parts:
                sales_notes_parts.append("Официальный сайт Paomma")
            else:
                sales_notes_parts.append("Официальный сайт Paomma")

            sales_notes = ". ".join(sales_notes_parts) + "."
            offer.append(f'        <sales_notes>{sales_notes}</sales_notes>')
            offer.append('      </offer>')

            offer_lines.extend(offer)

        except Exception as e:
            log(f"❌ Ошибка при генерации offer для {prod.get('name', 'unknown')}: {e}")
            continue

    # --- Формирование финального фида ---
    full_lines = header_lines + offer_lines + footer_lines

    if not is_feed_valid(full_lines):
        log("❌ Фид не прошёл проверку валидности — не сохранён")
        return

    # --- Резервная копия ---
    if os.path.exists(YML_FILE):
        backup_name = YML_FILE + ".backup."
        shutil.copy2(YML_FILE, backup_name)
        log(f"📁 Создана резервная копия: {backup_name}")

    # --- Атомарная запись ---
    try:
        with open(TEMP_YML_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(full_lines))
        os.replace(TEMP_YML_FILE, YML_FILE)
        log(f"✅ YML-фид успешно сохранён: {YML_FILE}")
    except Exception as e:
        log(f"❌ Ошибка при сохранении фида: {e}")

# --- ЗАПУСК ---
if __name__ == "__main__":
    log("🚀 Запуск парсера paomma.ru")
    progress = load_progress()
    all_products = progress["products"]
    seen_links = {p['link'].strip() for p in all_products}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        try:
            log("📦 Начинаем парсинг по фильтрам...")
            product_list = parse_catalog_page(page)
            new_items = [item for item in product_list if item['link'].strip() not in seen_links]
            log(f"🆕 Новых товаров для парсинга: {len(new_items)}")

            for i, item in enumerate(new_items, 1):
                log(f"➡️ Товар {i}/{len(new_items)}: {item['link']}")
                full_data = parse_product_page(page, item['link'])
                if full_data:
                    full_data.update({
                        'name': item['name'],
                        'price': item['price'] or full_data.get('price', '0'),  # ← Приоритет: цена из каталога
                        'link': item['link'],
                        'image': item['image'] or full_data.get('image', ''),
                        'collection': item.get('collection'),
                        'volume': item.get('volume') or full_data.get('volume', '')
                    })                    
                    all_products.append(full_data)
                    save_progress(all_products)
                time.sleep(random.uniform(1.0, 2.5))

            generate_yml(all_products)
            log(f"🎉 Готово! Всего: {len(all_products)}")

        except Exception as e:
            log(f"❌ Ошибка: {e}")
            save_progress(all_products)
        finally:
            browser.close()
            log("✅ Браузер закрыт.")

    log("✅ Готово! Проверьте папку 'output'.")
