"""Obliczenia do syntezy wysokoentropowych analogów błękitu pruskiego (HE-PBA) metodą współstrącania."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

R = 8.314462618
FARADAY_MAH = 26801.48

ATOMIC_MASSES = {
    "H": 1.008, "Li": 6.94, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45,
    "K": 39.098, "Ca": 40.078, "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938, "Fe": 55.845,
    "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38, "Ga": 69.723, "Se": 78.971, "Br": 79.904,
    "Rb": 85.468, "Sr": 87.62, "Zr": 91.224, "Nb": 92.906, "Mo": 95.95, "Ag": 107.87, "In": 114.82,
    "Sn": 118.71, "I": 126.90, "Cs": 132.91, "Ba": 137.33, "La": 138.91, "Ce": 140.12,
}

METALE = ["Ti", "V", "Cr", "Mn", "Fe", "Ni", "Cu", "Zr", "Nb", "Mg", "Zn", "Al"]

SOLE = {
    "Ti": ["TiCl3", "TiCl4", "TiOSO4", "Ti(SO4)2"],
    "V": ["VCl3", "VOSO4·5H2O"],
    "Cr": ["CrCl3·6H2O", "Cr(NO3)3·9H2O", "KCr(SO4)2·12H2O"],
    "Mn": ["MnCl2·4H2O", "MnSO4·H2O", "Mn(CH3COO)2·4H2O", "Mn(NO3)2·4H2O"],
    "Fe": ["FeCl2", "FeCl2·4H2O", "FeSO4·7H2O", "(NH4)2Fe(SO4)2·6H2O"],
    "Ni": ["NiCl2·6H2O", "Ni(NO3)2·6H2O", "NiSO4·6H2O", "Ni(CH3COO)2·4H2O"],
    "Cu": ["CuCl2", "CuCl2·2H2O", "CuSO4·5H2O", "Cu(NO3)2·3H2O", "Cu(CH3COO)2·H2O"],
    "Zr": ["ZrCl4", "ZrOCl2·8H2O", "Zr(SO4)2·4H2O"],
    "Nb": ["NbCl5", "NH4NbO(C2O4)2"],
    "Mg": ["MgCl2", "MgCl2·6H2O", "MgSO4·7H2O", "Mg(NO3)2·6H2O", "Mg(CH3COO)2·4H2O"],
    "Zn": ["ZnCl2", "ZnSO4·7H2O", "Zn(NO3)2·6H2O", "Zn(CH3COO)2·2H2O"],
    "Al": ["AlCl3", "AlCl3·6H2O", "Al(NO3)3·9H2O", "Al2(SO4)3·18H2O", "KAl(SO4)2·12H2O"],
}

ODCZYNNIKI_LABORATORIUM = {
    "ZrCl4", "NbCl5", "MgCl2", "ZnCl2", "AlCl3", "VCl3", "CrCl3·6H2O", "FeCl2", "MnCl2·4H2O",
    "NiCl2·6H2O", "CuCl2", "Na4[Fe(CN)6]·10H2O", "NaCl", "Na3C6H5O7·2H2O",
}

NAZWY = {
    "TiCl3": "chlorek tytanu(III)", "TiCl4": "chlorek tytanu(IV)", "TiOSO4": "siarczan tytanylu",
    "Ti(SO4)2": "siarczan tytanu(IV)",
    "VCl3": "chlorek wanadu(III)", "VOSO4·5H2O": "siarczan wanadylu pentahydrat",
    "CrCl3·6H2O": "chlorek chromu(III) heksahydrat", "Cr(NO3)3·9H2O": "azotan chromu(III) nonahydrat",
    "KCr(SO4)2·12H2O": "ałun chromowo-potasowy",
    "MnCl2·4H2O": "chlorek manganu(II) tetrahydrat", "MnSO4·H2O": "siarczan manganu(II) monohydrat",
    "Mn(CH3COO)2·4H2O": "octan manganu(II) tetrahydrat", "Mn(NO3)2·4H2O": "azotan manganu(II) tetrahydrat",
    "FeCl2": "chlorek żelaza(II)", "FeCl2·4H2O": "chlorek żelaza(II) tetrahydrat",
    "FeSO4·7H2O": "siarczan żelaza(II) heptahydrat", "(NH4)2Fe(SO4)2·6H2O": "sól Mohra",
    "NiCl2·6H2O": "chlorek niklu(II) heksahydrat", "Ni(NO3)2·6H2O": "azotan niklu(II) heksahydrat",
    "NiSO4·6H2O": "siarczan niklu(II) heksahydrat", "Ni(CH3COO)2·4H2O": "octan niklu(II) tetrahydrat",
    "CuCl2": "chlorek miedzi(II)", "CuCl2·2H2O": "chlorek miedzi(II) dihydrat",
    "CuSO4·5H2O": "siarczan miedzi(II) pentahydrat", "Cu(NO3)2·3H2O": "azotan miedzi(II) trihydrat",
    "Cu(CH3COO)2·H2O": "octan miedzi(II) monohydrat",
    "ZrCl4": "chlorek cyrkonu(IV)", "ZrOCl2·8H2O": "chlorek cyrkonylu oktahydrat",
    "Zr(SO4)2·4H2O": "siarczan cyrkonu(IV) tetrahydrat",
    "NbCl5": "chlorek niobu(V)", "NH4NbO(C2O4)2": "szczawian amonowo-niobowy",
    "MgCl2": "chlorek magnezu", "MgCl2·6H2O": "chlorek magnezu heksahydrat",
    "MgSO4·7H2O": "siarczan magnezu heptahydrat", "Mg(NO3)2·6H2O": "azotan magnezu heksahydrat",
    "Mg(CH3COO)2·4H2O": "octan magnezu tetrahydrat",
    "ZnCl2": "chlorek cynku(II)", "ZnSO4·7H2O": "siarczan cynku heptahydrat",
    "Zn(NO3)2·6H2O": "azotan cynku heksahydrat", "Zn(CH3COO)2·2H2O": "octan cynku dihydrat",
    "AlCl3": "chlorek glinu", "AlCl3·6H2O": "chlorek glinu heksahydrat", "Al(NO3)3·9H2O": "azotan glinu nonahydrat",
    "Al2(SO4)3·18H2O": "siarczan glinu oktadekahydrat", "KAl(SO4)2·12H2O": "ałun glinowo-potasowy",
    "Na4[Fe(CN)6]·10H2O": "heksacyjanożelazian(II) sodu dekahydrat",
    "K4[Fe(CN)6]·3H2O": "heksacyjanożelazian(II) potasu trihydrat",
    "Na3[Fe(CN)6]": "heksacyjanożelazian(III) sodu",
    "Na3C6H5O7·2H2O": "cytrynian trisodu dihydrat",
    "NaCl": "chlorek sodu",
}

AKTYWNE_REDOKS = {"Ti", "V", "Mn", "Fe"}

HEKSACYJANOZELAZIANY = {
    "Na4[Fe(CN)6]·10H2O (heksacyjanożelazian(II) sodu)": "Na4[Fe(CN)6]·10H2O",
    "K4[Fe(CN)6]·3H2O (heksacyjanożelazian(II) potasu)": "K4[Fe(CN)6]·3H2O",
    "Na3[Fe(CN)6] (heksacyjanożelazian(III) sodu)": "Na3[Fe(CN)6]",
}

CYTRYNIAN_SODU = "Na3C6H5O7·2H2O"
CHLOREK_SODU = "NaCl"

_TOKEN = re.compile(r"([A-Z][a-z]?|\(|\)|\[|\]|\d+(?:\.\d+)?)")


def _parse_group(tokens: list[str], pos: int) -> tuple[dict[str, float], int]:
    sklad: dict[str, float] = {}
    while pos < len(tokens):
        token = tokens[pos]
        if token in "([":
            wewnatrz, pos = _parse_group(tokens, pos + 1)
            mnoznik, pos = _read_number(tokens, pos)
            for pierwiastek, liczba in wewnatrz.items():
                sklad[pierwiastek] = sklad.get(pierwiastek, 0.0) + liczba * mnoznik
        elif token in ")]":
            return sklad, pos + 1
        elif token[0].isalpha():
            if token not in ATOMIC_MASSES:
                raise ValueError(f"Nieznany pierwiastek: {token}")
            liczba, pos = _read_number(tokens, pos + 1)
            sklad[token] = sklad.get(token, 0.0) + liczba
        else:
            raise ValueError(f"Nieoczekiwany fragment wzoru: {token}")
    return sklad, pos


def _read_number(tokens: list[str], pos: int) -> tuple[float, int]:
    if pos < len(tokens) and re.fullmatch(r"\d+(?:\.\d+)?", tokens[pos]):
        return float(tokens[pos]), pos + 1
    return 1.0, pos


def sklad_pierwiastkowy(wzor: str) -> dict[str, float]:
    """Zwraca liczbę atomów każdego pierwiastka; obsługuje nawiasy, ułamki i hydraty (· lub *)."""
    wzor = wzor.replace(" ", "")
    czesci = re.split(r"[·*•]", wzor)
    wynik: dict[str, float] = {}
    for nr, czesc in enumerate(czesci):
        if not czesc:
            continue
        dopasowanie = re.match(r"^(\d+(?:\.\d+)?)(?=[A-Z(\[])", czesc)
        mnoznik = 1.0
        if dopasowanie and nr > 0:
            mnoznik = float(dopasowanie.group(1))
            czesc = czesc[dopasowanie.end():]
        tokeny = _TOKEN.findall(czesc)
        if "".join(tokeny) != czesc:
            raise ValueError(f"Nieprawidłowy wzór: {wzor}")
        sklad, _ = _parse_group(tokeny, 0)
        for pierwiastek, liczba in sklad.items():
            wynik[pierwiastek] = wynik.get(pierwiastek, 0.0) + liczba * mnoznik
    return wynik


_INDEKSY = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def ladny_wzor(wzor: str) -> str:
    """Zamienia indeksy stechiometryczne na indeksy dolne, np. MnCl2·4H2O -> MnCl₂·4H₂O."""
    return re.sub(r"(?<=[A-Za-z)\]])(\d+(?:\.\d+)?)", lambda m: m.group(1).translate(_INDEKSY), wzor)


def masa_molowa(wzor: str) -> float:
    return sum(ATOMIC_MASSES[p] * n for p, n in sklad_pierwiastkowy(wzor).items())


def entropia_konfiguracyjna(udzialy: dict[str, float]) -> float:
    """S_conf = -R * suma(x_i ln x_i) dla podsieci metali przejściowych [J/(mol·K)]."""
    suma = sum(udzialy.values())
    return -R * sum((x / suma) * math.log(x / suma) for x in udzialy.values() if x > 0)


def klasa_entropii(s_conf: float) -> str:
    w_r = s_conf / R
    if w_r >= 1.5:
        return "wysokoentropowy (S ≥ 1,5R)"
    if w_r >= 1.0:
        return "średnioentropowy (1R ≤ S < 1,5R)"
    return "niskoentropowy (S < 1R)"


def wzor_produktu(udzialy: dict[str, float], sod: float, woda: float, kation: str = "Na") -> str:
    suma = sum(udzialy.values())
    metale = "".join(f"{m}{x / suma:.3g}" for m, x in udzialy.items() if x > 0)
    wzor = f"{kation}{sod:g}({metale})[Fe(CN)6]"
    return f"{wzor}·{woda:g}H2O" if woda > 0 else wzor


def nazwa_odczynnika(wzor: str, zapasowa: str = "") -> str:
    return NAZWY.get(wzor, zapasowa or wzor)


def na_liscie_laboratorium(wzor: str) -> bool:
    return wzor in ODCZYNNIKI_LABORATORIUM


def atomy_metalu(wzor_soli: str, metal: str) -> float:
    """Liczba atomów danego metalu w jednostce wzoru soli (0, jeśli wzór jest niepoprawny lub go nie zawiera)."""
    try:
        return sklad_pierwiastkowy(wzor_soli).get(metal, 0.0)
    except ValueError:
        return 0.0


def liczba_elektronow(udzialy: dict[str, float], aktywne: set[str], sod: float) -> float:
    """Elektrony na jednostkę wzoru: Fe w Fe(CN)6 + aktywne metale w podsieci M, ograniczone zawartością sodu."""
    suma = sum(udzialy.values())
    udzial_aktywnych = sum(x / suma for m, x in udzialy.items() if m in aktywne) if suma > 0 else 0.0
    return min(sod, 1 + udzial_aktywnych)


def pojemnosc_teoretyczna(masa_molowa_produktu: float, liczba_elektronow: float) -> float:
    """Pojemność teoretyczna [mAh/g] = n·F / (3,6·M)."""
    return liczba_elektronow * FARADAY_MAH / masa_molowa_produktu


@dataclass
class Odczynnik:
    nazwa: str
    wzor: str
    mmol: float
    roztwor: str

    @property
    def masa_molowa(self) -> float:
        return masa_molowa(self.wzor)

    @property
    def masa_g(self) -> float:
        return self.mmol * self.masa_molowa / 1000


def plan_syntezy(
    udzialy: dict[str, float],
    sole: dict[str, str],
    n_metali_mmol: float,
    heksacyjanian: str,
    stosunek_fecn: float,
    stosunek_cytrynianu: float,
    v_roztworu_a_ml: float,
    v_roztworu_b_ml: float,
    n_nacl_mmol: float = 0.0,
    roztwor_nacl: str = "B",
) -> tuple[list[Odczynnik], dict[str, float]]:
    """Naważki odczynników dla współstrącania.

    Roztwór A: sole metali (+ cytrynian sodu jako czynnik chelatujący).
    Roztwór B: heksacyjanożelazian.
    NaCl (opcjonalnie): zadana ilość [mmol] w roztworze A lub B, jako dodatkowe źródło sodu.
    """
    suma = sum(udzialy.values())
    if suma <= 0:
        raise ValueError("Suma udziałów metali musi być dodatnia.")

    odczynniki = []
    for metal, x in udzialy.items():
        if x <= 0:
            continue
        atomy = atomy_metalu(sole[metal], metal)
        if atomy <= 0:
            raise ValueError(f"Prekursor {sole[metal]} nie zawiera metalu {metal}.")
        odczynniki.append(Odczynnik(nazwa_odczynnika(sole[metal], f"sól {metal}"), sole[metal],
                                    n_metali_mmol * x / suma / atomy, "A"))
    if stosunek_cytrynianu > 0:
        odczynniki.append(Odczynnik(nazwa_odczynnika(CYTRYNIAN_SODU), CYTRYNIAN_SODU,
                                    n_metali_mmol * stosunek_cytrynianu, "A"))
    odczynniki.append(Odczynnik(nazwa_odczynnika(heksacyjanian, "heksacyjanożelazian"), heksacyjanian,
                                n_metali_mmol * stosunek_fecn, "B"))
    if n_nacl_mmol > 0:
        odczynniki.append(Odczynnik(nazwa_odczynnika(CHLOREK_SODU), CHLOREK_SODU, n_nacl_mmol, roztwor_nacl))

    stezenia = {
        "A [M] (metale)": n_metali_mmol / v_roztworu_a_ml if v_roztworu_a_ml > 0 else float("nan"),
        "B [M] (Fe(CN)6)": n_metali_mmol * stosunek_fecn / v_roztworu_b_ml if v_roztworu_b_ml > 0 else float("nan"),
    }
    return odczynniki, stezenia
