"""Analiza danych z testów cyklowania ogniw: wczytanie, podsumowanie cykli, modele degradacji, dQ/dV."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.signal import find_peaks, savgol_filter

ROLE = {
    "cycle": "Numer cyklu",
    "voltage": "Napięcie [V]",
    "current": "Prąd (znak: + ładowanie, − rozładowanie)",
    "q_charge": "Pojemność ładowania",
    "q_discharge": "Pojemność rozładowania",
}
WYMAGANE = ("cycle", "q_discharge")

WZORCE = {
    "cycle": ["cycle number", "cycle_index", "cycle index", "cycle id", "cycle", "cykl"],
    "voltage": ["ecell/v", "ewe/v", "voltage(v)", "voltage (v)", "voltage", "napięcie", "potential", "ecell", "ewe"],
    "current": ["<i>/ma", "i/ma", "current(a)", "current(ma)", "current (ma)", "current", "prąd", "<i>"],
    "q_discharge": ["q discharge/ma.h", "discharge_capacity(ah)", "discharge capacity(mah)", "discharge capacity",
                    "discharge_capacity", "dchg. cap", "q discharge", "discharge"],
    "q_charge": ["q charge/ma.h", "charge_capacity(ah)", "charge capacity(mah)", "charge capacity",
                 "charge_capacity", "chg. cap", "q charge", "charge"],
}


def _norm(nazwa: str) -> str:
    return re.sub(r"\s+", " ", str(nazwa).strip().lower())


def zgadnij_kolumny(kolumny: list[str]) -> dict[str, str | None]:
    """Dopasowuje kolumny pliku do ról na podstawie typowych nazw z cyklerów (EC-Lab, Arbin, Neware, Maccor)."""
    wynik: dict[str, str | None] = {}
    uzyte: set[str] = set()
    for rola in ("cycle", "q_discharge", "q_charge", "voltage", "current"):
        najlepsza, najlepszy_wynik = None, 0
        for kolumna in kolumny:
            if kolumna in uzyte:
                continue
            nazwa = _norm(kolumna)
            if rola == "q_charge" and ("dis" in nazwa or "dchg" in nazwa):
                continue
            if rola in ("q_charge", "q_discharge") and not any(s in nazwa for s in ("cap", "q ", "q_", "mah", "ma.h", "ah")):
                continue
            for priorytet, wzorzec in enumerate(WZORCE[rola]):
                punkty = 0
                if nazwa == wzorzec:
                    punkty = 300 - priorytet
                elif nazwa.startswith(wzorzec):
                    punkty = 200 - priorytet
                elif wzorzec in nazwa:
                    punkty = 100 - priorytet
                if punkty > najlepszy_wynik:
                    najlepsza, najlepszy_wynik = kolumna, punkty
        wynik[rola] = najlepsza
        if najlepsza:
            uzyte.add(najlepsza)

    if not wynik["q_discharge"] and wynik["current"]:
        wspolna = next((k for k in kolumny if k not in uzyte and re.search(r"cap|ma\.?h", _norm(k))), None)
        if wspolna:
            wynik["q_discharge"] = wynik["q_charge"] = wspolna
    return wynik


def jednostka_pojemnosci(nazwa_kolumny: str | None) -> str:
    nazwa = _norm(nazwa_kolumny or "")
    if "mah" in nazwa or "ma.h" in nazwa or "ma h" in nazwa:
        return "mAh"
    if re.search(r"\(ah\)|/a\.h|\[ah\]|\bah\b", nazwa):
        return "Ah"
    return "mAh"


def wczytaj_plik(zawartosc: bytes, nazwa: str) -> pd.DataFrame:
    """Wczytuje CSV/TXT/MPT (separator i przecinek dziesiętny wykrywane automatycznie) lub XLSX."""
    if nazwa.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(zawartosc))

    for kodowanie in ("utf-8", "cp1250", "latin-1"):
        try:
            tekst = zawartosc.decode(kodowanie)
            break
        except UnicodeDecodeError:
            continue
    linie = tekst.splitlines()
    if linie and linie[0].startswith("EC-Lab ASCII FILE"):
        naglowek = re.search(r"Nb header lines\s*:\s*(\d+)", tekst[:500])
        if naglowek:
            linie = linie[int(naglowek.group(1)) - 1:]
            tekst = "\n".join(linie)
    pierwsza = linie[0] if linie else ""
    separator = max(["\t", ";", ","], key=pierwsza.count)
    dziesietny = "," if separator != "," and re.search(r"\d,\d", tekst[:5000]) else "."
    return pd.read_csv(io.StringIO(tekst), sep=separator, decimal=dziesietny)


def standaryzuj(df: pd.DataFrame, mapowanie: dict[str, str | None], jednostka: str = "auto") -> pd.DataFrame:
    """Zwraca ramkę z kolumnami: cycle, voltage, current, q_ch, q_dis (pojemności w mAh)."""
    for rola in WYMAGANE:
        if not mapowanie.get(rola):
            raise ValueError(f"Nie wskazano kolumny: {ROLE[rola]}")

    wynik = pd.DataFrame(index=df.index)
    for rola, cel in (("cycle", "cycle"), ("voltage", "voltage"), ("current", "current"),
                      ("q_charge", "q_ch"), ("q_discharge", "q_dis")):
        kolumna = mapowanie.get(rola)
        if kolumna:
            seria = df[kolumna]
            if not pd.api.types.is_numeric_dtype(seria):
                seria = seria.astype(str).str.replace(",", ".", regex=False).str.strip()
            wynik[cel] = pd.to_numeric(seria, errors="coerce")
        else:
            wynik[cel] = np.nan

    for kolumna_q, rola in (("q_ch", "q_charge"), ("q_dis", "q_discharge")):
        jedn = jednostka if jednostka != "auto" else jednostka_pojemnosci(mapowanie.get(rola))
        if jedn == "Ah":
            wynik[kolumna_q] = wynik[kolumna_q] * 1000
        wynik[kolumna_q] = wynik[kolumna_q].abs()

    wynik = wynik.dropna(subset=["cycle"])
    wynik["cycle"] = wynik["cycle"].astype(int)
    return wynik.reset_index(drop=True)


def segment(cykl: pd.DataFrame, rodzaj: str) -> tuple[np.ndarray, np.ndarray]:
    """Zwraca (pojemność [mAh], napięcie [V]) dla etapu ładowania lub rozładowania w danym cyklu."""
    kolumna_q = "q_ch" if rodzaj == "charge" else "q_dis"
    if cykl["current"].notna().any():
        maska = cykl["current"] > 0 if rodzaj == "charge" else cykl["current"] < 0
    else:
        przyrost = cykl[kolumna_q].diff().fillna(0) > 0
        maska = przyrost | przyrost.shift(-1, fill_value=False)
    fragment = cykl.loc[maska, [kolumna_q, "voltage"]].dropna()
    return fragment[kolumna_q].to_numpy(), fragment["voltage"].to_numpy()


def _calka(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return float("nan")
    kolejnosc = np.argsort(x)
    x, y = x[kolejnosc], y[kolejnosc]
    return float(np.sum((x[1:] - x[:-1]) * (y[1:] + y[:-1]) / 2))


def podsumowanie_cykli(dane: pd.DataFrame, masa_mg: float | None = None) -> pd.DataFrame:
    """Parametry każdego cyklu: pojemności, wydajność kulombowska, energia, średnie napięcie."""
    surowe = dane.groupby("cycle").size().max() > 2 and dane["voltage"].notna().any()
    wiersze = []
    for nr, cykl in dane.groupby("cycle", sort=True):
        if surowe:
            q_ch, v_ch = segment(cykl, "charge")
            q_dis, v_dis = segment(cykl, "discharge")
            wiersz = {
                "cykl": nr,
                "Q_ład [mAh]": q_ch.max() if len(q_ch) else np.nan,
                "Q_rozł [mAh]": q_dis.max() if len(q_dis) else np.nan,
                "E_ład [mWh]": _calka(q_ch, v_ch),
                "E_rozł [mWh]": _calka(q_dis, v_dis),
            }
        else:
            wiersz = {
                "cykl": nr,
                "Q_ład [mAh]": cykl["q_ch"].max(),
                "Q_rozł [mAh]": cykl["q_dis"].max(),
                "E_ład [mWh]": np.nan,
                "E_rozł [mWh]": np.nan,
            }
        wiersze.append(wiersz)

    tabela = pd.DataFrame(wiersze)
    tabela = tabela[tabela["Q_rozł [mAh]"] > 0].reset_index(drop=True)
    tabela["CE [%]"] = tabela["Q_rozł [mAh]"] / tabela["Q_ład [mAh]"] * 100
    tabela["Wydajność energetyczna [%]"] = tabela["E_rozł [mWh]"] / tabela["E_ład [mWh]"] * 100
    tabela["Śr. napięcie rozł. [V]"] = tabela["E_rozł [mWh]"] / tabela["Q_rozł [mAh]"]
    if masa_mg and masa_mg > 0:
        tabela["Q_rozł [mAh/g]"] = tabela["Q_rozł [mAh]"] / (masa_mg / 1000)
        tabela["Q_ład [mAh/g]"] = tabela["Q_ład [mAh]"] / (masa_mg / 1000)
    return tabela


def tabela_z_pojemnosci(cykle: np.ndarray, q_mah_g: np.ndarray) -> pd.DataFrame:
    """Tabela cykli w formacie aplikacji, gdy znana jest tylko pojemność właściwa rozładowania (np. dane z publikacji)."""
    puste = np.full(len(cykle), np.nan)
    return pd.DataFrame({
        "cykl": np.asarray(cykle, dtype=int),
        "Q_ład [mAh]": puste, "Q_rozł [mAh]": puste, "E_ład [mWh]": puste, "E_rozł [mWh]": puste,
        "CE [%]": puste, "Wydajność energetyczna [%]": puste, "Śr. napięcie rozł. [V]": puste,
        "Q_rozł [mAh/g]": np.asarray(q_mah_g, dtype=float), "Q_ład [mAh/g]": puste,
    })


def cykle_odstajace(pojemnosc: np.ndarray, prog: float = 0.03, okno: int = 9) -> np.ndarray:
    """Cykle odbiegające od lokalnej mediany o więcej niż `prog` (np. cykle kontrolne przy innym prądzie, zakłócenia)."""
    seria = pd.Series(np.asarray(pojemnosc, dtype=float))
    mediana = seria.rolling(okno, center=True, min_periods=3).median()
    return (np.abs(seria / mediana - 1) > prog).to_numpy()


def kolumna_pojemnosci(tabela: pd.DataFrame) -> str:
    return "Q_rozł [mAh/g]" if "Q_rozł [mAh/g]" in tabela.columns else "Q_rozł [mAh]"


def wskazniki(tabela: pd.DataFrame, cykl_ref: int, prog_soh: float) -> dict:
    kol = kolumna_pojemnosci(tabela)
    ref = tabela.loc[tabela["cykl"] >= cykl_ref].iloc[0]
    ostatni = tabela.iloc[-1]
    retencja = tabela[kol] / ref[kol] * 100
    pod_progiem = tabela[(tabela["cykl"] > ref["cykl"]) & (retencja < prog_soh)]
    stabilne = tabela[tabela["cykl"] >= max(5, cykl_ref)]
    return {
        "Pojemność początkowa": ref[kol],
        "Pojemność końcowa": ostatni[kol],
        "Liczba cykli": int(ostatni["cykl"]),
        "Retencja [%]": ostatni[kol] / ref[kol] * 100,
        "Pierwsza CE [%]": tabela["CE [%]"].iloc[0],
        "Średnia CE [%]": stabilne["CE [%]"].mean() if len(stabilne) else np.nan,
        "Śr. napięcie rozł. [V]": stabilne["Śr. napięcie rozł. [V]"].mean() if len(stabilne) else np.nan,
        "Wydajność energetyczna [%]": stabilne["Wydajność energetyczna [%]"].mean() if len(stabilne) else np.nan,
        f"Cykl spadku < {prog_soh:g}%": int(pod_progiem["cykl"].iloc[0]) if len(pod_progiem) else None,
    }


@dataclass
class Model:
    nazwa: str
    wzor: str
    funkcja: Callable
    liczba_parametrow: int


MODELE = [
    Model("liniowy", "Q₀ − k·n", lambda n, q0, k: q0 - k * n, 2),
    Model("pierwiastkowy (wzrost SEI)", "Q₀ − k·√n", lambda n, q0, k: q0 - k * np.sqrt(n), 2),
    Model("potęgowy", "Q₀ − k·nᶻ", lambda n, q0, k, z: q0 - k * np.power(n, z), 3),
    Model("wykładniczy", "Q₀·exp(−k·n)", lambda n, q0, k: q0 * np.exp(-k * n), 2),
]


def _start(model: Model, x: np.ndarray, y: np.ndarray) -> tuple[list[float], tuple]:
    q0 = float(np.median(y[: max(3, len(y) // 20)]))
    koniec = float(np.median(y[-max(3, len(y) // 20):]))
    zakres = max(float(x[-1]), 1.0)
    spadek = max(q0 - koniec, q0 * 1e-4)
    if model.nazwa == "liniowy":
        return [q0, spadek / zakres], ([0, -np.inf], [np.inf, np.inf])
    if model.nazwa.startswith("pierwiastkowy"):
        return [q0, spadek / np.sqrt(zakres)], ([0, -np.inf], [np.inf, np.inf])
    if model.nazwa == "potęgowy":
        return [q0, spadek / zakres ** 0.7, 0.7], ([0, 0, 0.05], [np.inf, np.inf, 3.0])
    return [q0, max(-np.log(max(koniec, 1e-9) / q0) / zakres, 1e-7)], ([0, -np.inf], [np.inf, np.inf])


def dopasuj(model: Model, x: np.ndarray, y: np.ndarray) -> np.ndarray | None:
    p0, granice = _start(model, x, y)
    try:
        parametry, _ = curve_fit(model.funkcja, x, y, p0=p0, bounds=granice, maxfev=20000)
        return parametry
    except (RuntimeError, ValueError):
        return None


def porownaj_modele(x: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    """Dopasowuje wszystkie modele i porównuje je kryteriami RMSE, R² i AIC."""
    wiersze = []
    n = len(x)
    for model in MODELE:
        parametry = dopasuj(model, x, y)
        if parametry is None:
            continue
        reszty = y - model.funkcja(x, *parametry)
        sse = float(np.sum(reszty ** 2))
        wiersze.append({
            "model": model.nazwa,
            "wzór": model.wzor,
            "parametry": parametry,
            "RMSE": np.sqrt(sse / n),
            "R²": 1 - sse / float(np.sum((y - y.mean()) ** 2)),
            "AIC": n * np.log(sse / n + 1e-12) + 2 * model.liczba_parametrow,
        })
    return pd.DataFrame(wiersze).sort_values("AIC").reset_index(drop=True)


def model_po_nazwie(nazwa: str) -> Model:
    return next(m for m in MODELE if m.nazwa == nazwa)


def cykl_przekroczenia(model: Model, parametry: np.ndarray, prog: float, x_max: float) -> float | None:
    """Pierwszy (względny) numer cyklu, w którym model spada poniżej progu pojemności."""
    siatka = np.linspace(0, x_max, 20001)
    wartosci = model.funkcja(siatka, *parametry)
    ponizej = np.nonzero(wartosci <= prog)[0]
    return float(siatka[ponizej[0]]) if len(ponizej) else None


def prognoza_bootstrap(
    model: Model,
    x: np.ndarray,
    y: np.ndarray,
    prog: float,
    x_max: float,
    powtorzenia: int = 200,
    seed: int = 0,
) -> dict:
    """Przedziały predykcji krzywej i cyklu końca życia metodą bootstrapu reszt."""
    parametry = dopasuj(model, x, y)
    if parametry is None:
        raise ValueError("Nie udało się dopasować modelu.")
    dopasowane = model.funkcja(x, *parametry)
    reszty = y - dopasowane
    rng = np.random.default_rng(seed)
    siatka = np.linspace(0, x_max, 400)

    krzywe, eol = [], []
    for _ in range(powtorzenia):
        y_bootstrap = dopasowane + rng.choice(reszty, size=len(reszty), replace=True)
        p_b = dopasuj(model, x, y_bootstrap)
        if p_b is None:
            continue
        krzywe.append(model.funkcja(siatka, *p_b))
        przekroczenie = cykl_przekroczenia(model, p_b, prog, x_max)
        eol.append(np.nan if przekroczenie is None else przekroczenie)

    krzywe = np.array(krzywe)
    eol = np.array(eol, dtype=float)
    trafione = eol[~np.isnan(eol)]
    return {
        "parametry": parametry,
        "siatka": siatka,
        "krzywa": model.funkcja(siatka, *parametry),
        "dolna": np.percentile(krzywe, 2.5, axis=0),
        "gorna": np.percentile(krzywe, 97.5, axis=0),
        "eol": cykl_przekroczenia(model, parametry, prog, x_max),
        "eol_przedzial": (np.percentile(trafione, 2.5), np.percentile(trafione, 97.5)) if len(trafione) > 10 else None,
        "udzial_eol": len(trafione) / max(len(eol), 1),
    }


def test_wsteczny(model: Model, x: np.ndarray, y: np.ndarray, frakcja: float) -> dict | None:
    """Uczy model na pierwszych cyklach i sprawdza błąd prognozy na pozostałych (MAPE)."""
    granica = max(int(len(x) * frakcja), 5)
    if granica >= len(x) - 2:
        return None
    parametry = dopasuj(model, x[:granica], y[:granica])
    if parametry is None:
        return None
    prognoza = model.funkcja(x[granica:], *parametry)
    return {
        "granica": granica,
        "x_test": x[granica:],
        "prognoza": prognoza,
        "MAPE [%]": float(np.mean(np.abs((y[granica:] - prognoza) / y[granica:])) * 100),
        "parametry": parametry,
    }


def krzywa_dqdv(q: np.ndarray, v: np.ndarray, krok_v: float = 0.005, okno: int = 9) -> tuple[np.ndarray, np.ndarray]:
    """Analiza pojemności przyrostowej metodą binowania napięcia.

    Przyrosty pojemności między kolejnymi pomiarami sumowane są w przedziałach napięcia o szerokości `krok_v`,
    a wynik wygładzany filtrem Savitzky'ego-Golaya. Metoda jest odporna na szum i niemonotoniczność napięcia.
    Znak: dodatni dla ładowania, ujemny dla rozładowania.
    """
    q = np.asarray(q, dtype=float)
    v = np.asarray(v, dtype=float)
    if len(q) < 10:
        return np.array([]), np.array([])
    dq = np.diff(q)
    v_srodek = (v[1:] + v[:-1]) / 2
    maska = dq > 0
    v_min, v_max = float(np.min(v)), float(np.max(v))
    liczba_binow = max(int(round((v_max - v_min) / krok_v)), 10)
    suma, krawedzie = np.histogram(v_srodek[maska], bins=liczba_binow, range=(v_min, v_max), weights=dq[maska])
    srodki = (krawedzie[:-1] + krawedzie[1:]) / 2
    gestosc = suma / (krawedzie[1] - krawedzie[0])
    if len(gestosc) > okno:
        gestosc = savgol_filter(gestosc, okno, 2)
    znak = -1.0 if v[-1] < v[0] else 1.0
    return srodki, znak * gestosc


def piki_dqdv(v: np.ndarray, dqdv: np.ndarray, czulosc: float = 0.15) -> list[float]:
    if len(dqdv) == 0:
        return []
    sygnal = np.abs(dqdv)
    piki, _ = find_peaks(sygnal, prominence=czulosc * sygnal.max(), distance=max(len(v) // 40, 1))
    return [float(v[i]) for i in piki]
