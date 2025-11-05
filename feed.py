import os
import re
import time
import random
from datetime import datetime
from playwright.sync_api import sync_playwright
import xml.etree.ElementTree as ET
from xml.dom import minidom

OUTPUT_DIR = "output"
BASE_URL = "https://willfood.pro/"
CATALOG_URL = "https://willfood.pro/#calculator"
XML_FILE = os.path.join(OUTPUT_DIR, "willfood_catalog.xml")

PROGRAMS = {
    "900": {"id": 1, "name": "Программа 900 ккал", "image": "/assets/img/programmes/900.webp"},
    "1200": {"id": 2, "name": "Программа 1200 ккал", "image": "/assets/img/programmes/1200.webp"},
    "1500": {"id": 3, "name": "Программа 1500 ккал", "image": "/assets/img/programmes/1500.webp"},
    "1800": {"id": 4, "name": "Программа 1800 ккал", "image": "/assets/img/programmes/1800.webp"},
    "2500": {"id": 5, "name": "Программа 2500 ккал", "image": "/assets/img/programmes/2500.webp"},
    "3200": {"id": 6, "name": "Программа 3200 ккал", "image": "/assets/img/programmes/2500.webp"},
    "detox": {"id": 7, "name": "Программа Detox", "image": "/assets/img/programmes/detox.webp"}
}

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def random_wait(min_ms=2000, max_ms=5000, label=""):
    '''Случайная задержка для имитации человека'''
    wait_ms = random.randint(min_ms, max_ms)
    if label:
        log(f"   ⏳ {label}... {wait_ms}мс")
    time.sleep(wait_ms / 1000)

def mouse_move_random(page):
    '''Случайное движение мыши'''
    try:
        x = random.randint(0, 1000)
        y = random.randint(0, 600)
        page.mouse.move(x, y)
        page.wait_for_timeout(random.randint(100, 500))
    except:
        pass

def find_real_robot_button(page):
    '''V5.12: Детект реальной кнопки "Я не робот"'''

    try:
        log("\n🤖 Поиск РЕАЛЬНОЙ кнопки 'Я не робот'...")

        all_buttons = page.query_selector_all('div[onclick]')
        log(f"   Найдено div[onclick]: {len(all_buttons)} элементов")

        real_buttons = []

        for idx, btn in enumerate(all_buttons):
            try:
                text = btn.inner_text().lower()

                if 'не робот' not in text:
                    continue

                is_hidden = page.evaluate('''(el) => {
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none') return true;
                    if (el.style.display === 'none') return true;
                    if (style.visibility === 'hidden') return true;
                    if (style.opacity === '0') return true;
                    return false;
                }''', btn)

                if is_hidden:
                    log(f"   [{idx}] ❌ СКРЫТА")
                    continue

                is_visible = page.evaluate('''(el) => {
                    return el.offsetHeight > 0 && el.offsetWidth > 0;
                }''', btn)

                if not is_visible:
                    log(f"   [{idx}] ❌ Невидима в DOM")
                    continue

                log(f"   [{idx}] ✅ РЕАЛЬНАЯ КНОПКА!")
                real_buttons.append(btn)

            except:
                continue

        if len(real_buttons) == 0:
            log("   ⚠️ Реальная кнопка не найдена")
            return None

        log(f"   ✅ Выбрана кнопка из {len(real_buttons)} вариантов")
        return real_buttons[0]

    except Exception as e:
        log(f"   ❌ Ошибка: {e}")
        return None

def safe_click(elem, page, name="", max_retries=2):
    '''Надежный клик'''

    for attempt in range(max_retries):
        try:
            log(f"   🖱️  Кликаем {name}...")

            mouse_move_random(page)
            random_wait(800, 1500)

            try:
                page.keyboard.press('Escape')
            except:
                pass

            random_wait(300, 800)

            try:
                page.evaluate('''(el) => {
                    el.scrollIntoView(false);
                }''', elem)
                random_wait(1000, 2000)
            except:
                if attempt < max_retries - 1:
                    random_wait(2000, 3000)
                    continue

            try:
                page.evaluate('(el) => el.click()', elem)
                log(f"   ✅ OK")
                return True
            except:
                elem.click()
                log(f"   ✅ OK")
                return True

        except Exception as e:
            if attempt < max_retries - 1:
                random_wait(3000, 5000)

    return False

