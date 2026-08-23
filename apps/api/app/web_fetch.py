import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

MAX_PAGE_BYTES = 2_000_000
MAX_REDIRECTS = 3
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "div", "article", "section", "li", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        self.parts.append(value)

    def output(self) -> tuple[str, str]:
        title = " ".join(self.title_parts).strip()
        text = "\n".join(
            line.strip()
            for line in " ".join(self.parts).replace(" \n ", "\n").splitlines()
            if line.strip()
        )
        return title, text


def _ip_is_public(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("只允许 http/https URL")
    if not parsed.hostname:
        raise ValueError("URL 缺少有效主机名")
    if parsed.username or parsed.password:
        raise ValueError("URL 不允许包含用户名或密码")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("仅允许标准 HTTP/HTTPS 端口")

    hostname = parsed.hostname
    try:
        _ip_is_public(hostname)
        addresses = [hostname]
    except ValueError:
        try:
            addresses = list(
                {
                    item[4][0]
                    for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
                }
            )
        except socket.gaierror as exc:
            raise ValueError("无法解析目标域名") from exc

    if not addresses or any(not _ip_is_public(address) for address in addresses):
        raise ValueError("禁止访问本机、内网或保留地址")
    return url


async def fetch_public_page(url: str) -> tuple[str, str, str]:
    current = validate_public_url(url)
    headers = {
        "User-Agent": "Zhonggang-Zhituo/0.3 (+market-intelligence; public-page-reader)",
        "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
    }

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = await client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("网页重定向缺少目标地址")
                current = validate_public_url(urljoin(current, location))
                continue

            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and not any(kind in content_type for kind in ALLOWED_CONTENT_TYPES):
                raise ValueError("当前 URL 不是可解析的公开网页文本")
            body = response.content[: MAX_PAGE_BYTES + 1]
            if len(body) > MAX_PAGE_BYTES:
                raise ValueError("网页正文过大，超过 2MB 安全限制")
            encoding = response.encoding or "utf-8"
            raw = body.decode(encoding, errors="replace")
            if "html" in content_type or "<html" in raw[:1000].lower():
                parser = _TextExtractor()
                parser.feed(raw)
                title, text = parser.output()
            else:
                title, text = "", "\n".join(line.strip() for line in raw.splitlines() if line.strip())
            if len(text) < 40:
                raise ValueError("网页正文过短，无法形成可靠项目识别")
            return current, title, text[:100_000]

    raise ValueError("网页重定向次数过多")
