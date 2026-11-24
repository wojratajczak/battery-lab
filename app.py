"""Battery Lab - asystent badań nad katodami do ogniw sodowo-jonowych.

Uruchomienie: streamlit run app.py
"""

from __future__ import annotations

import hmac
import os
import time
from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import cycling
import demo_data
import karta_docx
import openalex_client as oa
import synthesis
import zenodo_data

st.set_page_config(page_title="Battery Lab", page_icon="🔋", layout="wide")

KOLORY = ["#3FA7D6", "#E4572E", "#76B041", "#9B5DE5", "#F4A261", "#17BEBB", "#ADB5BD"]
SZABLON = "plotly_dark"
ROK = date.today().year
TEMATY_DOMYSLNE = (
    "Prussian blue sodium cathode\n"
    "layered oxide sodium cathode\n"
    "polyanionic sodium cathode\n"
    "hard carbon sodium anode"
)


def wyglad(fig: go.Figure, wysokosc: int = 380, **kwargs) -> go.Figure:
    fig.update_layout(template=SZABLON, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=wysokosc, margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", yanchor="top", y=-0.3, x=0, title=None), **kwargs)
    return fig


def wykres_poziomy(df: pd.DataFrame, x: str, y: str, tytul: str, kolor: str) -> go.Figure:
    dane = df.sort_values(x)
    fig = px.bar(dane, x=x, y=y, orientation="h", title=tytul, text=x)
    fig.update_traces(marker_color=kolor, textposition="outside", cliponaxis=False)
    fig.update_yaxes(title=None)
    fig.update_xaxes(title=None, showticklabels=False)
    return wyglad(fig, wysokosc=max(300, 32 * len(dane) + 80))


def sekret(nazwa: str) -> str:
    try:
        wartosc = st.secrets.get(nazwa, "")
    except Exception:
        wartosc = ""
    return str(wartosc or os.environ.get(nazwa, ""))


def klucz_z_konfiguracji() -> str:
    return sekret("OPENALEX_API_KEY")


def dostep_przyznany() -> bool:
    haslo = sekret("APP_PASSWORD")
    if not haslo or st.session_state.get("zalogowany"):
        return True
    _, srodek, _ = st.columns([1, 1.2, 1])
    with srodek:
        st.title("🔋 Battery Lab")
        st.caption("Dostęp chroniony hasłem.")
        with st.form("logowanie"):
            wpisane = st.text_input("Hasło", type="password")
            if st.form_submit_button("Wejdź", type="primary", width="stretch"):
                if hmac.compare_digest(wpisane.encode("utf-8"), haslo.encode("utf-8")):
                    st.session_state["zalogowany"] = True
                    st.rerun()
                time.sleep(2)
                st.error("Nieprawidłowe hasło.")
    return False


@st.cache_data(ttl=86400, show_spinner=False)
def oa_trend(filtr: str, klucz: str) -> pd.DataFrame:
    return oa.trend_roczny(filtr, klucz or None)


@st.cache_data(ttl=86400, show_spinner=False)
def oa_grupy(filtr: str, pole: str, limit: int, klucz: str) -> pd.DataFrame:
    return oa.grupuj(filtr, pole, limit, klucz or None)


@st.cache_data(ttl=86400, show_spinner=False)
def oa_prace(filtr: str, sortowanie: str, limit: int, klucz: str) -> tuple[pd.DataFrame, int]:
    return oa.prace(filtr, sortowanie, limit, klucz or None)


@st.cache_data(show_spinner=False)
def analiza_demo() -> dict[str, tuple[pd.DataFrame, float, pd.DataFrame]]:
    wynik = {}
    for nazwa, (surowe, masa) in demo_data.dane_demo().items():
        std = cycling.standaryzuj(surowe, cycling.zgadnij_kolumny(list(surowe.columns)))
        wynik[nazwa] = (std, masa, cycling.podsumowanie_cykli(std, masa))
    return wynik


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def dane_rzeczywiste():
    return zenodo_data.dane_namnhcf()


@st.cache_data(show_spinner=False)
def przyklad_csv() -> bytes:
    surowe = demo_data.symuluj_ogniwo(demo_data.OGNIWA_DEMO[0], liczba_cykli=50)
    return surowe.to_csv(index=False, sep="\t").encode("utf-8")


@st.cache_data(show_spinner=False)
def wczytaj(zawartosc: bytes, nazwa: str) -> pd.DataFrame:
    return cycling.wczytaj_plik(zawartosc, nazwa)


@st.cache_data(show_spinner=False)
def analiza_pliku(zawartosc: bytes, nazwa: str, mapowanie: tuple, jednostka: str, masa: float):
    std = cycling.standaryzuj(wczytaj(zawartosc, nazwa), dict(mapowanie), jednostka)
    return std, cycling.podsumowanie_cykli(std, masa)


@st.cache_data(show_spinner=False)
def bootstrap(nazwa_modelu: str, x: np.ndarray, y: np.ndarray, prog: float, x_max: float) -> dict:
    return cycling.prognoza_bootstrap(cycling.model_po_nazwie(nazwa_modelu), x, y, prog, x_max)


# ---------------------------------------------------------------------------------------------
# Radar literatury
# ---------------------------------------------------------------------------------------------

def zakladka_literatura(klucz: str) -> None:
    st.subheader("📚 Radar literatury")
    st.caption("Dane na żywo z otwartej bazy publikacji naukowych OpenAlex. "
               "Wyszukiwanie obejmuje tytuły i abstrakty; wyniki są zapamiętywane na 24 godziny.")

    with st.form("wyszukiwanie"):
        k1, k2, k3 = st.columns([3, 2, 1])
        fraza = k1.text_input("Temat badań", "Prussian blue sodium",
                              help="Np. high-entropy Prussian blue, alluaudite sodium, sodium-ion cathode. "
                                   "Można używać AND, OR, NOT oraz cudzysłowów.")
        lata = k2.slider("Lata publikacji", 1990, ROK, (2010, ROK))
        tylko_artykuly = k3.checkbox("Tylko artykuły", value=True)
        st.form_submit_button("🔍 Szukaj", type="primary")

    filtr = oa.filtr(fraza, lata[0], lata[1], tylko_artykuly)
    try:
        with st.spinner("Pobieram dane z OpenAlex…"):
            trend = oa_trend(filtr, klucz)
            cytowane, liczba = oa_prace(filtr, "cited_by_count:desc", 25, klucz)
            najnowsze, _ = oa_prace(filtr, "publication_date:desc", 8, klucz)
            otwarte = oa_grupy(filtr, "open_access.is_oa", 2, klucz)
    except oa.BladOpenAlex as blad:
        st.error(f"Nie udało się pobrać danych: {blad}")
        return

    if liczba == 0:
        st.warning("Brak publikacji dla tego zapytania. Spróbuj ogólniejszej frazy albo szerszego zakresu lat.")
        return

    liczba_oa = int(otwarte.loc[otwarte["id"] == "true", "liczba"].sum())
    w_tym_roku = int(trend.loc[trend["rok"] == ROK, "liczba"].sum())
    poprzedni = trend.set_index("rok")["liczba"]
    rok_a, rok_b = ROK - 1, ROK - 2
    zmiana = None
    if poprzedni.get(rok_b, 0) > 0:
        zmiana = (poprzedni.get(rok_a, 0) / poprzedni[rok_b] - 1) * 100

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Publikacje", f"{liczba:,}".replace(",", " "), border=True)
    m2.metric(f"W {ROK} r. (do dziś)", w_tym_roku, border=True)
    m3.metric(f"Dynamika {rok_a} vs {rok_b}", f"{zmiana:+.0f}%" if zmiana is not None else "–", border=True)
    m4.metric("W otwartym dostępie", f"{liczba_oa / liczba * 100:.0f}%", border=True)

    trend["okres"] = np.where(trend["rok"] == ROK, f"{ROK} (rok niepełny)", "pełny rok")
    fig = px.bar(trend, x="rok", y="liczba", color="okres", title="Liczba publikacji w kolejnych latach",
                 color_discrete_map={"pełny rok": KOLORY[0], f"{ROK} (rok niepełny)": "#1F5F7F"})
    fig.update_layout(xaxis_title=None, yaxis_title="publikacje", legend_title=None)
    st.plotly_chart(wyglad(fig))

    try:
        with st.spinner("Analizuję czasopisma, instytucje i autorów…"):
            czasopisma = oa_grupy(filtr, "primary_location.source.id", 10, klucz)
            instytucje = oa_grupy(filtr, "authorships.institutions.id", 10, klucz)
            kraje = oa_grupy(filtr, "authorships.countries", 12, klucz)
            autorzy = oa_grupy(filtr, "authorships.author.id", 10, klucz)
    except oa.BladOpenAlex as blad:
        st.error(f"Nie udało się pobrać zestawień: {blad}")
    else:
        k1, k2 = st.columns(2)
        k1.plotly_chart(wykres_poziomy(czasopisma, "liczba", "nazwa", "Czasopisma publikujące najwięcej", KOLORY[0]))
        k2.plotly_chart(wykres_poziomy(instytucje, "liczba", "nazwa", "Najaktywniejsze instytucje", KOLORY[1]))
        k3, k4 = st.columns(2)
        k3.plotly_chart(wykres_poziomy(kraje, "liczba", "nazwa", "Kraje (afiliacje autorów)", KOLORY[2]))
        k4.plotly_chart(wykres_poziomy(autorzy, "liczba", "nazwa", "Najaktywniejsi autorzy", KOLORY[3]))

    st.markdown("#### 🏆 Najczęściej cytowane prace")
    st.caption("Kliknij wiersz, żeby zobaczyć abstrakt i pełną listę autorów.")
    tabela = cytowane[["rok", "cytowania", "tytuł", "czasopismo", "autorzy", "open_access", "doi", "pdf"]]
    wybor = st.dataframe(
        tabela,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "tytuł": st.column_config.TextColumn(width="large"),
            "czasopismo": st.column_config.TextColumn(width="medium"),
            "autorzy": st.column_config.TextColumn(width="medium"),
            "cytowania": st.column_config.ProgressColumn(format="%d", min_value=0, width="small",
                                                         max_value=int(cytowane["cytowania"].max() or 1)),
            "open_access": st.column_config.CheckboxColumn("OA"),
            "doi": st.column_config.LinkColumn("DOI", display_text="otwórz"),
            "pdf": st.column_config.LinkColumn("PDF", display_text="pobierz"),
            "rok": st.column_config.NumberColumn(format="%d"),
        },
    )
    zaznaczone = wybor.selection.rows if wybor and wybor.selection else []
    if zaznaczone:
        praca = cytowane.iloc[zaznaczone[0]]
        with st.container(border=True):
            st.markdown(f"**{praca['tytuł']}** ({praca['rok']}), *{praca['czasopismo']}*")
            st.caption(", ".join(praca["wszyscy_autorzy"]))
            st.write(praca["abstrakt"] or "_Abstrakt niedostępny w OpenAlex._")
            linki = [f"[DOI]({praca['doi']})" if praca["doi"] else "", f"[PDF]({praca['pdf']})" if praca["pdf"] else ""]
            st.markdown(" · ".join(l for l in linki if l))

    k1, k2 = st.columns([3, 2])
    with k1:
        st.markdown("#### 🆕 Najnowsze publikacje")
        for _, praca in najnowsze.iterrows():
            tytul = f"[{praca['tytuł']}]({praca['doi']})" if praca["doi"] else praca["tytuł"]
            znaczek = " · 🔓 open access" if praca["open_access"] else ""
            st.markdown(f"**{praca['data']}** · {tytul}  \n<small>{praca['autorzy']} · *{praca['czasopismo']}*{znaczek}</small>",
                        unsafe_allow_html=True)
    with k2:
        st.markdown("#### 🇵🇱 Kto w Polsce pracuje nad tematem")
        try:
            polskie, liczba_pl = oa_prace(oa.filtr(fraza, lata[0], lata[1], tylko_artykuly, kraj="PL"),
                                          "cited_by_count:desc", 50, klucz)
        except oa.BladOpenAlex as blad:
            st.error(str(blad))
        else:
            if liczba_pl == 0:
                st.info("Brak prac z polską afiliacją dla tego zapytania.")
            else:
                st.metric("Prace z co najmniej jednym autorem z Polski", liczba_pl)
                st.dataframe(oa.instytucje_z_kraju(polskie, "PL"), hide_index=True)
                with st.expander("Lista prac"):
                    for _, praca in polskie.iterrows():
                        st.markdown(f"- {praca['rok']} · [{praca['tytuł']}]({praca['doi']}) · {praca['cytowania']} cyt.")

    st.markdown("#### 📈 Porównanie tematów badawczych")
    if st.toggle("Pokaż porównanie (jedno zapytanie do API na temat)", value=True):
        tematy_tekst = st.text_area("Tematy (jeden w wierszu)", TEMATY_DOMYSLNE, height=130)
        tematy = [t.strip() for t in tematy_tekst.splitlines() if t.strip()][:6]
        normalizuj = st.checkbox("Pokaż udział w roku zamiast liczby publikacji")
        serie = []
        try:
            for temat in tematy:
                df = oa_trend(oa.filtr(temat, lata[0], lata[1], tylko_artykuly), klucz)
                serie.append(df.assign(temat=temat))
        except oa.BladOpenAlex as blad:
            st.error(str(blad))
        if serie:
            dane = pd.concat(serie)
            dane = dane[dane["rok"] < ROK]
            os_y = "liczba"
            if normalizuj:
                dane["udział [%]"] = dane["liczba"] / dane.groupby("rok")["liczba"].transform("sum") * 100
                os_y = "udział [%]"
            fig = px.line(dane, x="rok", y=os_y, color="temat", markers=True, color_discrete_sequence=KOLORY,
                          title="Publikacje w kolejnych latach (pełne lata)")
            fig.update_layout(xaxis_title=None, legend_title=None)
            st.plotly_chart(wyglad(fig, 420))


