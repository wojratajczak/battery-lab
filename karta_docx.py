"""Karta syntezy HE-PBA w formacie Word (.docx)."""

from __future__ import annotations

import io
import re
from datetime import date

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

import synthesis

AKCENT = RGBColor(0x1F, 0x5F, 0x7F)
SZARY = RGBColor(0x6B, 0x72, 0x80)
TLO_NAGLOWKA = "DCE8F0"
_INDEKS = re.compile(r"(?<=[A-Za-z)\]])(\d+(?:\.\d+)?)")


def _liczba(wartosc: float, miejsca: int) -> str:
    return f"{wartosc:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def _wzor(akapit, wzor: str, pogrubienie: bool = False, rozmiar: float | None = None) -> None:
    """Wstawia wzór chemiczny z indeksami stechiometrycznymi jako indeksami dolnymi."""
    pozycja = 0
    fragmenty = []
    for dopasowanie in _INDEKS.finditer(wzor):
        fragmenty.append((wzor[pozycja:dopasowanie.start()], False))
        fragmenty.append((dopasowanie.group(1).replace(".", ","), True))
        pozycja = dopasowanie.end()
    fragmenty.append((wzor[pozycja:], False))
    for tekst, indeks in fragmenty:
        if not tekst:
            continue
        run = akapit.add_run(tekst)
        run.bold = pogrubienie
        run.font.subscript = indeks
        if rozmiar:
            run.font.size = Pt(rozmiar)


def _cieniowanie(komorka, kolor: str) -> None:
    wlasciwosci = komorka._tc.get_or_add_tcPr()
    cien = OxmlElement("w:shd")
    cien.set(qn("w:val"), "clear")
    cien.set(qn("w:color"), "auto")
    cien.set(qn("w:fill"), kolor)
    wlasciwosci.append(cien)


def _linia_do_pisania(dokument, szerokosc: Cm) -> None:
    akapit = dokument.add_paragraph()
    akapit.paragraph_format.space_before = Pt(12)
    akapit.paragraph_format.space_after = Pt(0)
    akapit.paragraph_format.tab_stops.add_tab_stop(szerokosc, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.LINES)
    run = akapit.add_run("\t")
    run.font.color.rgb = RGBColor(0xA0, 0xA7, 0xB0)


def _tabela(dokument, naglowki: list[str] | None, wiersze: list[list], szerokosci_cm: list[float],
            wyrownaj_prawo: set[int] = frozenset(), kolumny_wzorow: set[int] = frozenset()):
    """Tabela z opcjonalnym cieniowanym nagłówkiem; komórki z kolumn_wzorow są formatowane jak wzory chemiczne."""
    liczba_wierszy = len(wiersze) + (1 if naglowki else 0)
    tabela = dokument.add_table(rows=liczba_wierszy, cols=len(szerokosci_cm))
    tabela.style = "Table Grid"
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabela.autofit = False
    wszystkie = ([naglowki] if naglowki else []) + wiersze
    for nr_wiersza, wiersz in enumerate(wszystkie):
        jest_naglowkiem = naglowki is not None and nr_wiersza == 0
        for nr_kolumny, wartosc in enumerate(wiersz):
            komorka = tabela.cell(nr_wiersza, nr_kolumny)
            komorka.width = Cm(szerokosci_cm[nr_kolumny])
            akapit = komorka.paragraphs[0]
            akapit.paragraph_format.space_after = Pt(0)
            akapit.paragraph_format.keep_with_next = nr_wiersza < len(wszystkie) - 1
            if nr_kolumny in wyrownaj_prawo and not jest_naglowkiem:
                akapit.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if jest_naglowkiem:
                _cieniowanie(komorka, TLO_NAGLOWKA)
                akapit.add_run(str(wartosc)).bold = True
            elif nr_kolumny in kolumny_wzorow:
                _wzor(akapit, str(wartosc))
            else:
                akapit.add_run(str(wartosc))
            for run in akapit.runs:
                run.font.size = Pt(10)
    for nr_kolumny, szerokosc in enumerate(szerokosci_cm):
        tabela.columns[nr_kolumny].width = Cm(szerokosc)
    for wiersz in tabela.rows:
        wlasciwosci = wiersz._tr.get_or_add_trPr()
        nie_dziel = OxmlElement("w:cantSplit")
        wlasciwosci.append(nie_dziel)
    return tabela


