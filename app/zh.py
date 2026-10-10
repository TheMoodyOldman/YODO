"""Chinese script helpers. Bangumi and Open Library mostly carry Simplified Chinese; the site is
Traditional (Taiwan), so queries go out simplified and titles come back traditional."""

import re
from functools import cache

import opencc

_HAN = re.compile(r"[㐀-鿿]")
_KANA = re.compile(r"[぀-ヿ]")


@cache
def _converter(config: str) -> opencc.OpenCC:
    return opencc.OpenCC(config)


def is_chinese(text: str | None) -> bool:
    """Has Han characters and no kana (so Japanese titles are left alone)."""
    return bool(text and _HAN.search(text) and not _KANA.search(text))


def to_simplified(text: str) -> str:
    return _converter("t2s").convert(text) if is_chinese(text) else text


def to_traditional(text: str) -> str:
    # Character conversion only (s2tw, not s2twp): titles are proper names, so 软件 stays 軟件.
    return _converter("s2tw").convert(text) if is_chinese(text) else text