# ---------------------------------------------------------------------------------------------
# Analiza ogniw
# ---------------------------------------------------------------------------------------------

def wczytaj_ogniwa() -> dict[str, tuple[pd.DataFrame, float, pd.DataFrame]]:
    zrodla = ["Prawdziwe dane: NaMnHCF (KIT)", "Dane symulowane", "Moje pliki z cyklera"]
    zrodlo = st.segmented_control("Źródło danych", zrodla, default=zrodla[0], required=True)
    if zrodlo == zrodla[0]:
        try:
            with st.spinner("Pobieram dane z repozytorium Zenodo…"):
                ogniwa, meta = dane_rzeczywiste()
        except zenodo_data.BladZenodo as blad:
            st.error(f"Nie udało się pobrać danych: {blad}. Wybierz dane symulowane albo wgraj własne pliki.")
            return {}
        autorzy = meta["autorzy"][0] if meta["autorzy"] else ""
        st.info(
            f"**Dane rzeczywiste** z publikacji: *{meta['tytul']}* ({autorzy} i in., KIT, {meta['data'][:4]}). "
            f"Katoda NaMnHCF – analog błękitu pruskiego – w półogniwie z sodem oraz w ogniwach pełnych z twardym "
            f"węglem przy różnych elektrolitach i zakresach napięcia. Pobrane przez API Zenodo, "
            f"[DOI {meta['doi']}](https://doi.org/{meta['doi']}), licencja {meta['licencja'].upper()}. "
            "Co ok. 52 cykle wykonywano cykle kontrolne przy niższym prądzie (C/20) – widać je jako skoki pojemności."
        )
        return ogniwa

    if zrodlo == zrodla[1]:
        k1, k2 = st.columns([4, 1])
        k1.info("Dane symulowane: trzy ogniwa połówkowe z katodą typu PBA (model z dwoma plateau napięciowymi, "
                "rosnącą polaryzacją i spadkiem pojemności). Służą do pokazania analiz – wgraj własne pliki, "
                "żeby przeanalizować prawdziwe pomiary.")
        k2.download_button("⬇️ Przykładowy plik", przyklad_csv(), "przyklad_ec-lab.txt", mime="text/plain",
                           help="Fragment danych demonstracyjnych w formacie eksportu EC-Lab - wzór pliku do wgrania.")
        return analiza_demo()

    pliki = st.file_uploader("Pliki z cyklera: CSV / TXT / MPT / XLSX (jeden plik = jedno ogniwo)",
                             type=["csv", "txt", "mpt", "xlsx", "xls"], accept_multiple_files=True)
    if not pliki:
        st.info("Obsługiwane są typowe eksporty (EC-Lab, Arbin, Neware, Maccor): kolumny z numerem cyklu, "
                "napięciem, prądem i pojemnością są rozpoznawane automatycznie. Separator i przecinek dziesiętny też.")
        return {}

    try:
        pierwszy = wczytaj(pliki[0].getvalue(), pliki[0].name)
    except Exception as blad:
        st.error(f"Nie udało się odczytać pliku {pliki[0].name}: {blad}")
        return {}

    kolumny = list(pierwszy.columns)
    zgadniete = cycling.zgadnij_kolumny(kolumny)
    brakuje = [r for r in cycling.WYMAGANE if not zgadniete.get(r)]
    with st.expander("⚙️ Mapowanie kolumn (wykryte automatycznie)", expanded=bool(brakuje)):
        opcje = ["—"] + kolumny
        mapowanie = {}
        kolumny_ui = st.columns(3)
        for i, (rola, opis) in enumerate(cycling.ROLE.items()):
            domyslna = zgadniete.get(rola)
            wybor = kolumny_ui[i % 3].selectbox(opis, opcje, index=opcje.index(domyslna) if domyslna else 0,
                                                key=f"map_{rola}")
            mapowanie[rola] = None if wybor == "—" else wybor
        jednostka = kolumny_ui[2].selectbox("Jednostka pojemności", ["auto", "mAh", "Ah"])
        st.dataframe(pierwszy.head(8), hide_index=True)

    masy = st.data_editor(
        pd.DataFrame({"plik": [p.name for p in pliki], "masa materiału aktywnego [mg]": [0.0] * len(pliki)}),
        disabled=["plik"], hide_index=True,
        column_config={"masa materiału aktywnego [mg]": st.column_config.NumberColumn(min_value=0.0, step=0.1,
                                                                                       format="%.2f")},
    )
    st.caption("Podaj masę materiału aktywnego, żeby przeliczyć pojemność na mAh/g.")

    ogniwa = {}
    for plik, masa in zip(pliki, masy["masa materiału aktywnego [mg]"]):
        try:
            std, tabela = analiza_pliku(plik.getvalue(), plik.name, tuple(sorted(mapowanie.items(), key=str)),
                                        jednostka, float(masa or 0))
        except Exception as blad:
            st.error(f"{plik.name}: {blad}")
            continue
        if tabela.empty:
            st.warning(f"{plik.name}: nie znaleziono pełnych cykli z pojemnością rozładowania.")
            continue
        ogniwa[plik.name.rsplit(".", 1)[0]] = (std, float(masa or 0), tabela)
    return ogniwa


