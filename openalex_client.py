"""Klient API OpenAlex (https://openalex.org) - otwarta baza ponad 250 mln publikacji naukowych."""

from __future__ import annotations

from datetime import date

import pandas as pd
import requests

API_URL = "https://api.openalex.org/works"
USER_AGENT = f"BatteryLab/1.0 (aplikacja Streamlit, projekt studencki) python-requests/{requests.__version__}"
POLA_PRAC = (
    "id,doi,title,publication_year,publication_date,cited_by_count,primary_location,"
    "authorships,open_access,best_oa_location,abstract_inverted_index"
)


class BladOpenAlex(Exception):
    pass


def filtr(fraza: str, rok_od: int, rok_do: int, tylko_artykuly: bool = True, kraj: str | None = None) -> str:
    """Buduje filtr wyszukiwania w tytułach i abstraktach (przecinki są separatorem filtrów, więc je usuwamy)."""
    fraza = " ".join(fraza.replace(",", " ").split())
    czesci = [
        f"title_and_abstract.search:{fraza}",
        f"from_publication_date:{rok_od}-01-01",
        f"to_publication_date:{rok_do}-12-31",
    ]
    if tylko_artykuly:
        czesci.append("type:article")
    if kraj:
        czesci.append(f"authorships.countries:{kraj}")
    return ",".join(czesci)


def zapytanie(parametry: dict, klucz_api: str | None = None) -> dict:
    parametry = dict(parametry)
    if klucz_api:
        parametry["api_key"] = klucz_api
    try:
        odpowiedz = requests.get(API_URL, params=parametry, headers={"User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException as blad:
        raise BladOpenAlex(f"Brak połączenia z OpenAlex: {blad}") from blad

    if odpowiedz.status_code == 429:
        raise BladOpenAlex(
            "Wyczerpany dzienny limit zapytań OpenAlex dla tego adresu IP. "
            "Dodaj darmowy klucz API w panelu bocznym (openalex.org/settings/api) albo spróbuj jutro."
        )
    try:
        dane = odpowiedz.json()
    except ValueError as blad:
        raise BladOpenAlex(f"Nieprawidłowa odpowiedź serwera (HTTP {odpowiedz.status_code}).") from blad
    if odpowiedz.status_code >= 400:
        raise BladOpenAlex(dane.get("message") or dane.get("error") or f"HTTP {odpowiedz.status_code}")
    return dane


def grupuj(filtr_: str, pole: str, limit: int = 10, klucz_api: str | None = None) -> pd.DataFrame:
    dane = zapytanie({"filter": filtr_, "group_by": pole, "per_page": limit}, klucz_api)
    grupy = dane.get("group_by", [])
    df = pd.DataFrame(grupy, columns=["key", "key_display_name", "count"])
    return df.rename(columns={"key": "id", "key_display_name": "nazwa", "count": "liczba"})


def trend_roczny(filtr_: str, klucz_api: str | None = None) -> pd.DataFrame:
    dane = zapytanie({"filter": filtr_, "group_by": "publication_year"}, klucz_api)
    df = pd.DataFrame(dane.get("group_by", []), columns=["key", "key_display_name", "count"])
    df = df.rename(columns={"key": "rok", "count": "liczba"})[["rok", "liczba"]]
    df["rok"] = pd.to_numeric(df["rok"], errors="coerce")
    return df.dropna().astype({"rok": int}).sort_values("rok").reset_index(drop=True)


def abstrakt(odwrocony_indeks: dict | None) -> str:
    """OpenAlex przechowuje abstrakty jako indeks odwrócony {słowo: [pozycje]} - odtwarzamy tekst."""
    if not odwrocony_indeks:
        return ""
    pozycje = {p: slowo for slowo, lista in odwrocony_indeks.items() for p in lista}
    return " ".join(pozycje[i] for i in sorted(pozycje))


def _praca(rekord: dict) -> dict:
    autorzy = rekord.get("authorships") or []
    zrodlo = ((rekord.get("primary_location") or {}).get("source") or {}).get("display_name")
    oa = rekord.get("open_access") or {}
    najlepsza = rekord.get("best_oa_location") or {}
    instytucje = []
    for autor in autorzy:
        for inst in autor.get("institutions") or []:
            nazwa = inst.get("display_name")
            if nazwa and (nazwa, inst.get("country_code")) not in instytucje:
                instytucje.append((nazwa, inst.get("country_code")))
    nazwiska = [((a.get("author") or {}).get("display_name") or "") for a in autorzy]
    return {
        "tytuł": rekord.get("title") or "(bez tytułu)",
        "rok": rekord.get("publication_year"),
        "data": rekord.get("publication_date"),
        "cytowania": rekord.get("cited_by_count", 0),
        "czasopismo": zrodlo or "",
        "autorzy": ", ".join(nazwiska[:3]) + (" i in." if len(nazwiska) > 3 else ""),
        "wszyscy_autorzy": nazwiska,
        "instytucje": instytucje,
        "open_access": bool(oa.get("is_oa")),
        "pdf": najlepsza.get("pdf_url") or oa.get("oa_url") or "",
        "doi": rekord.get("doi") or "",
        "openalex": rekord.get("id", ""),
        "abstrakt": abstrakt(rekord.get("abstract_inverted_index")),
    }


def prace(filtr_: str, sortowanie: str, limit: int = 25, klucz_api: str | None = None) -> tuple[pd.DataFrame, int]:
    dane = zapytanie(
        {"filter": filtr_, "sort": sortowanie, "per_page": limit, "select": POLA_PRAC},
        klucz_api,
    )
    lista = [_praca(r) for r in dane.get("results", [])]
    return pd.DataFrame(lista), int((dane.get("meta") or {}).get("count", 0))


def instytucje_z_kraju(prace_df: pd.DataFrame, kod_kraju: str) -> pd.DataFrame:
    licznik: dict[str, int] = {}
    for instytucje in prace_df.get("instytucje", []):
        for nazwa in {n for n, kraj in instytucje if kraj == kod_kraju}:
            licznik[nazwa] = licznik.get(nazwa, 0) + 1
    return (
        pd.DataFrame(list(licznik.items()), columns=["instytucja", "liczba prac"])
        .sort_values("liczba prac", ascending=False)
        .reset_index(drop=True)
    )


def biezacy_rok() -> int:
    return date.today().year
