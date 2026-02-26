from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
import unicodedata
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/122.0.0.0 Safari/537.36'
)
SOURCE_NAME = 'PagineGialle'
BASE_URL = 'https://www.paginegialle.it'


@dataclass
class ScrapedCompany:
    search_term: str
    region: str
    province: str
    city: str
    municipality: str
    company: str
    phone: str
    contact_name: str
    address: str
    distance_km: float | None
    source_name: str
    source_url: str


class CompanyScraperService:
    def search(
        self,
        search_term: str,
        region: str = 'Lombardia',
        province: str = 'Milano',
        city: str = '',
        municipality: str = '',
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        term = (search_term or '').strip()
        max_rows = min(max(1, int(max_results)), 200)
        results: list[ScrapedCompany] = []
        seen: set[tuple[str, str, str]] = set()
        for where in self._candidate_locations(region, province, city, municipality):
            next_url: str | None = self._build_search_url(term, where)
            while next_url and len(results) < max_rows:
                html = self._fetch_html(next_url)
                if not html:
                    break

                parsed, next_page = self._parse_page(
                    html=html,
                    search_term=term,
                    region=region,
                    province=province,
                    city=city,
                    municipality=municipality,
                )
                for item in parsed:
                    key = (item.company.lower(), item.phone.lower(), item.address.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(item)
                    if len(results) >= max_rows:
                        break

                next_url = next_page if len(results) < max_rows else None

        indexed = list(enumerate(results))
        indexed.sort(
            key=lambda entry: (
                self._priority_bucket(entry[1], municipality, city, region),
                entry[1].distance_km if entry[1].distance_km is not None else 999999.0,
                entry[0],
            )
        )
        ordered = [item for _, item in indexed]
        return [self._as_row(item) for item in ordered]

    def _candidate_locations(self, region: str, province: str, city: str, municipality: str) -> list[str]:
        values = [
            (municipality or '').strip(),
            (city or '').strip(),
            f"{(province or '').strip()} {(region or '').strip()}".strip(),
            (province or '').strip(),
            (region or '').strip(),
            'Italia',
        ]
        ordered: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(value)
        return ordered

    def _build_search_url(self, search_term: str, where: str) -> str:
        clean_term = (search_term or '').strip()
        clean_where = (where or '').strip()
        if clean_term:
            return f'{BASE_URL}/ricerca/{quote(clean_term)}/{quote(clean_where)}'
        return f'{BASE_URL}/ricerca/{quote(clean_where)}'

    def _fetch_html(self, url: str) -> str:
        req = Request(self._normalize_url(url), headers={'User-Agent': USER_AGENT, 'Accept-Language': 'it-IT,it;q=0.9'})
        with urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8', 'ignore')

    def _parse_page(
        self,
        html: str,
        search_term: str,
        region: str,
        province: str,
        city: str,
        municipality: str,
    ) -> tuple[list[ScrapedCompany], str | None]:
        items: list[ScrapedCompany] = []
        blocks = self._extract_search_blocks(html)
        for block in blocks:
            company = self._extract_company(block)
            if not company:
                continue
            address = self._strip_region_prefix(self._extract_address(block), region)
            phone = self._extract_phone(block)
            source_url = self._extract_source_url(block)
            distance_km = self._extract_distance_km(block)
            parsed_city = self._extract_city_from_address(address)
            resolved_city = (parsed_city or city or '').strip()
            resolved_municipality = (parsed_city or municipality or '').strip()
            items.append(
                ScrapedCompany(
                    search_term=search_term,
                    region=(region or '').strip(),
                    province=(province or '').strip(),
                    city=resolved_city,
                    municipality=resolved_municipality,
                    company=company,
                    phone=phone,
                    contact_name='',
                    address=address,
                    distance_km=distance_km,
                    source_name=SOURCE_NAME,
                    source_url=source_url,
                )
            )

        next_page = None
        match = re.search(r'class="bttn[^"]*next-page-btn[^"]*"[^>]*data-pageurl="([^"]+)"', html)
        if match:
            next_page = self._normalize_url(urljoin(BASE_URL, unescape(match.group(1))))
        return items, next_page

    def _extract_search_blocks(self, html: str) -> list[str]:
        blocks: list[str] = []
        for match in re.finditer(r'<div[^>]*class="[^"]*\bsearch-itm\b[^"]*"[^>]*>', html):
            start = match.start()
            block = self._extract_balanced_div(html, start)
            if block:
                blocks.append(block)
        return blocks

    def _extract_balanced_div(self, text: str, start: int) -> str:
        depth = 0
        for match in re.finditer(r'<div\b|</div>', text[start:]):
            token = match.group(0)
            if token.startswith('<div'):
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    return text[start:start + match.end()]
        return ''

    def _extract_company(self, block: str) -> str:
        match = re.search(r'<h2 class="search-itm__rag[^>]*>(.*?)</h2>', block, re.S)
        if not match:
            return ''
        return self._clean_html(match.group(1))

    def _extract_address(self, block: str) -> str:
        container = self._extract_div_container(block, 'search-itm__adr')
        if not container:
            return ''
        return self._clean_html(container)

    def _extract_phone(self, block: str) -> str:
        container = self._extract_div_container(block, 'search-itm__phone')
        if not container:
            return ''
        raw = self._clean_html(container)
        raw = raw.replace('Tel:', '').strip()
        return re.sub(r'\s{2,}', ' ', raw)

    def _extract_source_url(self, block: str) -> str:
        match = re.search(r'<h2 class="search-itm__rag[\s\S]*?<a[^>]+href="([^"]+)"', block)
        if not match:
            return ''
        href = unescape(match.group(1)).strip()
        if href.startswith('javascript:'):
            alt = re.search(r'<a[^>]+href="([^"]+)"[^>]+title="Dettagli azienda"', block)
            if alt:
                href = unescape(alt.group(1)).strip()
        return href

    def _extract_distance_km(self, block: str) -> float | None:
        container = self._extract_div_container(block, 'search-itm__dist')
        raw = self._clean_html(container).lower() if container else self._clean_html(block).lower()
        raw = raw.replace(',', '.')
        match = re.search(r'(\d+(?:\.\d+)?)\s*km\b', raw)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _extract_city_from_address(self, address: str) -> str:
        match = re.search(r'([A-Za-z\u00C0-\u00FF\'\-\s]+)\s*\([A-Z]{2}\)\s*$', address)
        if not match:
            return ''
        return re.sub(r'\s+', ' ', match.group(1)).strip()

    def _strip_region_prefix(self, address: str, region: str) -> str:
        clean_address = (address or '').strip()
        clean_region = (region or '').strip()
        if not clean_region:
            return clean_address
        return re.sub(rf'^\s*{re.escape(clean_region)}\s+', '', clean_address, flags=re.I)

    def _clean_html(self, value: str) -> str:
        no_tags = re.sub(r'<[^>]+>', ' ', value or '')
        clean = unescape(no_tags)
        return re.sub(r'\s+', ' ', clean).strip()

    def _extract_div_container(self, block: str, class_name: str) -> str:
        class_idx = block.find(f'class="{class_name}')
        if class_idx == -1:
            return ''
        start = block.rfind('<div', 0, class_idx)
        if start == -1:
            return ''

        depth = 0
        for match in re.finditer(r'<div\b|</div>', block[start:]):
            token = match.group(0)
            if token.startswith('<div'):
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    end = start + match.end()
                    return block[start:end]
        return ''

    def _as_row(self, item: ScrapedCompany) -> dict[str, Any]:
        return {
            'search_term': item.search_term,
            'region': item.region,
            'province': item.province,
            'city': item.city,
            'municipality': item.municipality,
            'company': item.company,
            'phone': item.phone,
            'contact_name': item.contact_name,
            'address': item.address,
            'distance_km': item.distance_km,
            'source_name': item.source_name,
            'source_url': item.source_url,
        }

    def _priority_bucket(self, item: ScrapedCompany, municipality: str, city: str, region: str) -> int:
        haystack = self._normalized_text(
            ' '.join(
                [
                    item.address or '',
                    item.city or '',
                    item.municipality or '',
                    item.province or '',
                    item.region or '',
                ]
            )
        )
        wanted_municipality = self._normalized_text(municipality)
        wanted_city = self._normalized_text(city)
        wanted_region = self._normalized_text(region)

        if self._contains_phrase(haystack, wanted_municipality):
            return 0
        if self._contains_phrase(haystack, wanted_city):
            return 1
        if self._contains_phrase(haystack, wanted_region):
            return 2
        return 3

    def _normalized_text(self, value: str) -> str:
        normalized = unicodedata.normalize('NFKD', value or '')
        no_accents = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
        lowered = no_accents.lower()
        return re.sub(r'\s+', ' ', lowered).strip()

    def _contains_phrase(self, haystack: str, phrase: str) -> bool:
        if not phrase:
            return False
        escaped = re.escape(phrase).replace(r'\ ', r'\s+')
        pattern = rf'(?<!\w){escaped}(?!\w)'
        return bool(re.search(pattern, haystack))

    def _normalize_url(self, url: str) -> str:
        parts = urlsplit((url or '').strip())
        path = quote(parts.path, safe='/%:@')
        query = quote(parts.query, safe='=&%:@,+')
        fragment = quote(parts.fragment, safe='')
        return urlunsplit((parts.scheme, parts.netloc, path, query, fragment))