def sekcja_przeglad(ogniwa: dict, cykl_ref: int, prog: int) -> None:
    jednostka = "mAh/g" if all(m > 0 for _, m, _ in ogniwa.values()) else "mAh"
    wiersze = []
    for nazwa, (_, _, tabela) in ogniwa.items():
        if tabela["cykl"].max() < cykl_ref:
            continue
        wiersze.append({"ogniwo": nazwa, **cycling.wskazniki(tabela, cykl_ref, prog)})
    if not wiersze:
        st.warning("Żadne ogniwo nie ma tylu cykli, ile wynosi cykl odniesienia.")
        return

    kpi = pd.DataFrame(wiersze).dropna(axis=1, how="all")
    st.dataframe(
        kpi, hide_index=True,
        column_config={
            "Pojemność początkowa": st.column_config.NumberColumn(f"Q pocz. [{jednostka}]", format="%.1f"),
            "Pojemność końcowa": st.column_config.NumberColumn(f"Q końc. [{jednostka}]", format="%.1f"),
            "Retencja [%]": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
            "Pierwsza CE [%]": st.column_config.NumberColumn(format="%.1f"),
            "Średnia CE [%]": st.column_config.NumberColumn(format="%.2f"),
            "Śr. napięcie rozł. [V]": st.column_config.NumberColumn(format="%.3f"),
            "Wydajność energetyczna [%]": st.column_config.NumberColumn(format="%.1f"),
        },
    )

    k1, k2 = st.columns(2)
    fig_q, fig_ce = go.Figure(), go.Figure()
    for i, (nazwa, (_, _, tabela)) in enumerate(ogniwa.items()):
        kol = cycling.kolumna_pojemnosci(tabela)
        kolor = KOLORY[i % len(KOLORY)]
        fig_q.add_scatter(x=tabela["cykl"], y=tabela[kol], mode="markers", marker=dict(size=4, color=kolor), name=nazwa)
        fig_ce.add_scatter(x=tabela["cykl"], y=tabela["CE [%]"], mode="lines", line=dict(width=1.5, color=kolor),
                           name=nazwa)
    fig_q.update_layout(title="Pojemność rozładowania", xaxis_title="cykl", yaxis_title=f"Q [{jednostka}]")
    fig_ce.update_layout(title="Wydajność kulombowska", xaxis_title="cykl", yaxis_title="CE [%]")
    ma_ce = any(t["CE [%]"].notna().any() for _, _, t in ogniwa.values())
    ce_stabilne = pd.concat([t.loc[t["cykl"] >= 3, "CE [%]"] for _, _, t in ogniwa.values()]).dropna()
    if len(ce_stabilne):
        fig_ce.update_yaxes(range=[max(80.0, ce_stabilne.quantile(0.01) - 0.3), 100.2])
    fig_ce.add_annotation(text="1. cykl poza skalą – patrz „Pierwsza CE” w tabeli", xref="paper", yref="paper",
                          x=0, y=0.02, showarrow=False, font=dict(size=11, color="#888"), xanchor="left")
    legenda_nisko = dict(legend=dict(orientation="h", yanchor="top", y=-0.42, x=0, title=None))
    if ma_ce:
        k1.plotly_chart(wyglad(fig_q, 440).update_layout(**legenda_nisko))
        k2.plotly_chart(wyglad(fig_ce, 440).update_layout(**legenda_nisko))
    else:
        st.plotly_chart(wyglad(fig_q, 480).update_layout(**legenda_nisko))