def parse(page):
    log("✅ Все ссылки ведут на https://willfood.pro/#calculator\n")

    all_products = []

    try:
        log("📍 Переход на сайт...")
        response = page.goto(BASE_URL, timeout=60000)
        log(f"   Status: {response.status if response else 'No response'}")

        random_wait(3000, 5000, "Инициализация")

        # Поиск реальной кнопки робота
        real_button = find_real_robot_button(page)

        if real_button:
            safe_click(real_button, page, "реальную кнопку робота", max_retries=2)
            random_wait(5000, 8000, "Проверка робота")
        else:
            log("   ℹ️ Кнопка робота не найдена")

        log("\n⏳ Загрузка контента...")
        random_wait(5000, 8000, "Ожидание контента")

        log("\n🔍 Ищем карточки...")
        cards = page.query_selector_all('.program-card-wrapper')

        if len(cards) == 0:
            log("   ❌ Карточки не найдены")
            return []

        log(f"📦 Найдено {len(cards)} карточек")

        for card_idx, card in enumerate(cards):
            try:
                ptype = card.get_attribute('data-type')
                if not ptype or ptype not in PROGRAMS:
                    continue

                info = PROGRAMS[ptype]
                log(f"\n🔄 [{card_idx+1}] {info['name']}")

                if not safe_click(card, page, ptype, max_retries=2):
                    continue

                random_wait(2500, 3500, "Открытие карточки")

                # Выбираем вариант
                if ptype in ["2500", "3200"]:
                    sel = card.query_selector(f'button[data-type="{ptype}"]')
                    if sel:
                        safe_click(sel, page, f"var-{ptype}", max_retries=1)
                        random_wait(1500, 2000)

                # Цена
                try:
                    pe = page.query_selector('.var-pPriceDay')
                    if pe:
                        pt = re.search(r'\d+', pe.inner_text())
                        price = pt.group(0) if pt else "0"
                    else:
                        price = "0"
                    log(f"   💰 {price} ₽")
                except:
                    price = "0"

                if price == "0":
                    continue

                # Кнопка дней
                btns = page.query_selector_all('.nutrition-duration button')
                if btns:
                    if not safe_click(btns[0], page, "дни", max_retries=1):
                        continue

                    random_wait(1000, 1500, "Выбор дней")

                    days = btns[0].get_attribute('data-days') or "1"

                    try:
                        te = page.query_selector('.var-pPriceTotal')
                        tp = re.sub(r'[^0-9]', '', te.inner_text()) if te else str(int(price) * int(days))
                    except:
                        tp = str(int(price) * int(days))

                    name = f"{info['name']} на {days}д"
                    vid = f"WF_{info['id']:02d}_{days}D"

                    product = {
                        'id': vid,
                        'name': name,
                        'price': tp,
                        'oldprice': str(int(int(tp) * 1.05)) if tp != "0" else None,
                        'categoryId': str(info['id']),
                        'image': BASE_URL.rstrip('/') + info['image'],
                        'url': CATALOG_URL,  # ⭐ ССЫЛКА НА #calculator
                        'available': 'true',
                        'ptype': ptype
                    }

                    all_products.append(product)
                    log(f"   ✅ {name}: {tp}₽")

            except Exception as e:
                continue

        return all_products

    except Exception as e:
        log(f"❌ {e}")
        return []

def generate_xml(products):
    log("\n📝 V5.13: Генерирую XML...")

    if not products:
        log("   ⚠️ Нет товаров")
        return

    yml_catalog = ET.Element('yml_catalog', date=datetime.now().strftime("%Y-%m-%d %H:%M"))
    shop = ET.SubElement(yml_catalog, 'shop')

    ET.SubElement(shop, 'name').text = 'WILL FOOD'
    ET.SubElement(shop, 'company').text = 'WILL FOOD Самара'
    ET.SubElement(shop, 'url').text = BASE_URL
    ET.SubElement(shop, 'platform').text = 'Доставка здорового питания'

    currencies = ET.SubElement(shop, 'currencies')
    ET.SubElement(currencies, 'currency', id='RUB', rate='1')

    categories = ET.SubElement(shop, 'categories')
    for prog_data in PROGRAMS.values():
        category = ET.SubElement(categories, 'category', id=str(prog_data['id']))
        category.text = prog_data['name']

    offers = ET.SubElement(shop, 'offers')

    for product in products:
        offer = ET.SubElement(offers, 'offer', id=product['id'], available=product['available'])

        ET.SubElement(offer, 'name').text = product['name']
        ET.SubElement(offer, 'vendorCode').text = product['id']
        # ⭐ V5.13: ВСЕ ссылки ведут на #calculator
        ET.SubElement(offer, 'url').text = product['url']
        ET.SubElement(offer, 'price').text = product['price']

        if product['oldprice']:
            ET.SubElement(offer, 'oldprice').text = product['oldprice']

        ET.SubElement(offer, 'currencyId').text = 'RUB'
        ET.SubElement(offer, 'categoryId').text = product['categoryId']
        ET.SubElement(offer, 'picture').text = product['image']
        ET.SubElement(offer, 'sales_notes').text = 'Доставка здорового питания'

    # ⭐ V5.13: Collections тоже ведут на #calculator
    collections_elem = ET.SubElement(shop, 'collections')
    for ptype, prog_data in PROGRAMS.items():
        coll = ET.SubElement(collections_elem, 'collection', id=str(prog_data['id']))
        ET.SubElement(coll, 'name').text = prog_data['name']
        ET.SubElement(coll, 'url').text = CATALOG_URL  # ⭐ #calculator
        ET.SubElement(coll, 'description').text = prog_data['name']
        ET.SubElement(coll, 'picture').text = BASE_URL.rstrip('/') + prog_data['image']

    rough_string = ET.tostring(yml_catalog, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    xml_content = '\n'.join(lines)

    with open(XML_FILE, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    log(f"   ✅ XML: {len(products)} товаров")

if __name__ == "__main__":
    log("\n" + "="*80)
    log("="*80 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        ).new_page()

        try:
            products = parse(page)
            generate_xml(products)
            log(f"\n🎉 Готово!")
            log(f"📊 Товаров: {len(products)}")
            if len(products) == 7:
                log("✅✅✅ ВСЕ 7 ТОВАРОВ!")
        finally:
            browser.close()
