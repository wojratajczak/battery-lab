"""Prawdziwe dane z testów ogniw sodowo-jonowych pobierane przez API Zenodo.

Zbiór: S. Büchele i in. (KIT), "Sodium Manganese Hexacyanoferrate: Characterization as Sodium-Ion Cathode
Material, Full Cell Cycling with Hard Carbon and Post-Mortem Analyses", DOI 10.5281/zenodo.14359482,
licencja CC BY 4.0. Katoda NaMnHCF (analog błękitu pruskiego), półogniwo z sodem i ogniwa pełne z twardym węglem.
"""

from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd
import requests

import cycling

REKORD = "14359482"
API_URL = "https://zenodo.org/api/records/{rekord}"
PLIKI_CYKLI = [
    "Fig8_Cycling_data_NaMnHCF.csv",
    "Fig11a-1_Cycling_data_NaMnHCF_NaPF6_EC_DEC.csv",
    "Fig11a-2_Cycling_data_NaMnHCF_NaPF6_EC_PC_DMC+FEC.csv",
]
PLIK_KRZYWYCH = "Fig9a_C20_voltage_curves_NaMnHCF_half_cell.csv"
NAGLOWKI = {"User-Agent": f"BatteryLab/1.0 (aplikacja Streamlit, projekt studencki) python-requests/{requests.__version__}"}
MASA_JEDNOSTKOWA_MG = 1000.0


class BladZenodo(Exception):
    pass


def _get(url: str) -> requests.Response:
    try:
        odpowiedz = requests.get(url, headers=NAGLOWKI, timeout=60)
    except requests.RequestException as blad:
        raise BladZenodo(f"Brak połączenia z Zenodo: {blad}") from blad
    if odpowiedz.status_code >= 400:
        raise BladZenodo(f"Zenodo zwróciło błąd HTTP {odpowiedz.status_code} dla {url}")
    return odpowiedz


def pobierz_metadane(rekord: str = REKORD) -> dict:
    dane = _get(API_URL.format(rekord=rekord)).json()
    metadane = dane.get("metadata", {})
    return {
        "tytul": metadane.get("title", ""),
        "autorzy": [a.get("name", "") for a in metadane.get("creators", [])],
        "data": metadane.get("publication_date", ""),
        "doi": dane.get("doi", ""),
        "licencja": (metadane.get("license") or {}).get("id", ""),
        "pliki": {p["key"]: p["links"]["self"] for p in dane.get("files", [])},
    }


def pobierz_tekst(url: str) -> str:
    odpowiedz = _get(url)
    return odpowiedz.content.decode("utf-8-sig", errors="replace")


def nazwa_ogniwa(naglowek: str) -> str:
    """Np. 'Discharge capacity (mAh/g) full cell NaPF6 in EC:DEC 2.5 - 3-65 V' -> czytelna nazwa ogniwa."""
    tekst = re.sub(r"(?i)discharge capacity\s*\(mAh/g\)\s*", "", naglowek).strip()
    polowkowe = "half cell" in tekst.lower()
    okno = re.search(r"(\d\.\d+)\s*-\s*(\d)[.\-](\d+)\s*V", tekst)
    elektrolit = tekst[: okno.start()] if okno else tekst
    elektrolit = re.sub(r"(?i)^(half|full) cell\s*", "", elektrolit).replace(" in ", " w ").strip()

    if polowkowe:
        return f"Półogniwo NaMnHCF‖Na · {elektrolit}"
    zakres = f"{okno.group(1)}–{okno.group(2)}.{okno.group(3)} V" if okno else "1.5–4.0 V"
    return f"Ogniwo pełne NaMnHCF‖HC · {elektrolit} · {zakres.replace('.', ',')}"


def parsuj_cykle(tekst: str) -> dict[str, pd.Series]:
    """Plik z pojemnością rozładowania w kolejnych cyklach (kolumna cyklu + jedna kolumna na ogniwo)."""
    df = pd.read_csv(io.StringIO(tekst), sep=";")
    cykle = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    wynik = {}
    for kolumna in df.columns[1:]:
        seria = pd.Series(pd.to_numeric(df[kolumna], errors="coerce").to_numpy(), index=cykle).dropna()
        seria = seria[seria.index.notna()]
        seria.index = seria.index.astype(int)
        if len(seria):
            wynik[nazwa_ogniwa(kolumna)] = seria
    return wynik


def parsuj_krzywe(tekst: str) -> pd.DataFrame:
    """Plik z krzywymi napięciowymi: bloki po 4 kolumny na cykl (ładowanie: 2 kolumny, rozładowanie: 2 kolumny).

    W pliku źródłowym etykiety kolumn napięcia i pojemności są zamienione miejscami,
    dlatego kolumnę napięcia rozpoznajemy po zakresie wartości, a nie po nagłówku.
    """
    linie = tekst.splitlines()
    etykiety = linie[0].split(";")
    dane = pd.read_csv(io.StringIO("\n".join(linie[2:])), sep=";", header=None)
    dane = dane.apply(pd.to_numeric, errors="coerce")

    fragmenty = []
    for poczatek in range(0, dane.shape[1] - 3, 4):
        numer = re.search(r"\d+", etykiety[poczatek] if poczatek < len(etykiety) else "")
        if not numer:
            continue
        cykl = int(numer.group())
        for przesuniecie, znak in ((0, 1.0), (2, -1.0)):
            a = dane.iloc[:, poczatek + przesuniecie].to_numpy()
            b = dane.iloc[:, poczatek + przesuniecie + 1].to_numpy()
            maska = ~(np.isnan(a) | np.isnan(b))
            a, b = a[maska], b[maska]
            if not len(a):
                continue
            napiecie, pojemnosc = (a, b) if np.nanmax(a) <= 5.5 < np.nanmax(b) else (b, a)
            fragmenty.append(pd.DataFrame({
                "cycle": cykl,
                "voltage": napiecie,
                "current": znak,
                "q_ch": pojemnosc if znak > 0 else 0.0,
                "q_dis": pojemnosc if znak < 0 else 0.0,
            }))
    if not fragmenty:
        raise BladZenodo("Nie rozpoznano struktury pliku z krzywymi napięciowymi.")
    return pd.concat(fragmenty, ignore_index=True)


def dane_namnhcf() -> tuple[dict[str, tuple[pd.DataFrame | None, float, pd.DataFrame]], dict]:
    """Pobiera zbiór z Zenodo i zwraca ogniwa w formacie aplikacji: {nazwa: (krzywe, masa, tabela cykli)}."""
    metadane = pobierz_metadane()
    pliki = metadane["pliki"]

    serie: dict[str, pd.Series] = {}
    for nazwa_pliku in PLIKI_CYKLI:
        if nazwa_pliku not in pliki:
            continue
        for nazwa, seria in parsuj_cykle(pobierz_tekst(pliki[nazwa_pliku])).items():
            serie.setdefault(nazwa, seria)
    if not serie:
        raise BladZenodo("W rekordzie Zenodo nie znaleziono plików z danymi cyklowania.")

    krzywe = parsuj_krzywe(pobierz_tekst(pliki[PLIK_KRZYWYCH])) if PLIK_KRZYWYCH in pliki else None

    ogniwa = {}
    for nazwa, seria in serie.items():
        tabela = cycling.tabela_z_pojemnosci(seria.index.to_numpy(), seria.to_numpy())
        std = krzywe if nazwa.startswith("Półogniwo") else None
        ogniwa[nazwa] = (std, MASA_JEDNOSTKOWA_MG, tabela)
    return ogniwa, metadane
