from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from .db import Database, Security

AUTO_PICK_SCORE = 90
SUGGEST_TOP_N = 3
MIN_SCORE = 55


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


@dataclass
class MatchResult:
    """Результат матчинга. Ровно одно из полей заполнено:
    picked — однозначный выбор,
    suggestions — нужно уточнить у пользователя,
    nothing — ничего не подошло."""

    picked: Security | None = None
    suggestions: list[Security] | None = None

    @property
    def is_ambiguous(self) -> bool:
        return self.suggestions is not None


async def match_security(db: Database, user_id: int, raw_name: str) -> MatchResult:
    raw_norm = _normalize(raw_name)

    alias_secid = await db.get_alias(user_id, raw_norm)
    if alias_secid:
        sec = await db.get_security(alias_secid)
        if sec:
            return MatchResult(picked=sec)

    # exact ticker match (e.g. "SBER" или "GLDRUB_TOM")
    exact = await db.get_security(raw_name.upper())
    if exact:
        return MatchResult(picked=exact)

    securities = await db.all_securities()
    if not securities:
        return MatchResult(suggestions=[])

    by_key: dict[str, Security] = {}
    choices: list[str] = []
    for sec in securities:
        for label in (sec.secid, sec.shortname, sec.secname):
            key = _normalize(label)
            if key and key not in by_key:
                by_key[key] = sec
                choices.append(key)

    results = process.extract(
        raw_norm,
        choices,
        scorer=fuzz.WRatio,
        limit=SUGGEST_TOP_N * 3,
    )

    seen_secids: set[str] = set()
    ranked: list[tuple[Security, float]] = []
    for choice, score, _idx in results:
        sec = by_key[choice]
        if sec.secid in seen_secids:
            continue
        seen_secids.add(sec.secid)
        ranked.append((sec, float(score)))
        if len(ranked) >= SUGGEST_TOP_N:
            break

    if not ranked or ranked[0][1] < MIN_SCORE:
        return MatchResult(suggestions=[])

    top_sec, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if top_score >= AUTO_PICK_SCORE and top_score - second_score >= 10:
        return MatchResult(picked=top_sec)

    return MatchResult(suggestions=[s for s, _ in ranked])
