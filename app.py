import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
import base64
from collections import Counter

# Ustawienia strony
st.set_page_config(page_title="Panel Admina Śpiewnika", page_icon="⚙️", layout="wide")

# ─────────────────────────────────────────────
#  KONFIGURACJA GITHUB (DLA EXPORTU JSON)
# ─────────────────────────────────────────────
# Te wartości najlepiej dodać do secrets.toml we Streamlicie
GITHUB_TOKEN = st.secrets.get("github_token", "TWÓJ_TOKEN_GITHUB")
GITHUB_REPO = st.secrets.get("github_repo", "TWÓJ_LOGIN/TWÓJ_REPOSYTORIUM") # np. "jraciborski/spiewnik"
GITHUB_FILE_PATH = "songs.json"

# ─────────────────────────────────────────────
#  POŁĄCZENIE Z GOOGLE SHEETS
# ─────────────────────────────────────────────
def init_gsheet():
    try:
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            client = gspread.authorize(creds)
            # Twój zdefiniowany klucz arkusza
            return client.open_by_key("1RG82ZtUZfNsOjXI7xHKDnwbnDUl2SwE5oDLMNJNYdkw").worksheet("Songs")
        else:
            st.error("Brak konfiguracji 'gcp_service_account' w secrets.toml")
            return None
    except Exception as e:
        st.error(f"Błąd połączenia z Google Sheets: {e}")
        return None

ws = init_gsheet()

# ─────────────────────────────────────────────
#  LOGIKA PARSOWANIA BAZY DO JSON
# ─────────────────────────────────────────────
def get_all_songs_from_sheet():
    if not ws:
        return []
    
    rows = ws.get_all_values()
    if not rows or len(rows) <= 1:
        return []
    
    headers = rows[0]
    songs_list = []
    
    # Mapowanie kolumn na podstawie nagłówków w Twoim arkuszu
    # Załóżmy standard: Tytuł, Tekst_i_Chwyty, Tagi
    try:
        title_idx = headers.index("Tytuł")
        content_idx = headers.index("Tekst")
        tags_idx = headers.index("Tagi") if "Tagi" in headers else None
    except ValueError:
        st.error("Arkusz musi zawierać kolumny o nazwach 'Tytuł' oraz 'Tekst'.")
        return []

    for row in rows[1:]:
        if not row or len(row) <= max(title_idx, content_idx):
            continue
        
        title = row[title_idx].strip()
        raw_content = row[content_idx]
        
        if not title:
            continue
            
        tags = []
        if tags_idx is not None and len(row) > tags_idx and row[tags_idx]:
            tags = [t.strip() for t in row[tags_idx].split(",") if t.strip()]

        # Konwersja surowego tekstu z akordami w nawiasach kwadratowych [C] na strukturę liniową
        lyrics_structure = []
        lines = raw_content.split("\n")
        
        for line in lines:
            # Wyciągamy akordy z linii (np. "Tekst piosenki [C] [G]")
            chords = []
            # Szukamy wszystkiego co jest wewnątrz [ ]
            import re
            found_chords = re.findall(r'\[(.*?)\]', line)
            for c in found_chords:
                chords.append(c.strip())
            
            # Czyszczenie linii z akordów, aby został sam czysty tekst
            clean_text = re.sub(r'\[.*?\]', '', line).strip()
            
            lyrics_structure.append({
                "text": clean_text,
                "chords": chords
            })
            
        songs_list.append({
            "title": title,
            "tags": tags,
            "lyrics": lyrics_structure
        })
        
    return songs_list

# ─────────────────────────────────────────────
#  FUNKCJA WYPYCHAJĄCA PLIK DO GITHUB API
# ─────────────────────────────────────────────
def push_json_to_github(json_content_str):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 1. Musimy pobrać aktualną folię (SHA) pliku, jeśli istnieje, żeby go nadpisać
    sha = None
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        sha = res.json().get("sha")
        
    # 2. Przygotowanie danych do wysyłki
    message = "Update songs.json via Streamlit Admin Panel"
    content_b64 = base64.b64encode(json_content_str.encode('utf-8')).decode('utf-8')
    
    payload = {
        "message": message,
        "content": content_b64
    }
    if sha:
        payload["sha"] = sha
        
    # 3. Wysłanie pliku (PUT)
    put_res = requests.put(url, headers=headers, json=payload)
    return put_res.status_code in [200, 201], put_res.text

