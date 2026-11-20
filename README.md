# 🔋 Battery Lab

[![Otwórz w Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://battery-lab.streamlit.app/)

**Aplikacja online: https://battery-lab.streamlit.app/**

Aplikacja w Streamlit do pracy z materiałami katodowymi do ogniw sodowo-jonowych, ze szczególnym naciskiem
na analogi błękitu pruskiego (PBA) i ich wysokoentropowe odmiany (HE-PBA). Ma trzy moduły: przegląd literatury,
analizę danych z testów cyklowania i kalkulator syntezy. Działa na danych rzeczywistych: otwartym zbiorze
pomiarów ogniw z Zenodo, bazie publikacji OpenAlex i plikach z cyklera wgrywanych przez użytkownika.

---

## Moduły

| Zakładka | Co robi |
|---|---|
| 📚 Radar literatury | trend publikacji, najczęściej cytowane i najnowsze prace, czasopisma, instytucje, kraje, autorzy, prace z Polski, porównanie kilku tematów |
| 🔋 Analiza ogniw | wskaźniki cykli, modele degradacji pojemności, prognoza końca życia z niepewnością, test wsteczny, krzywe napięciowe i dQ/dV |
| ⚗️ Kalkulator syntezy | naważki do współstrącania HE-PBA, stężenia roztworów, entropia konfiguracyjna, masa molowa, wydajność i pojemność teoretyczna |

---

## Dane

| Źródło | Zawartość | Dostęp | Licencja |
|---|---|---|---|
| [Zenodo, DOI 10.5281/zenodo.14359482](https://doi.org/10.5281/zenodo.14359482) | cyklowanie katody NaMnHCF w półogniwie z sodem i w ogniwach pełnych z twardym węglem (różne elektrolity i zakresy napięcia), krzywe napięciowe półogniwa | REST API Zenodo, cache 7 dni | CC BY 4.0 |
| [OpenAlex](https://openalex.org) | metadane publikacji: tytuły, abstrakty, cytowania, afiliacje | REST API OpenAlex, cache 24 h | CC0 |
| pliki użytkownika | eksporty z cyklera (CSV, TXT, MPT, XLSX) | upload w aplikacji, tylko w pamięci, nic nie jest zapisywane | – |

Aplikacja ma też generator danych symulowanych, wyraźnie oznaczony w interfejsie, do testowania funkcji bez
własnych plików.

Zbiór z Zenodo: S. Büchele, V. Mereacre, N. Bohn, P. Stüble, X. Wu, N. Keim, R. Xu, H. Geßwein, W. Sun,
G. Vrhovac, M. Pordzik, T. Bergfeldt, S. Indris, W. Bauer, H. Ehrenberg, J. R. Binder, *Sodium Manganese
Hexacyanoferrate: Characterization as Sodium-Ion Cathode Material, Full Cell Cycling with Hard Carbon and
Post-Mortem Analyses*, Zenodo (2024), https://doi.org/10.5281/zenodo.14359482.

---

## Metodologia

### Wczytywanie danych z cyklera

- **Format pliku:** kodowanie sprawdzane po kolei (UTF-8 → CP1250 → Latin-1). Nagłówek plików EC-Lab ASCII
  jest pomijany na podstawie pola `Nb header lines`. Separator (tabulator, `;`, `,`) i przecinek dziesiętny
  są wykrywane automatycznie.
- **Mapowanie kolumn:** nazwy kolumn są normalizowane i porównywane z wzorcami z eksportów EC-Lab, Arbin,
  Neware i Maccor. Pełne dopasowanie liczy się bardziej niż dopasowanie początku nazwy, a to bardziej niż
  fragment. Wynik można poprawić ręcznie w interfejsie.
- **Jednostki:** pojemność w Ah jest przeliczana na mAh na podstawie nazwy kolumny. Pojemność właściwa
  [mAh/g] liczona jest z masy materiału aktywnego podanej przez użytkownika.

### Wskaźniki cyklu

Dla danych surowych każdy cykl dzielony jest na ładowanie i rozładowanie według znaku prądu, a bez kolumny
prądu według przyrostu pojemności.

| Wielkość | Definicja |
|---|---|
| pojemność ładowania / rozładowania | maksimum pojemności w danym etapie |
| energia | E = ∫ V dQ, całkowanie metodą trapezów |
| wydajność kulombowska (CE) | Q_rozł / Q_ład |
| wydajność energetyczna | E_rozł / E_ład |
| średnie napięcie rozładowania | E_rozł / Q_rozł |
| retencja | Q(n) / Q(n_ref), gdzie n_ref to cykl odniesienia wybrany przez użytkownika |

### Cykle odstające

Cykl jest odstający, jeśli jego pojemność różni się o więcej niż 3% od mediany kroczącej z 9 sąsiednich cykli.
W ten sposób wychwytywane są np. cykle kontrolne przy niższym prądzie. Domyślnie są pomijane przy
dopasowaniu modelu, a na wykresie widać je jako puste znaczniki.

### Modele degradacji

Numer cyklu liczony jest od cyklu odniesienia (n = cykl − n_ref). Dopasowywane są cztery modele:

| Model | Wzór | Parametry | Interpretacja |
|---|---|---|---|
| liniowy | Q₀ − k·n | Q₀, k | stała szybkość spadku |
| pierwiastkowy | Q₀ − k·√n | Q₀, k | spadek kontrolowany dyfuzyjnie, typowy dla narastania warstwy SEI/CEI |
| potęgowy | Q₀ − k·nᶻ | Q₀, k, z ∈ [0,05; 3] | uogólnienie dwóch powyższych: z < 1 to spadek zwalniający, z > 1 to przyspieszający |
| wykładniczy | Q₀·e^(−k·n) | Q₀, k | spadek proporcjonalny do bieżącej pojemności |

- **Dopasowanie:** nieliniowa metoda najmniejszych kwadratów z ograniczeniami na parametry
  (`scipy.optimize.curve_fit`). Wartości startowe liczone są z mediany pierwszych i ostatnich 5% punktów.
- **Wybór modelu:** kryterium Akaike, AIC = n·ln(SSE/n) + 2k, które karze model potęgowy za dodatkowy
  parametr. Dla porównania pokazywane są też RMSE i R².

### Prognoza końca życia i niepewność

- **Koniec życia (EOL):** pierwszy cykl, w którym krzywa modelu spada poniżej progu, np. 80% pojemności
  w cyklu odniesienia. Szukany na gęstej siatce do zadanego horyzontu.
- **Przedziały 95%:** bootstrap reszt. Reszty modelu losowane są ze zwracaniem i dodawane do dopasowanej
  krzywej, po czym model jest dopasowywany ponownie (200 powtórzeń, stałe ziarno, więc wynik jest
  powtarzalny). Przedział dla krzywej i dla EOL to percentyle 2,5 i 97,5. Przedział EOL pokazywany jest
  tylko wtedy, gdy próg przekroczyło ponad 10 replikacji.

### Test wsteczny

Model dopasowywany jest tylko do pierwszych p% cykli (domyślnie 40%), a jego prognoza porównywana jest
z pozostałymi pomiarami. Miarą błędu jest MAPE. Pokazuje to, jak wiarygodna byłaby prognoza zrobiona
wcześniej, na krótszym teście.

### Analiza dQ/dV

Proste różniczkowanie ΔQ/ΔV jest niestabilne na plateau napięcia, gdzie ΔV → 0. Dlatego dQ/dV liczone jest
metodą binowania napięcia:

1. przyrosty pojemności między kolejnymi punktami pomiarowymi przypisywane są do środka odpowiadającego
   im przedziału napięcia,
2. przyrosty sumowane są w przedziałach o szerokości 5 mV i dzielone przez szerokość przedziału,
3. wynik wygładzany jest filtrem Savitzky'ego-Golaya (okno 9, wielomian 2. stopnia).

Piki wykrywane są przez `scipy.signal.find_peaks` z progiem wyrazistości (prominence) równym 15% maksimum
sygnału. Ich położenie śledzone jest w kolejnych cyklach: przesuwanie się pików świadczy o rosnącej
polaryzacji, a zanik lub poszerzenie o zmianach w strukturze materiału.

### Radar literatury

- Wyszukiwanie w tytułach i abstraktach (`title_and_abstract.search`) z filtrem dat i typu publikacji.
  Prace z Polski filtrowane są przez `authorships.countries:PL`.
- Statystyki (trend roczny, czasopisma, instytucje, kraje, autorzy, udział open access) liczone są po stronie
  serwera przez `group_by`. Dzięki temu jedno zapytanie zastępuje pobieranie tysięcy rekordów.
- Abstrakty odtwarzane są z indeksu odwróconego (`abstract_inverted_index`), w którym OpenAlex je udostępnia.
- Opcjonalny klucz API zwiększa dzienny limit zapytań.

### Kalkulator syntezy

- **Parser wzorów chemicznych:** obsługuje nawiasy, indeksy ułamkowe i hydraty (`·`, `*`). Masy molowe
  liczone są z tablicy mas atomowych.
- **Produkt:** Na_x M[Fe(CN)₆]·yH₂O, gdzie M to mieszanina metali przejściowych o zadanych udziałach.
- **Entropia konfiguracyjna podsieci M:** S = −R·Σ xᵢ·ln xᵢ. Materiał jest niskoentropowy dla S < 1R,
  średnioentropowy dla 1R ≤ S < 1,5R i wysokoentropowy dla S ≥ 1,5R.
- **Pojemność teoretyczna:** Q = n·F / (3,6·M) [mAh/g], gdzie n = min(x, 1 + Σ x(Mn, Fe, Co)). Redoks
  zachodzi na Fe w Fe(CN)₆ i na aktywnych metalach w podsieci M. Ni, Cu i Zn traktowane są jako nieaktywne.
- **Naważki:** sole metali w proporcji do udziałów w podsieci M, heksacyjanożelazian i cytrynian sodu
  (czynnik chelatujący) w zadanych stosunkach molowych do sumy metali. Wydajność teoretyczna liczona jest
  na sumę metali M.

---

## Ograniczenia

- Prognoza to ekstrapolacja dopasowanej krzywej. Zakłada, że mechanizm degradacji się nie zmienia, więc nie
  przewidzi nagłego załamania pojemności (tzw. *knee point*).
- Bootstrap reszt uwzględnia szum pomiarowy, ale nie niepewność wyboru modelu. Przedziały są przez to raczej
  wąskie. Rozrzut między modelami w tabeli porównawczej i wynik testu wstecznego lepiej oddają realną
  niepewność.
- Analiza dQ/dV wymaga pełnych krzywych napięciowych, a nie tylko pojemności z każdego cyklu.
- Pojemność teoretyczna to uproszczenie: zakłada pełne wykorzystanie aktywnych centrów redoks i skład
  zgodny z założonym wzorem.

---

## Uruchomienie lokalne

```
pip install -r requirements.txt
streamlit run app.py
```

Klucz API OpenAlex (darmowy, https://openalex.org/settings/api) można wpisać w panelu bocznym albo zapisać
w `.streamlit/secrets.toml`:

```
OPENALEX_API_KEY = "twój_klucz"
```

---

## Struktura projektu

| Plik | Zawartość |
|---|---|
| `app.py` | interfejs Streamlit, cache zapytań, wykresy |
| `cycling.py` | wczytywanie plików z cyklera, wskaźniki cykli, cykle odstające, modele degradacji, bootstrap, test wsteczny, dQ/dV |
| `zenodo_data.py` | pobieranie i parsowanie zbioru z Zenodo |
| `openalex_client.py` | klient API OpenAlex: filtry, agregacje, abstrakty |
| `synthesis.py` | parser wzorów, masy molowe, entropia, plan syntezy |
| `demo_data.py` | generator danych symulowanych |
| `.streamlit/config.toml` | motyw i limit wielkości plików |

**Stack:** Python 3.12 · Streamlit · pandas · NumPy · SciPy · Plotly · Requests
