import re
import logging
import unicodedata
from datetime import datetime
import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def strip_html_comments(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'<!--[\s\S]*?-->', '', text)

def decode_html_entities(text: str) -> str:
    if not text:
        return ""
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    text = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), text)
    return text

def strip_tags(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r'<\s*br\s*/?\s*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<\s*/\s*p\s*>', '\n\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<[^>]+>', '', html)
    html = decode_html_entities(html)
    html = re.sub(r'\r', '', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()

def extract_element_inner_html(html: str, open_tag_re_str: str) -> str:
    match = re.search(open_tag_re_str, html, re.IGNORECASE)
    if not match:
        return ""
    
    tag_match = re.match(r'<([a-z0-9]+)', match.group(0), re.IGNORECASE)
    if not tag_match:
        return ""
    tag = tag_match.group(1).lower()
    
    open_tag_end = match.end()
    tag_re = re.compile(rf'</?{tag}\b', re.IGNORECASE)
    
    depth = 1
    for m in tag_re.finditer(html, open_tag_end):
        is_closing = m.group(0).startswith('</')
        if is_closing:
            depth -= 1
        else:
            depth += 1
            
        if depth == 0:
            return html[open_tag_end:m.start()]
            
    return ""

def choose_best_image(entry_html: str) -> str:
    candidates = re.findall(r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>', entry_html, re.IGNORECASE)
    
    def is_bad(src: str) -> bool:
        s = src.lower()
        return 'icon-x-ext' in s or 'device-liturgia' in s or 'pedido-thumb' in s
        
    def is_good(src: str) -> bool:
        s = src.lower()
        return any(ext in s for ext in ['.jpg', '.jpeg', '.png', '.webp']) or 'uploads' in s or 'cnimages' in s
        
    good = [src for src in candidates if not is_bad(src) and is_good(src)]
    if good:
        return good[0]
        
    ok = [src for src in candidates if not is_bad(src)]
    return ok[0] if ok else None

def normalize_spaces(text: str) -> str:
    if not text:
        return ""
    text = text.replace('\u00A0', ' ')
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def should_skip_text(text: str) -> bool:
    cleaned = normalize_spaces(text)
    if not cleaned or cleaned in ['.', '…', '-->', '->']:
        return True
    upper = cleaned.upper()
    return any(term in upper for term in ['COMPARTILHE NO', 'AJUDE A CANCAO NOVA', 'PEDIDO DE ORACAO', 'APLICATIVO LITURGIA'])

def is_bold_only_paragraph(inner_html: str) -> bool:
    s = inner_html.strip()
    if not s:
        return False
    return bool(re.match(r'^(?:<span\b[^>]*>\s*)*<(strong|b)\b[^>]*>[\s\S]*?</\1>\s*(?:</span>\s*)*$', s, re.IGNORECASE))

def normalize_search_key(text: str) -> str:
    if not text:
        return ""
    text_normalized = unicodedata.normalize('NFD', text)
    text_no_accents = "".join(c for c in text_normalized if unicodedata.category(c) != 'Mn')
    return text_no_accents.lower()

def is_outros_santos_text(text: str) -> bool:
    n = normalize_search_key(text)
    return 'outros' in n and ('santos' in n or 'beatos' in n)

def is_footer_text(text: str) -> bool:
    n = normalize_search_key(text).strip()
    return n in ['fontes:', 'fontes']

def find_other_saints_section_index(entry_html: str) -> int:
    re_tag = re.compile(r'<(h2|h3|h4|p|strong|b)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
    for match in re_tag.finditer(entry_html):
        if is_outros_santos_text(strip_tags(match.group(2))):
            return match.start()
    return -1

def find_footer_section_index(entry_html: str) -> int:
    re_tag = re.compile(r'<(h2|h3|h4|p|strong|b)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
    for match in re_tag.finditer(entry_html):
        if is_footer_text(strip_tags(match.group(2))):
            return match.start()
    return -1

def extract_content_blocks(entry_html: str) -> list:
    blocks = []
    
    other_idx = find_other_saints_section_index(entry_html)
    footer_idx = find_footer_section_index(entry_html)
    
    end_idx = -1
    if other_idx >= 0 and footer_idx >= 0:
        end_idx = min(other_idx, footer_idx)
    elif other_idx >= 0:
        end_idx = other_idx
    elif footer_idx >= 0:
        end_idx = footer_idx
        
    html = entry_html[:end_idx] if end_idx >= 0 else entry_html
    
    element_re = re.compile(r'<(p|h2|h3|h4|blockquote|ul|ol|strong|b)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
    
    for match in element_re.finditer(html):
        tag = match.group(1).lower()
        inner = match.group(2)
        
        plain_text = strip_tags(inner)
        if is_outros_santos_text(plain_text) or is_footer_text(plain_text):
            break
            
        if tag in ['ul', 'ol']:
            items_raw = re.findall(r'<li[^>]*>([\s\S]*?)</li>', inner, re.IGNORECASE)
            items = [normalize_spaces(strip_tags(item)) for item in items_raw]
            items = [item for item in items if item and not should_skip_text(item)]
            if items:
                blocks.append({"type": tag, "items": items})
            continue
            
        if tag in ['strong', 'b']:
            cleaned = normalize_spaces(plain_text)
            if cleaned and not should_skip_text(cleaned):
                blocks.append({"type": "h3", "text": cleaned})
            continue
            
        if tag == 'p':
            if is_bold_only_paragraph(inner):
                cleaned = normalize_spaces(plain_text)
                if cleaned and not should_skip_text(cleaned):
                    blocks.append({"type": "h3", "text": cleaned})
                continue
                
            bold_re = re.compile(r'<(strong|b)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
            last_index = 0
            has_bold = False
            
            for bm in bold_re.finditer(inner):
                has_bold = True
                before_html = inner[last_index:bm.start()]
                cleaned_before = normalize_spaces(strip_tags(before_html))
                if cleaned_before and not should_skip_text(cleaned_before):
                    blocks.append({"type": "p", "text": cleaned_before})
                    
                bold_html = bm.group(2)
                cleaned_bold = normalize_spaces(strip_tags(bold_html))
                if cleaned_bold and not should_skip_text(cleaned_bold):
                    blocks.append({"type": "h3", "text": cleaned_bold})
                    
                last_index = bm.end()
                
            if has_bold:
                after_html = inner[last_index:]
                cleaned_after = normalize_spaces(strip_tags(after_html))
                if cleaned_after and not should_skip_text(cleaned_after):
                    blocks.append({"type": "p", "text": cleaned_after})
                continue
                
            cleaned = normalize_spaces(plain_text)
            if cleaned and not should_skip_text(cleaned):
                blocks.append({"type": "p", "text": cleaned})
            continue
            
        cleaned = normalize_spaces(plain_text)
        if cleaned and not should_skip_text(cleaned):
            blocks.append({"type": tag, "text": cleaned})
            
    return blocks if blocks else None

def extract_balanced_outer_html_from(html: str, tag_name: str, start_index: int = 0) -> str:
    slice_html = html[start_index:]
    open_match = re.search(rf'<{tag_name}\b[^>]*>', slice_html, re.IGNORECASE)
    if not open_match:
        return None
        
    absolute_open_start = start_index + open_match.start()
    open_tag_end = absolute_open_start + len(open_match.group(0))
    
    tag_re = re.compile(rf'</?{tag_name}\b', re.IGNORECASE)
    depth = 1
    
    for mm in tag_re.finditer(html, open_tag_end):
        is_closing = mm.group(0).startswith('</')
        if is_closing:
            depth -= 1
        else:
            depth += 1
            
        if depth == 0:
            close_start = mm.start()
            close_end = html.find('>', close_start)
            if close_end == -1:
                return None
            return html[absolute_open_start:close_end + 1]
            
    return None

def extract_other_saints(entry_html: str) -> list:
    other_idx = find_other_saints_section_index(entry_html)
    footer_idx = find_footer_section_index(entry_html)
    
    candidates = []
    
    if other_idx >= 0:
        other_slice = entry_html[other_idx:footer_idx] if footer_idx >= 0 and footer_idx > other_idx else entry_html[other_idx:]
        ul_outer = extract_balanced_outer_html_from(other_slice, 'ol') or extract_balanced_outer_html_from(other_slice, 'ul')
        
        if ul_outer:
            items_raw = re.findall(r'<li[^>]*>([\s\S]*?)</li>', ul_outer, re.IGNORECASE)
            items = [normalize_spaces(strip_tags(item)) for item in items_raw]
            items = [item for item in items if item]
            if items:
                return items
                
    list_re = re.compile(r'<(ul|ol)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
    best_score = -1
    best_items = None
    
    for mm in list_re.finditer(entry_html):
        outer = mm.group(0)
        inner = mm.group(2)
        items_raw = re.findall(r'<li[^>]*>([\s\S]*?)</li>', inner, re.IGNORECASE)
        items = [normalize_spaces(strip_tags(item)) for item in items_raw]
        items = [item for item in items if item]
        if len(items) < 3:
            continue
            
        starts_with_em = sum(1 for i in items if re.match(r'^em\s+', i, re.IGNORECASE))
        has_dagger = sum(1 for i in items if '†' in i)
        score = len(items) + starts_with_em * 2 + has_dagger
        
        if score > best_score:
            best_score = score
            best_items = items
            
    if best_items:
        candidates.extend(best_items)
        
    return candidates if candidates else None

def extract_image_caption(entry_html: str, image_url: str) -> str:
    if not image_url:
        return None
    try:
        img_idx = entry_html.find(image_url)
        if img_idx < 0:
            return None
            
        p_close_idx = entry_html.find('</p>', img_idx)
        if p_close_idx < 0:
            return None
            
        after = entry_html[p_close_idx + 4 : p_close_idx + 1004]
        next_p = re.match(r'^\s*<p[^>]*>([\s\S]*?)</\1>', after, re.IGNORECASE)
        if not next_p:
            return None
            
        inner = next_p.group(1)
        if not re.search(r'<span\b', inner, re.IGNORECASE):
            return None
            
        if re.match(r'^\s*<strong\b', inner, re.IGNORECASE):
            return None
            
        text = strip_tags(inner).strip()
        if not text or len(text) > 200:
            return None
            
        return text
    except Exception:
        return None

def get_month_name_pt(month_num: int) -> str:
    months = {
        1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril",
        5: "maio", 6: "junho", 7: "julho", 8: "agosto",
        9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
    }
    return months.get(month_num, "")

def get_month_abbrev_pt(month_num: int) -> str:
    abbrevs = {
        1: "jan", 2: "fev", 3: "mar", 4: "abr",
        5: "mai", 6: "jun", 7: "jul", 8: "ago",
        9: "set", 10: "out", 11: "nov", 12: "dez"
    }
    return abbrevs.get(month_num, "")

async def extrair_santo_do_dia_por_data(target_date: str, fallback_home: bool = True) -> dict:
    """
    Executa o scraping do Santo do Dia para a data especificada (no formato YYYY-MM-DD).
    """
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD.")
        
    day_str = str(dt.day)
    month_name = get_month_name_pt(dt.month)
    month_abbrev = get_month_abbrev_pt(dt.month)
    year_str = str(dt.year)
    
    url = f"https://santo.cancaonova.com/santo/{day_str}-de-{month_name}/"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.6',
        })
        if response.status_code == 404:
            if not fallback_home:
                raise HTTPException(status_code=404, detail="Santo do dia não disponível para a data especificada.")
            response = await client.get("https://santo.cancaonova.com/", headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.6',
            })
        
        response.raise_for_status()
            
    html = strip_html_comments(response.text)
    
    title_match = re.search(r'<h1[^>]*class=["\'][^"\']*entry-title[^"\']*["\'][^>]*>([\s\S]*?)</h1>', html, re.IGNORECASE)
    title = strip_tags(title_match.group(1)) if title_match else "Santo do Dia"
    
    entry_inner = extract_element_inner_html(html, r'<([a-z0-9]+)[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>')
    
    image = choose_best_image(entry_inner) if entry_inner else None
    image_caption = extract_image_caption(entry_inner, image) if entry_inner and image else None
    content_blocks = extract_content_blocks(entry_inner) if entry_inner else None
    full_text = strip_tags(entry_inner) if entry_inner else None
    
    if image_caption and content_blocks:
        caption_norm = normalize_search_key(image_caption)
        content_blocks = [b for b in content_blocks if not ('text' in b and normalize_search_key(b['text']) == caption_norm)]
        if not content_blocks:
            content_blocks = None
            
    outros_santos = extract_other_saints(entry_inner) if entry_inner else None
    
    return {
        "objective": "A API_LITURGIA_DIARIA visa disponibilizar via api as leituras para facilitar a criação de aplicações que almejam a evangelização.",
        "source": "Canção Nova",
        "today": {
            "day": day_str,
            "month": month_abbrev,
            "year": year_str,
            "title": title,
            "image": image,
            "image_caption": image_caption,
            "content_blocks": content_blocks,
            "full_text": full_text,
            "outros_santos": outros_santos
        }
    }