# ─────────────────────────────────────────────
#  INTERFEJS UŻYTKOWNIKA (STREAMLIT)
# ─────────────────────────────────────────────
st.title("⚙️ Panel Zarządzania Śpiewnikiem (Admin)")

tab1, tab2, tab3 = st.tabs(["📊 Statystyki & Publikacja", "➕ Dodaj Nową Piosenkę", "📋 Podgląd Bazy"])

with tab1:
    st.subheader("Stan Bazy Danych i Publikacja")
    
    if ws:
        songs_data = get_all_songs_from_sheet()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📚 Wszystkich utworów", len(songs_data))
        with col2:
            all_tags = [t for s in songs_data for t in s.get("tags", [])]
            st.metric("🏷️ Unikalnych tagów", len(set(all_tags)))
        with col3:
            st.info("Baza pobierana jest na bieżąco z Google Sheets.")
            
        st.markdown("---")
        st.subheader("🚀 Publikacja Śpiewnika na Świat")
        st.write("Kliknięcie poniższego przycisku spowoduje pobranie danych z Google Sheets, sformatowanie ich do pliku `songs.json` i automatyczne wgranie na Twój hosting GitHub Pages. Zmiana na stronie głównej pojawi się natychmiastowo!")
        
        if st.button("⚡ GENERUJ I PUBLIKUJ NOWĄ WERSJĘ", type="primary", use_container_width=True):
            with st.spinner("Pobieranie danych z Google Sheets i generowanie struktury JSON..."):
                songs_json = json.dumps(songs_data, ensure_ascii=False, indent=2)
                
            with st.spinner("Wysyłanie pliku do repozytorium GitHub..."):
                success, response_text = push_json_to_github(songs_json)
                if success:
                    st.success("🎉 Sukces! Śpiewnik został zaktualizowany i opublikowany w ułamku sekundy.")
                else:
                    st.error(f"Błąd publikacji na GitHub API. Sprawdź konfigurację tokenów. Kod błędu: {response_text}")
    else:
        st.warning("Brak połączenia z Google Sheets. Publikacja niemożliwa.")

with tab2:
    st.subheader("Formularz dodawania utworu")
    st.write("Wprowadź dane. Akordy w tekście zapisuj w nawiasach kwadratowych, np: *Chciałem przejść [C] suchą stopą [G]*")
    
    with st.form("add_song_form"):
        new_title = st.text_input("Tytuł Piosenki")
        new_tags = st.text_input("Tagi (rozdzielane przecinkami, np. turystyczne, bieszczady)")
        new_content = st.text_area("Tekst i chwyty (chwyty w nawiasach kwadratowych)", height=300)
        
        submit_btn = st.form_submit_button("Zapisz do Google Sheets")
        
        if submit_btn:
            if not new_title or not new_content:
                st.error("Tytuł i tekst nie mogą być puste!")
            elif not ws:
                st.error("Brak połączenia z bazą danych.")
            else:
                try:
                    # Dodaj wiersz do Arkusza Google: Tytuł, Tekst, Tagi
                    ws.append_row([new_title.strip(), new_content.strip(), new_tags.strip()])
                    st.success(f"Dodano piosenkę '{new_title}' do Google Sheets! Przejdź do zakładki pierwszej, aby ją opublikować.")
                except Exception as e:
                    st.error(f"Wystąpił błąd podczas zapisu: {e}")

with tab3:
    st.subheader("Aktualna zawartość tabeli Google Sheets")
    if ws:
        try:
            import pandas as pd
            data = ws.get_all_records()
            if data:
                st.dataframe(pd.DataFrame(data), use_container_width=True)
            else:
                st.write("Tabela jest pusta.")
        except Exception as e:
            st.write("Nie udało się wygenerować podglądu tabeli.")