def sekcja_model(ogniwa: dict, cykl_ref: int, prog: int, frakcja: int) -> None:
    st.markdown("### 📉 Model degradacji i prognoza końca życia")
    st.caption("Dopasowanie kilku modeli spadku pojemności, wybór najlepszego kryterium AIC i prognoza cyklu, "
               "w którym pojemność spadnie poniżej progu. Przedział 95% wyznaczony bootstrapem reszt.")
    nazwa = st.selectbox("Ogniwo", list(ogniwa), key="model_ogniwo")
    tabela = ogniwa[nazwa][2]
    kol = cycling.kolumna_pojemnosci(tabela)
    dane = tabela[tabela["cykl"] >= cykl_ref].dropna(subset=[kol])
    odstajace = cycling.cykle_odstajace(dane[kol].to_numpy(float))
    pomin = False
    if odstajace.any():
        pomin = st.checkbox(
            f"Pomiń w modelu {int(odstajace.sum())} odstających cykli (np. cykle kontrolne przy innym prądzie)",
            value=True, help="Cykle, których pojemność odbiega o ponad 3% od mediany sąsiednich cykli.")
    wykluczone = dane[odstajace] if pomin else dane.iloc[0:0]
    if pomin:
        dane = dane[~odstajace]
    if len(dane) < 10:
        st.warning("Do modelowania potrzeba co najmniej 10 cykli od cyklu odniesienia.")
        return

    start = int(dane["cykl"].iloc[0])
    x = (dane["cykl"] - start).to_numpy(float)
    y = dane[kol].to_numpy(float)
    q_ref = float(y[0])
    prog_q = prog / 100 * q_ref

    porownanie = cycling.porownaj_modele(x, y)
    if porownanie.empty:
        st.error("Nie udało się dopasować żadnego modelu.")
        return

    k1, k2 = st.columns([1, 2])
    horyzont = k1.number_input("Horyzont prognozy [cykle]", min_value=int(x[-1]) + 10,
                               value=int(max(2 * x[-1], x[-1] + 200)), step=100)
    nazwa_modelu = k1.radio(
        "Model", porownanie["model"].tolist(),
        format_func=lambda m: f"{m}  ⭐ najlepszy (AIC)" if m == porownanie["model"].iloc[0] else m,
    )
    model = cycling.model_po_nazwie(nazwa_modelu)
    with st.spinner("Liczę przedziały predykcji…"):
        wynik = bootstrap(nazwa_modelu, x, y, prog_q, float(horyzont))

    eol = wynik["eol"]
    przedzial = wynik["eol_przedzial"]
    with k1:
        if eol is None:
            st.metric(f"Spadek poniżej {prog}%", f"> {horyzont + start} cykli", border=True)
        else:
            st.metric(f"Przewidywany cykl spadku poniżej {prog}%", f"{eol + start:.0f}", border=True)
            if przedzial:
                st.caption(f"Przedział 95%: {przedzial[0] + start:.0f}–{przedzial[1] + start:.0f} cykli")
        wiersz = porownanie[porownanie["model"] == nazwa_modelu].iloc[0]
        st.caption(f"Model: {model.wzor} · R² = {wiersz['R²']:.4f} · RMSE = {wiersz['RMSE']:.2f}")

    fig = go.Figure()
    siatka = wynik["siatka"] + start
    fig.add_scatter(x=np.r_[siatka, siatka[::-1]],
                    y=np.maximum(np.r_[wynik["gorna"], wynik["dolna"][::-1]], 0), fill="toself",
                    fillcolor="rgba(63,167,214,0.22)", line=dict(width=0), name="przedział 95%", hoverinfo="skip")
    fig.add_scatter(x=dane["cykl"], y=y, mode="markers", marker=dict(size=4, color="#D0D0D0"), name="pomiar")
    if len(wykluczone):
        fig.add_scatter(x=wykluczone["cykl"], y=wykluczone[kol], mode="markers", name="pominięte",
                        marker=dict(size=7, color="rgba(0,0,0,0)", line=dict(color=KOLORY[1], width=1.5)))
    fig.add_scatter(x=siatka, y=np.maximum(wynik["krzywa"], 0), mode="lines", line=dict(color=KOLORY[0], width=2.5),
                    name=f"model {nazwa_modelu}")
    fig.add_hline(y=prog_q, line_dash="dash", line_color=KOLORY[1], annotation_text=f"{prog}% pojemności")
    if eol is not None:
        fig.add_vline(x=eol + start, line_dash="dot", line_color=KOLORY[1])
    fig.update_layout(title=f"{nazwa}: prognoza pojemności", xaxis_title="cykl", yaxis_title=kol)
    fig.update_yaxes(range=[0, float(max(y.max(), wykluczone[kol].max() if len(wykluczone) else 0)) * 1.08])
    k2.plotly_chart(wyglad(fig, 430))

    tabela_modeli = porownanie.drop(columns=["parametry"]).copy()
    przekroczenia = []
    for nazwa_m, parametry in zip(porownanie["model"], porownanie["parametry"]):
        cykl = cycling.cykl_przekroczenia(cycling.model_po_nazwie(nazwa_m), parametry, prog_q, float(horyzont))
        przekroczenia.append(None if cykl is None else round(cykl + start))
    tabela_modeli[f"cykl < {prog}%"] = przekroczenia
    st.dataframe(tabela_modeli, hide_index=True,
                 column_config={"RMSE": st.column_config.NumberColumn(format="%.3f"),
                                "R²": st.column_config.NumberColumn(format="%.4f"),
                                "AIC": st.column_config.NumberColumn(format="%.1f")})

    test = cycling.test_wsteczny(model, x, y, frakcja / 100)
    if test:
        fig = go.Figure()
        fig.add_scatter(x=dane["cykl"], y=y, mode="markers", marker=dict(size=4, color="#999"), name="pomiar")
        fig.add_scatter(x=test["x_test"] + start, y=test["prognoza"], mode="lines",
                        line=dict(color=KOLORY[2], width=2.5), name="prognoza z wcześniejszych cykli")
        fig.add_vrect(x0=start, x1=start + x[test["granica"] - 1], fillcolor="rgba(118,176,65,0.16)", line_width=0,
                      annotation_text="dane do nauki", annotation_position="top left")
        fig.update_layout(title=f"Test wsteczny: model uczony na pierwszych {frakcja}% cykli · "
                                f"średni błąd prognozy (MAPE) = {test['MAPE [%]']:.2f}%",
                          xaxis_title="cykl", yaxis_title=kol)
        st.plotly_chart(wyglad(fig, 360))