def _naglowek(dokument, tekst: str) -> None:
    akapit = dokument.add_heading(tekst, level=1)
    akapit.paragraph_format.space_before = Pt(14)
    akapit.paragraph_format.space_after = Pt(6)
    akapit.paragraph_format.keep_with_next = True
    for run in akapit.runs:
        run.font.color.rgb = AKCENT
        run.font.size = Pt(13)
        run.font.name = "Calibri"


def karta_syntezy(
    *,
    wzor: str,
    udzialy: dict[str, float],
    sole: dict[str, str],
    aktywne: set[str],
    n_metali_mmol: float,
    stosunek_fecn: float,
    stosunek_cytrynianu: float,
    heksacyjanian: str,
    v_a_ml: float,
    v_b_ml: float,
    sod: float,
    woda: float,
    m_produktu: float,
    n_nacl_mmol: float = 0.0,
    roztwor_nacl: str = "B",
    s_conf: float,
    elektrony: float,
    q_teor: float,
    odczynniki: list[synthesis.Odczynnik],
    stezenia: dict[str, float],
) -> bytes:
    """Zwraca kartę syntezy jako plik .docx (bajty)."""
    dokument = Document()
    powiekszenie = dokument.settings.element.find(qn("w:zoom"))
    if powiekszenie is not None:
        powiekszenie.set(qn("w:percent"), "100")
    sekcja = dokument.sections[0]
    sekcja.page_width, sekcja.page_height = Cm(21.0), Cm(29.7)
    sekcja.left_margin = sekcja.right_margin = Cm(2.0)
    sekcja.top_margin = sekcja.bottom_margin = Cm(2.0)

    normalny = dokument.styles["Normal"]
    normalny.font.name = "Calibri"
    normalny.font.size = Pt(11)
    normalny.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")

    stopka = sekcja.footer.paragraphs[0]
    stopka.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = stopka.add_run(f"Battery Lab · karta syntezy · wygenerowano {date.today():%d.%m.%Y}")
    run.font.size = Pt(8)
    run.font.color.rgb = SZARY

    tytul = dokument.add_paragraph()
    tytul.paragraph_format.space_after = Pt(2)
    run = tytul.add_run("Karta syntezy")
    run.bold = True
    run.font.size = Pt(22)
    run.font.color.rgb = AKCENT

    podtytul = dokument.add_paragraph()
    podtytul.paragraph_format.space_after = Pt(10)
    run = podtytul.add_run("Współstrącanie analogu błękitu pruskiego: ")
    run.font.size = Pt(12)
    _wzor(podtytul, wzor, pogrubienie=True, rozmiar=12)

    _tabela(dokument, None,
            [["Data syntezy", ""], ["Nr próbki", ""], ["Wykonał(a)", ""], ["Cel / uwagi", ""]],
            [4.0, 13.0])

    suma = sum(udzialy.values())
    _naglowek(dokument, "Skład podsieci M")
    _tabela(
        dokument,
        ["Metal", "Udział molowy", "Prekursor", "Aktywny redoks"],
        [[metal, _liczba(x / suma, 3), sole[metal], "tak" if metal in aktywne else "nie"]
         for metal, x in udzialy.items() if x > 0],
        [2.5, 3.5, 7.5, 3.5],
        wyrownaj_prawo={1},
        kolumny_wzorow={2},
    )

    _naglowek(dokument, "Parametry syntezy")
    _tabela(
        dokument,
        None,
        [
            ["Ilość metali M", f"{_liczba(n_metali_mmol, 3)} mmol"],
            ["Heksacyjanożelazian", heksacyjanian],
            ["Stosunek molowy Fe(CN)₆ : M", _liczba(stosunek_fecn, 2)],
            ["Stosunek molowy cytrynian : M", _liczba(stosunek_cytrynianu, 2)],
            ["Objętość roztworu A", f"{_liczba(v_a_ml, 1)} mL"],
            ["Objętość roztworu B", f"{_liczba(v_b_ml, 1)} mL"],
            ["Zakładana zawartość Na (x)", _liczba(sod, 2)],
            ["Woda krystalizacyjna (y)", _liczba(woda, 2)],
            ["Chlorek sodu (NaCl)", f"{_liczba(n_nacl_mmol, 3)} mmol w roztworze {roztwor_nacl} "
             f"({_liczba(n_nacl_mmol / (v_a_ml if roztwor_nacl == 'A' else v_b_ml), 2)} mol/L)"
             if n_nacl_mmol > 0 else "nie dodano"],
        ],
        [7.0, 10.0],
        kolumny_wzorow={1},
    )

    _naglowek(dokument, "Charakterystyka produktu (wartości teoretyczne)")
    _tabela(
        dokument,
        None,
        [
            ["Wzór", wzor],
            ["Masa molowa", f"{_liczba(m_produktu, 2)} g/mol"],
            ["Entropia konfiguracyjna", f"{_liczba(s_conf / synthesis.R, 3)} R  ({_liczba(s_conf, 2)} J/(mol·K)), "
                                        f"materiał {synthesis.klasa_entropii(s_conf).split(' (')[0]}"],
            ["Pojemność teoretyczna", f"{_liczba(q_teor, 0)} mAh/g  ({_liczba(elektrony, 2)} e⁻ na jednostkę wzoru)"],
            ["Wydajność teoretyczna", f"{_liczba(n_metali_mmol * m_produktu / 1000, 4)} g"],
        ],
        [7.0, 10.0],
        kolumny_wzorow={1},
    )

    _naglowek(dokument, "Naważki")
    for roztwor, objetosc, opis in (("A", v_a_ml, "sole metali"), ("B", v_b_ml, "heksacyjanożelazian")):
        pozycje = [o for o in odczynniki if o.roztwor == roztwor]
        if not pozycje:
            continue
        akapit = dokument.add_paragraph()
        akapit.paragraph_format.space_before = Pt(6)
        akapit.paragraph_format.space_after = Pt(4)
        akapit.paragraph_format.keep_with_next = True
        akapit.add_run(f"Roztwór {roztwor} ({opis}), {_liczba(objetosc, 1)} mL").bold = True
        _tabela(
            dokument,
            ["Odczynnik", "Wzór", "M [g/mol]", "n [mmol]", "Masa [g]", "Odważono [g]"],
            [[o.nazwa, o.wzor, _liczba(o.masa_molowa, 2), _liczba(o.mmol, 3), _liczba(o.masa_g, 4), ""]
             for o in pozycje],
            [5.0, 3.8, 2.0, 1.9, 2.0, 2.3],
            wyrownaj_prawo={2, 3, 4},
            kolumny_wzorow={1},
        )

    akapit = dokument.add_paragraph()
    akapit.paragraph_format.space_before = Pt(8)
    akapit.add_run("Stężenia: ").bold = True
    akapit.add_run(f"metale w roztworze A {_liczba(stezenia['A [M] (metale)'], 3)} M, "
                   f"Fe(CN)₆ w roztworze B {_liczba(stezenia['B [M] (Fe(CN)6)'], 3)} M.")

    _naglowek(dokument, "Przebieg syntezy i obserwacje")
    szerokosc_tekstu = sekcja.page_width - sekcja.left_margin - sekcja.right_margin
    for _ in range(12):
        _linia_do_pisania(dokument, szerokosc_tekstu)

    _naglowek(dokument, "Założenia obliczeń")
    for tekst in (
        "Entropia konfiguracyjna podsieci M: S = −R·Σ xᵢ·ln xᵢ. Materiał wysokoentropowy dla S ≥ 1,5R, "
        "średnioentropowy dla 1R ≤ S < 1,5R.",
        "Pojemność teoretyczna: Q = n·F / (3,6·M), gdzie n = min(x, 1 + udział metali aktywnych redoks). "
        "Uwzględnia redoks Fe w Fe(CN)₆ oraz metali oznaczonych w tabeli składu jako aktywne.",
        "Naważki soli liczone są na liczbę atomów metalu w jednostce wzoru prekursora. "
        "Wydajność teoretyczna liczona jest na sumę metali M.",
    ):
        akapit = dokument.add_paragraph(style="List Bullet")
        akapit.paragraph_format.space_after = Pt(2)
        run = akapit.add_run(tekst)
        run.font.size = Pt(9)
        run.font.color.rgb = SZARY

    bufor = io.BytesIO()
    dokument.save(bufor)
    return bufor.getvalue()
