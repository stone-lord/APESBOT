import os
import re
import time
import logging
from typing import Dict, List
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

BASE_URL = "https://krest.gg"
SERVERS_TO_CHECK = [
    {"id": "AAS", "text_pattern": r"\[RU\]\[AAS"},
    {"id": "INV", "text_pattern": r"\[RU\]\[INV"},
    {"id": "MINI", "text_pattern": r"\[RU\]\[MINI"},
    {"id": "RAAS", "text_pattern": r"\[RU\]\[RAAS"},
    {"id": "TRN", "text_pattern": r"\[RU\]\[TRN"},
]

BROWSER_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
    "--disable-gpu", "--single-process", "--disable-extensions", "--no-zygote"
]


def _build_clan_pattern() -> re.Pattern:
    """Динамически формирует регулярное выражение для поиска клан-тегов из .env."""
    env_tags = os.getenv("CLAN_TAG_FILTER", "❀A❀, APES, ✿A✿")

    tags = [re.escape(tag.strip()) for tag in env_tags.split(",") if tag.strip()]

    if not tags:
        tags = [re.escape("❀A❀"), re.escape("APES"), re.escape("✿A✿")]

    tags_joined = "|".join(tags)

    # Ищет сам тег без обязательных внешних рамок
    pattern_str = rf"({tags_joined})"
    return re.compile(pattern_str, re.IGNORECASE)

class KrestGGParser:
    def __init__(self, timeout: int = 15000):
        self.timeout = timeout
        self._cache = {"data": {}, "timestamp": 0, "ttl": 120}

    async def get_pet_online_by_server(self, force_refresh: bool = False) -> Dict[str, List[str]]:
        now = time.time()
        if not force_refresh and self._cache["data"] and (now - self._cache["timestamp"]) < self._cache["ttl"]:
            return self._cache["data"]

        logger.info("🔍 Сканирую сервера krest.gg...")
        result = {}

        async with async_playwright() as p:
            browser = None
            try:
                browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()

                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=self.timeout)
                await page.wait_for_timeout(2000)

                for srv in SERVERS_TO_CHECK:
                    try:
                        btn = page.get_by_text(re.compile(srv["text_pattern"])).first

                        if await btn.count() > 0:
                            raw_name = await btn.text_content()
                            clean_name = re.sub(r'\s*\d+/\d+.*', '', raw_name).strip()

                            logger.info(f"🔄 Переключаю на: {clean_name}")

                            await btn.scroll_into_view_if_needed()
                            await btn.evaluate("el => el.click()")
                            await page.wait_for_timeout(1500)

                            players = await self._extract_pet_players(page)
                            if players:
                                result[clean_name] = players
                                logger.debug(f"✅ {clean_name}: {len(players)} чел.")
                        else:
                            logger.debug(f"⚠️ Кнопка {srv['id']} не найдена")

                    except Exception as e:
                        logger.error(f"❌ Ошибка с сервером {srv['id']}: {e}")
                        continue

                self._cache["data"] = result
                self._cache["timestamp"] = time.time()
                return result

            except Exception as e:
                logger.error(f"❌ Глобальная ошибка парсинга krest.gg: {e}")
                return {}
            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass

    async def _extract_pet_players(self, page) -> List[str]:
        players = set()
        tag_pattern = _build_clan_pattern()

        try:
            # Находим все текстовые элементы с тегами
            elements = await page.get_by_text(tag_pattern).all()

            for el in elements:
                try:
                    text = await el.text_content()
                    if not text:
                        continue

                    # Очищаем системный мусор (кнопку "В друзья" и HTML-теги)
                    text_clean = re.sub(r'<[^>]+>', '', text)
                    text_clean = re.sub(r'В\s*друзья.*', '', text_clean, flags=re.IGNORECASE).strip()

                    # Если в очищенной строке есть наш клан-тег
                    if tag_pattern.search(text_clean):
                        # Если строка содержит имя вроде "❀APES❀ stl", берем её полностью
                        full_nick = text_clean.strip()

                        if 3 <= len(full_nick) <= 30:
                            players.add(full_nick)

                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Ошибка парсинга игроков: {e}")

        return list(players)



krest_parser = KrestGGParser()