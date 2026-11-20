# 🔋 Battery Lab

Aplikacja Streamlit wspierająca badania nad katodami do ogniw sodowo-jonowych (Na-ion),
w szczególności nad wysokoentropowymi analogami błękitu pruskiego (HE-PBA).

## Uruchomienie

```
pip install -r requirements.txt
streamlit run app.py
```

## Zakładki

### 📚 Radar literatury
Dane na żywo z otwartej bazy publikacji [OpenAlex](https://openalex.org) (ponad 250 mln prac, bez logowania):
- liczba publikacji w kolejnych latach i dynamika tematu,
- najczęściej cytowane prace z abstraktami oraz linkami do DOI i darmowych PDF-ów,
- czasopisma, instytucje, kraje i autorzy najaktywniejsi w temacie,
- prace z udziałem polskich instytucji,
- porównanie popularności kilku tematów badawczych.

Bez klucza API wszyscy użytkownicy z jednej sieci dzielą mały dzienny limit OpenAlex.
Darmowy klucz (openalex.org/settings/api) można wpisać w panelu bocznym albo zapisać w pliku
`.streamlit/secrets.toml` jako `OPENALEX_API_KEY = "..."`. Wyniki są zapamiętywane na 24 godziny.

### 🔋 Analiza ogniw
Wgrywasz pliki z cyklera (CSV, TXT, MPT, XLSX; jeden plik = jedno ogniwo). Kolumny z eksportów EC-Lab, Arbin,
Neware i Maccor są rozpoznawane automatycznie, separator i przecinek dziesiętny również. Po podaniu masy
materiału aktywnego pojemność jest przeliczana na mAh/g.

- pojemność rozładowania, retencja, wydajność kulombowska i energetyczna, średnie napięcie rozładowania,
- modele spadku pojemności (liniowy, pierwiastkowy, potęgowy, wykładniczy) porównywane kryterium AIC,
- prognoza cyklu, w którym pojemność spadnie poniżej progu (np. 80%), z przedziałem 95% z bootstrapu reszt,
- test wsteczny: model uczony na pierwszych cyklach i porównany z dalszymi pomiarami,
- krzywe ładowania/rozładowania, analiza dQ/dV i wędrówka pików w kolejnych cyklach,
- eksport podsumowania cykli do CSV.

Wbudowane źródła danych:
- **dane rzeczywiste** pobierane przez API Zenodo: katoda NaMnHCF (analog błękitu pruskiego) w półogniwie
  i w pięciu ogniwach pełnych z twardym węglem (różne elektrolity i zakresy napięcia), wraz z krzywymi
  napięciowymi; S. Büchele i in., KIT, [DOI 10.5281/zenodo.14359482](https://doi.org/10.5281/zenodo.14359482),
  licencja CC BY 4.0,
- symulowane dane demonstracyjne trzech ogniw oraz przykładowy plik w formacie EC-Lab.

Cykle odbiegające od sąsiednich (np. cykle kontrolne przy innym prądzie) są wykrywane automatycznie
i mogą zostać pominięte przy dopasowaniu modelu.

### ⚗️ Kalkulator syntezy
Synteza HE-PBA metodą współstrącania: naważki soli metali, heksacyjanożelazianu i cytrynianu sodu, stężenia
roztworów, entropia konfiguracyjna podsieci metali, masa molowa produktu, wydajność i pojemność teoretyczna.
Kartę syntezy można pobrać jako plik tekstowy.

## Struktura

| Plik | Zawartość |
|---|---|
| `app.py` | interfejs Streamlit |
| `openalex_client.py` | klient API OpenAlex |
| `cycling.py` | wczytywanie danych z cyklera, podsumowanie cykli, modele degradacji, dQ/dV |
| `synthesis.py` | parser wzorów chemicznych, masy molowe, obliczenia do syntezy |
| `zenodo_data.py` | pobieranie i parsowanie danych rzeczywistych z API Zenodo |
| `demo_data.py` | generator danych demonstracyjnych |