def sekcja_krzywe(ogniwa: dict) -> None:
    st.markdown("### ⚡ Krzywe napięciowe i analiza dQ/dV")
    z_napieciem = {n: v for n, v in ogniwa.items()
                   if v[0] is not None and v[0]["voltage"].notna().any() and v[0].groupby("cycle").size().max() > 5}
    if not z_napieciem:
        st.info("Krzywe napięciowe wymagają surowych danych z napięciem (wiele punktów na cykl).")
        return

    k1, k2, k3 = st.columns([2, 3, 1])
    nazwa = k1.selectbox("Ogniwo", list(z_napieciem), key="krzywe_ogniwo")
    std, masa, tabela = z_napieciem[nazwa]
    dostepne = sorted(std.loc[std["voltage"].notna(), "cycle"].unique().tolist())
    if len(dostepne) <= 8:
        domyslne = dostepne
    else:
        domyslne = [c for c in (1, 10, 50, 100, 150, 200, dostepne[-1]) if c in dostepne]
    cykle = k2.multiselect("Cykle", dostepne, default=sorted(set(domyslne)), key=f"cykle_{nazwa}")
    etap = k3.radio("Etap dQ/dV", ["rozładowanie", "ładowanie"])
    if not cykle:
        return

    przelicznik = 1000 / masa if masa > 0 else 1.0
    jednostka = "mAh/g" if masa > 0 else "mAh"
    kolory = px.colors.sample_colorscale("Plasma", [0.35 + 0.6 * i / max(len(cykle) - 1, 1) for i in range(len(cykle))])

    fig_v, fig_d = go.Figure(), go.Figure()
    piki = []
    for kolor, nr in zip(kolory, sorted(cykle)):
        cykl = std[std["cycle"] == nr]
        for rodzaj, linia in (("charge", "solid"), ("discharge", "dash")):
            q, v = cycling.segment(cykl, rodzaj)
            if len(q):
                fig_v.add_scatter(x=q * przelicznik, y=v, mode="lines", line=dict(color=kolor, dash=linia, width=2),
                                  name=f"cykl {nr}", legendgroup=str(nr), showlegend=rodzaj == "charge")
        q, v = cycling.segment(cykl, "discharge" if etap == "rozładowanie" else "charge")
        siatka, dqdv = cycling.krzywa_dqdv(q * przelicznik, v)
        if len(siatka):
            fig_d.add_scatter(x=siatka, y=dqdv, mode="lines", line=dict(color=kolor, width=2), name=f"cykl {nr}")
            piki.append({"cykl": nr, **{f"pik {i + 1} [V]": round(p, 3)
                                        for i, p in enumerate(cycling.piki_dqdv(siatka, dqdv))}})

    fig_v.update_layout(title="Krzywe ładowania (linia ciągła) i rozładowania (przerywana)",
                        xaxis_title=f"pojemność [{jednostka}]", yaxis_title="napięcie [V]")
    fig_d.update_layout(title=f"dQ/dV – {etap}", xaxis_title="napięcie [V]", yaxis_title=f"dQ/dV [{jednostka}·V⁻¹]")
    k1, k2 = st.columns(2)
    k1.plotly_chart(wyglad(fig_v, 430))
    k2.plotly_chart(wyglad(fig_d, 430))

    k1, k2 = st.columns([2, 3])
    with k1:
        st.markdown("**Położenie pików dQ/dV**")
        st.caption("Przesuwanie się pików między cyklami świadczy o rosnącej polaryzacji, a ich zanik i poszerzenie "
                   "o degradacji struktury materiału.")
        st.dataframe(pd.DataFrame(piki), hide_index=True)
    with k2:
        trajektoria = []
        krok = max(1, len(dostepne) // 50)
        for nr in dostepne[::krok]:
            q, v = cycling.segment(std[std["cycle"] == nr], "discharge" if etap == "rozładowanie" else "charge")
            siatka, dqdv = cycling.krzywa_dqdv(q * przelicznik, v)
            for i, p in enumerate(sorted(cycling.piki_dqdv(siatka, dqdv))):
                trajektoria.append({"cykl": nr, "napięcie piku [V]": p, "pik": f"pik {i + 1}"})
        if trajektoria:
            fig = px.scatter(pd.DataFrame(trajektoria), x="cykl", y="napięcie piku [V]", color="pik",
                             color_discrete_sequence=KOLORY, title="Wędrówka pików dQ/dV w kolejnych cyklach")
            st.plotly_chart(wyglad(fig, 330))


def zakladka_ogniwa() -> None:
    st.subheader("🔋 Analiza testów cyklowania")
    ogniwa = wczytaj_ogniwa()
    if not ogniwa:
        return

    k1, k2, k3 = st.columns(3)
    cykl_ref = k1.number_input("Cykl odniesienia (100%)", min_value=1, value=2,
                               help="Pierwszy cykl ma zwykle nieodwracalną stratę pojemności (formowanie warstwy CEI), "
                                    "dlatego retencję liczy się najczęściej od 2. cyklu.")
    prog = k2.slider("Próg końca życia [% pojemności]", 50, 95, 80)
    frakcja = k3.slider("Cykle do nauki modelu w teście wstecznym [%]", 20, 90, 40)

    sekcja_przeglad(ogniwa, int(cykl_ref), prog)
    sekcja_model(ogniwa, int(cykl_ref), prog, frakcja)
    sekcja_krzywe(ogniwa)

    wszystkie = pd.concat([t.assign(ogniwo=n) for n, (_, _, t) in ogniwa.items()], ignore_index=True)
    st.download_button("⬇️ Pobierz podsumowanie cykli (CSV)", wszystkie.to_csv(index=False).encode("utf-8-sig"),
                       "podsumowanie_cykli.csv", mime="text/csv")


# ---------------------------------------------------------------------------------------------
# Kalkulator syntezy
# ---------------------------------------------------------------------------------------------

def zakladka_synteza() -> None:
    st.subheader("⚗️ Kalkulator syntezy HE-PBA metodą współstrącania")
    st.caption("Naważki odczynników dla NaₓM[Fe(CN)₆]·yH₂O, gdzie M to mieszanina metali. "
               "Roztwór A: sole metali (+ cytrynian sodu jako czynnik chelatujący spowalniający krystalizację), "
               "roztwór B: heksacyjanożelazian.")

    lewa, prawa = st.columns([1.3, 1])
    with lewa:
        metale = st.multiselect("Metale w podsieci M", synthesis.METALE, default=["Mn", "Fe", "Ni", "Cu", "Zn"])
        if not metale:
            st.info("Wybierz co najmniej jeden metal.")
            return
        wszystkie_sole = [s for m in synthesis.METALE for s in synthesis.SOLE[m]]
        tabela = st.data_editor(
            pd.DataFrame({"metal": metale, "udział": [round(1 / len(metale), 4)] * len(metale),
                          "sól": [synthesis.SOLE[m][0] for m in metale], "własny wzór": [""] * len(metale),
                          "redoks": [m in synthesis.AKTYWNE_REDOKS for m in metale]}),
            key=f"sklad_{'-'.join(metale)}", hide_index=True, disabled=["metal"],
            column_config={
                "udział": st.column_config.NumberColumn("udział molowy", min_value=0.0, max_value=1.0, step=0.01,
                                                        format="%.3f"),
                "sól": st.column_config.SelectboxColumn("prekursor", options=wszystkie_sole, required=True),
                "własny wzór": st.column_config.TextColumn(
                    "własny prekursor", help="Opcjonalnie: wzór innej soli, np. z inną liczbą cząsteczek wody, "
                                             "np. NH4NbO(C2O4)2·3H2O. Zastępuje prekursor z listy."),
                "redoks": st.column_config.CheckboxColumn(
                    "redoks", help="Czy metal w podsieci M bierze udział w reakcji redoks "
                                           "(wpływa na pojemność teoretyczną)."),
            },
        )
        k1, k2, k3 = st.columns(3)
        n_metali = k1.number_input("Ilość metali M [mmol]", min_value=0.1, value=5.0, step=0.5)
        stosunek_fecn = k2.number_input("Fe(CN)₆ : M", min_value=0.1, value=1.0, step=0.1)
        stosunek_cytr = k3.number_input("cytrynian : M", min_value=0.0, value=1.0, step=0.5)
        k1, k2, k3 = st.columns(3)
        heks = k1.selectbox("Heksacyjanożelazian", list(synthesis.HEKSACYJANOZELAZIANY))
        v_a = k2.number_input("Objętość roztworu A [mL]", min_value=1.0, value=100.0, step=10.0)
        v_b = k3.number_input("Objętość roztworu B [mL]", min_value=1.0, value=100.0, step=10.0)
        k1, k2 = st.columns(2)
        sod = k1.number_input("Zakładana zawartość Na (x)", min_value=0.0, max_value=2.0, value=1.5, step=0.1)
        woda = k2.number_input("Woda krystalizacyjna (y)", min_value=0.0, max_value=6.0, value=2.0, step=0.5)

    udzialy, sole, aktywne, niepasujace = {}, {}, set(), []
    for _, r in tabela.iterrows():
        metal = r["metal"]
        udzialy[metal] = float(r["udział"] or 0)
        wlasny = str(r["własny wzór"] or "").strip()
        wybrany = wlasny or str(r["sól"] or "")
        if synthesis.atomy_metalu(wybrany, metal) > 0:
            sole[metal] = wybrany
        else:
            niepasujace.append(f"{metal} ({wybrany or 'brak'})")
            sole[metal] = synthesis.SOLE[metal][0]
        if bool(r["redoks"]):
            aktywne.add(metal)
    if niepasujace:
        st.warning("Prekursor jest niepoprawny albo nie zawiera wybranego metalu: "
                   f"{', '.join(niepasujace)}. Użyto domyślnej soli.")
    suma = sum(udzialy.values())
    if suma <= 0:
        st.error("Suma udziałów musi być większa od zera.")
        return
    if abs(suma - 1) > 0.005:
        st.info(f"Suma udziałów wynosi {suma:.3f} – udziały zostały znormalizowane do 1.")

    wzor_heks = synthesis.HEKSACYJANOZELAZIANY[heks]
    kation = "K" if wzor_heks.startswith("K") else "Na"
    odczynniki, stezenia = synthesis.plan_syntezy(udzialy, sole, n_metali, wzor_heks, stosunek_fecn,
                                                  stosunek_cytr, v_a, v_b)
    wzor = synthesis.wzor_produktu(udzialy, sod, woda, kation)
    m_produktu = synthesis.masa_molowa(wzor)
    s_conf = synthesis.entropia_konfiguracyjna(udzialy)
    elektrony = synthesis.liczba_elektronow(udzialy, aktywne, sod)
    q_teor = synthesis.pojemnosc_teoretyczna(m_produktu, elektrony)

    with prawa:
        st.markdown(f"**Produkt:** {synthesis.ladny_wzor(wzor)}")
        r1 = st.columns(2)
        r1[0].metric("S konfiguracyjna", f"{s_conf / synthesis.R:.2f} R", border=True,
                     help=f"S = −R·Σ xᵢ·ln xᵢ = {s_conf:.2f} J/(mol·K)")
        r1[1].metric("Masa molowa [g/mol]", f"{m_produktu:.1f}", border=True)
        r2 = st.columns(2)
        r2[0].metric("Pojemność teoretyczna", f"{q_teor:.0f} mAh/g", border=True)
        r2[1].metric("Wydajność teoretyczna", f"{n_metali * m_produktu / 1000:.3f} g", border=True)
        st.caption(f"Materiał {synthesis.klasa_entropii(s_conf)}. Pojemność teoretyczna dla {elektrony:.2f} e⁻ "
                   "na jednostkę wzoru: redoks Fe w Fe(CN)₆ oraz metali oznaczonych w tabeli jako aktywne, "
                   "ograniczony zawartością sodu x.")
        fig = px.bar(x=list(udzialy), y=[v / suma for v in udzialy.values()], text_auto=".2f",
                     color=list(udzialy), color_discrete_sequence=KOLORY, title="Skład podsieci M")
        fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="udział molowy")
        st.plotly_chart(wyglad(fig, 280))

    st.markdown("#### 🧾 Naważki")
    nawazki = pd.DataFrame([{
        "roztwór": o.roztwor, "odczynnik": o.nazwa, "wzór": synthesis.ladny_wzor(o.wzor), "M [g/mol]": o.masa_molowa,
        "n [mmol]": o.mmol, "masa [g]": o.masa_g,
    } for o in odczynniki])
    st.dataframe(nawazki, hide_index=True,
                 column_config={"M [g/mol]": st.column_config.NumberColumn(format="%.2f"),
                                "n [mmol]": st.column_config.NumberColumn(format="%.3f"),
                                "masa [g]": st.column_config.NumberColumn(format="%.4f")})
    k1, k2, k3 = st.columns([1, 1, 2])
    k1.metric("Stężenie metali w A", f"{stezenia['A [M] (metale)']:.3f} M")
    k2.metric("Stężenie Fe(CN)₆ w B", f"{stezenia['B [M] (Fe(CN)6)']:.3f} M")

    docx = karta_docx.karta_syntezy(
        wzor=wzor, udzialy=udzialy, sole=sole, aktywne=aktywne, n_metali_mmol=n_metali,
        stosunek_fecn=stosunek_fecn, stosunek_cytrynianu=stosunek_cytr, heksacyjanian=wzor_heks,
        v_a_ml=v_a, v_b_ml=v_b, sod=sod, woda=woda, m_produktu=m_produktu, s_conf=s_conf,
        elektrony=elektrony, q_teor=q_teor, odczynniki=odczynniki, stezenia=stezenia,
    )
    nazwa = "karta_syntezy_" + "".join(m for m, x in udzialy.items() if x > 0) + f"_{date.today():%Y%m%d}"
    with k3:
        st.download_button("⬇️ Pobierz kartę syntezy (Word)", docx, f"{nazwa}.docx", type="primary",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# ---------------------------------------------------------------------------------------------

def main() -> None:
    with st.sidebar:
        st.markdown("## 🔋 Battery Lab")
        st.caption("Asystent badań nad katodami do ogniw sodowo-jonowych")
        klucz_serwera = klucz_z_konfiguracji()
        wpisany = st.text_input(
            "Klucz API OpenAlex (opcjonalnie)", type="password",
            placeholder="klucz aplikacji jest już ustawiony" if klucz_serwera else "",
            help="Bez klucza wszystkie osoby z tej samej sieci dzielą mały darmowy limit dzienny. "
                 "Darmowy klucz: openalex.org/settings/api",
        )
        klucz = wpisany.strip() or klucz_serwera
        if sekret("APP_PASSWORD") and st.button("Wyloguj", width="stretch"):
            st.session_state.pop("zalogowany", None)
            st.rerun()
        st.divider()
        st.markdown(
            "**Co tu jest**\n"
            "- 📚 trendy i kluczowe prace z bazy OpenAlex (na żywo)\n"
            "- 🔋 analiza danych z cyklera: retencja, CE, dQ/dV, prognoza żywotności\n"
            "- ⚗️ nawazki do syntezy HE-PBA i entropia konfiguracyjna"
        )

    st.title("🔋 Battery Lab")
    st.markdown("Literatura, dane z cyklera i synteza materiałów katodowych **w jednym miejscu**.")
    zakladki = st.tabs(["📚 Radar literatury", "🔋 Analiza ogniw", "⚗️ Kalkulator syntezy"])
    with zakladki[0]:
        zakladka_literatura(klucz.strip())
    with zakladki[2]:
        zakladka_synteza()
    with zakladki[1]:
        zakladka_ogniwa()


if dostep_przyznany():
    main()
