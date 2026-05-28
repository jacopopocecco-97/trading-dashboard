import streamlit as st
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import time
import altair as alt

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Trading Dashboard", page_icon="📈", layout="wide")

# --- COSTANTI E CONFIGURAZIONI ---
SHEET_NAME = " TradingDashboard"
WORKSHEET_ATTIVE = "Posizioni_Attive"
WORKSHEET_STORICO = "Storico"
WORKSHEET_PREZZI = "Storico_Prezzi"
WORKSHEET_PENDING = "Ordini_Pending"
WORKSHEET_PORTAFOGLIO = "Storico_Portafoglio"

# --- FUNZIONI DI CONNESSIONE A GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        # Recupera le credenziali dai secrets di Streamlit
        skey = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(skey, scopes=scopes)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"Errore di connessione a Google Sheets. Verifica i Secrets. Dettagli: {e}")
        return None

@st.cache_resource
def get_worksheet(_client, ws_name):
    try:
        # Usiamo l'ID univoco così non importa se cambi il nome o togli gli spazi
        sheet = _client.open_by_key("1Y4qUgzJvrF6IE0Bv9DQzAo-SOkHqsx2CHQW-fBEoR3w")
        return sheet.worksheet(ws_name)
    except Exception as e:
        st.error(f"Errore nell'aprire il foglio '{ws_name}'. Assicurati che esista. Dettagli: {e}")
        return None

# --- FUNZIONI FINANZIARIE (YFINANCE) ---
def get_current_price(ticker_symbol):
    """Ottiene l'ultimo prezzo disponibile usando yfinance (incluso pre/after market se disponibile)."""
    try:
        ticker_obj = yf.Ticker(ticker_symbol)
        # Scarica l'ultimo minuto disponibile includendo pre e post market
        data = ticker_obj.history(period="1d", interval="1m", prepost=True)
        if not data.empty:
            return data['Close'].iloc[-1]
        # Fallback se non ci sono dati intraday
        return ticker_obj.fast_info.last_price
    except Exception:
        return None

# Mappa suffissi ticker -> valuta per dedurre la valuta corretta
# senza dipendere dall'API yfinance (che può fallire e ritornare 'USD' erroneamente)
SUFFIX_CURRENCY_MAP = {
    ".MI": "EUR", ".PA": "EUR", ".DE": "EUR", ".AS": "EUR", ".BR": "EUR",
    ".LS": "EUR", ".MC": "EUR", ".HE": "EUR", ".VI": "EUR", ".AT": "EUR",
    ".IR": "EUR", ".L": "GBP", ".SW": "CHF", ".TO": "CAD", ".AX": "AUD",
    ".HK": "HKD", ".T": "JPY", ".SS": "CNY", ".SZ": "CNY", ".KS": "KRW",
    ".NS": "INR", ".BO": "INR", ".SA": "BRL", ".MX": "MXN", ".ST": "SEK",
    ".CO": "DKK", ".OL": "NOK",
}

_currency_cache = {}

def _get_currency_from_suffix(ticker_symbol):
    """Deduce la valuta dal suffisso del ticker (es. .MI -> EUR)."""
    ticker_upper = ticker_symbol.upper()
    for suffix, currency in SUFFIX_CURRENCY_MAP.items():
        if ticker_upper.endswith(suffix.upper()):
            return currency
    return None

def get_stock_currency(ticker_symbol):
    """
    Ottiene la valuta di quotazione. Usa il suffisso del ticker come fallback
    per evitare il bug critico dove yfinance ritorna 'USD' per errore su titoli europei.
    """
    if ticker_symbol in _currency_cache:
        return _currency_cache[ticker_symbol]
    
    suffix_currency = _get_currency_from_suffix(ticker_symbol)
    
    try:
        ticker = yf.Ticker(ticker_symbol)
        api_currency = ticker.info.get("currency", None)
        
        if api_currency and api_currency != "USD":
            _currency_cache[ticker_symbol] = api_currency
            return api_currency
        elif api_currency == "USD":
            if suffix_currency and suffix_currency != "USD":
                _currency_cache[ticker_symbol] = suffix_currency
                return suffix_currency
            _currency_cache[ticker_symbol] = "USD"
            return "USD"
        else:
            if suffix_currency:
                _currency_cache[ticker_symbol] = suffix_currency
                return suffix_currency
            _currency_cache[ticker_symbol] = "USD"
            return "USD"
    except:
        if suffix_currency:
            _currency_cache[ticker_symbol] = suffix_currency
            return suffix_currency
        _currency_cache[ticker_symbol] = "USD"
        return "USD"

def get_conversion_rate(from_curr, to_curr):
    """Ottiene il tasso di conversione in tempo reale."""
    if from_curr == to_curr:
        return 1.0
    try:
        ticker = f"{from_curr}{to_curr}=X"
        return get_current_price(ticker)
    except:
        return 1.0

# --- INIZIALIZZAZIONE ---
st.title("📈 La Tua Dashboard di Trading")

client = get_gspread_client()
if not client:
    st.stop()

ws_attive = get_worksheet(client, WORKSHEET_ATTIVE)
ws_storico = get_worksheet(client, WORKSHEET_STORICO)
ws_prezzi = get_worksheet(client, WORKSHEET_PREZZI)
ws_pending = get_worksheet(client, WORKSHEET_PENDING)
ws_portafoglio = get_worksheet(client, WORKSHEET_PORTAFOGLIO)

if not ws_attive or not ws_storico:
    st.stop()

# Layout con tre tab
tab1, tab2, tab3 = st.tabs(["📊 Dashboard Posizioni", "➕ Nuova Posizione", "📈 Statistiche"])

# Inizializzazione chiavi per i form
if 'form_ticker' not in st.session_state:
    st.session_state.form_ticker = ""
if 'form_sl' not in st.session_state:
    st.session_state.form_sl = 0.0
if 'form_tp' not in st.session_state:
    st.session_state.form_tp = 0.0
if 'form_suggeritore' not in st.session_state:
    st.session_state.form_suggeritore = ""
if 'form_modello' not in st.session_state:
    st.session_state.form_modello = ""
if 'form_range_min' not in st.session_state:
    st.session_state.form_range_min = 0.0
if 'form_range_max' not in st.session_state:
    st.session_state.form_range_max = 0.0
if 'form_strategia' not in st.session_state:
    st.session_state.form_strategia = "Speculativo"
if 'form_orizzonte' not in st.session_state:
    st.session_state.form_orizzonte = 0
if 'form_tp2' not in st.session_state:
    st.session_state.form_tp2 = 0.0
if 'form_perc_tp1' not in st.session_state:
    st.session_state.form_perc_tp1 = 50

# --- TAB 1: DASHBOARD ---
with tab1:
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.header("Posizioni Attive")
    with col_t2:
        if st.button("🔄 Aggiorna Dati", width="stretch"):
            st.rerun()
            
    st.caption(f"Ultimo aggiornamento: {datetime.now().strftime('%H:%M:%S')}")

    # Carica dati attivi
    dati_attive = ws_attive.get_all_records(numericise_ignore=['all'])
    df_attive = pd.DataFrame(dati_attive) if dati_attive else pd.DataFrame()
    
    if df_attive.empty:
        st.info("Nessuna posizione attiva al momento.")
    else:
        
        # Colonne per l'aggiornamento
        df_display = df_attive.copy()
        prezzi_attuali = []
        pnl_perc_list = []
        
        righe_da_chiudere = []

        # Scorre le posizioni e controlla i prezzi
        for index, row in df_attive.iterrows():
            ticker = row.get("Ticker", "")
            
            def to_float(val):
                if isinstance(val, str):
                    val = val.replace(',', '.')
                try:
                    return float(val)
                except:
                    return 0.0
                    
            prezzo_ingresso = to_float(row.get("Prezzo_Entrata", 0))
            sl = to_float(row.get("Stop_Loss", 0))
            tp = to_float(row.get("Take_Profit", 0))
            valuta_inserita = row.get("Valuta_Entrata", "USD")
            
            suggeritore = row.get("Suggeritore", "")
            modello = row.get("Modello", "")
            
            # Prezzo in tempo reale dalla borsa
            prezzo_reale_borsa = get_current_price(ticker)
            
            if prezzo_reale_borsa is None:
                prezzi_attuali.append(None)
                pnl_perc_list.append(None)
                continue
            
            # Conversione valuta se necessario
            valuta_borsa = get_stock_currency(ticker)
            tasso = get_conversion_rate(valuta_borsa, valuta_inserita)
            
            # Prezzo convertito nella valuta scelta dall'utente
            prezzo_corrente_convertito = prezzo_reale_borsa * tasso
            prezzi_attuali.append(round(prezzo_corrente_convertito, 2))
            
            # Calcolo P/L
            if prezzo_ingresso > 0:
                pnl = ((prezzo_corrente_convertito - prezzo_ingresso) / prezzo_ingresso) * 100
            else:
                pnl = 0.0
            pnl_perc_list.append(round(pnl, 2))
            
            # (Il controllo SL/TP e il logging dei prezzi sono ora gestiti in background dal file bot.py)

        df_display["Prezzo_Attuale"] = prezzi_attuali
        df_display["P/L %"] = pnl_perc_list
        
        # Mostra la tabella
        st.dataframe(df_display, width="stretch")

        # --- SEZIONE GESTIONE (ELIMINA POSIZIONE) ---
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🗑️ Elimina una posizione (Senza salvarla nello storico)"):
            col_del1, col_del2 = st.columns([3, 1])
            
            # Creiamo opzioni con Ticker e Prezzo per capire quale stiamo cancellando
            opzioni_elimina = [f"Riga {idx + 2}: {row.get('Ticker', '')} (Aperta a {row.get('Prezzo_Entrata', '')})" for idx, row in df_attive.iterrows()]
            
            with col_del1:
                riga_da_eliminare = st.selectbox("Seleziona la posizione da cestinare:", ["-- Seleziona --"] + opzioni_elimina)
            
            with col_del2:
                st.markdown("<br>", unsafe_allow_html=True) # Allineamento col selectbox
                if riga_da_eliminare != "-- Seleziona --":
                    if st.button("🗑️ Cestina Definitivamente", type="primary"):
                        # Estrae l'indice di riga dalla stringa "Riga 3: AAPL..."
                        riga_idx = int(riga_da_eliminare.split(":")[0].replace("Riga ", ""))
                        try:
                            ws_attive.delete_rows(riga_idx)
                            st.success("Posizione eliminata e cancellata dal foglio!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante l'eliminazione: {e}")

    st.divider()
    st.header("⏳ Ordini Pending (In attesa di esecuzione)")
    dati_pending = ws_pending.get_all_records(numericise_ignore=['all']) if ws_pending else []
    if not dati_pending:
        st.info("Nessun ordine pending al momento.")
    else:
        df_pending = pd.DataFrame(dati_pending)
        st.dataframe(df_pending, width="stretch")
        
        with st.expander("🗑️ Annulla un ordine pending"):
            col_delp1, col_delp2 = st.columns([3, 1])
            opzioni_elimina_p = [f"Riga {idx + 2}: {row.get('Ticker', '')} (Range: {row.get('Prezzo_Min', '')} - {row.get('Prezzo_Max', '')})" for idx, row in df_pending.iterrows()]
            with col_delp1:
                riga_da_eliminare_p = st.selectbox("Seleziona l'ordine da annullare:", ["-- Seleziona --"] + opzioni_elimina_p)
            with col_delp2:
                st.markdown("<br>", unsafe_allow_html=True)
                if riga_da_eliminare_p != "-- Seleziona --":
                    if st.button("🗑️ Annulla Ordine", type="primary"):
                        riga_idx = int(riga_da_eliminare_p.split(":")[0].replace("Riga ", ""))
                        try:
                            ws_pending.delete_rows(riga_idx)
                            st.success("Ordine pending annullato!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante l'eliminazione: {e}")

    st.divider()
    st.header("Storico Posizioni Chiuse")
    dati_storico = ws_storico.get_all_records(numericise_ignore=['all'])
    if dati_storico:
        st.dataframe(pd.DataFrame(dati_storico), width="stretch")
    else:
        st.info("Lo storico è vuoto.")

    st.divider()
    st.header("📈 Trend Prezzi (Storico Salvato)")
    
    tickers_attivi = set(df_attive['Ticker'].tolist()) if not df_attive.empty else set()
    tickers_storico = set(pd.DataFrame(dati_storico)['Ticker'].tolist()) if dati_storico else set()
    
    tutti_tickers = sorted(list(tickers_attivi | tickers_storico))
    opzioni_tickers = [f"🟢 {t} (Attiva)" if t in tickers_attivi else f"🔴 {t} (Chiusa)" for t in tutti_tickers]
    
    if opzioni_tickers:
        ticker_selezionato_label = st.selectbox("Seleziona un'azione per vedere l'andamento del suo prezzo registrato:", opzioni_tickers)
        ticker_selezionato = ticker_selezionato_label.split(" ")[1] # Estrae il ticker puro, es. "TSLA"
        
        if ws_prezzi:
            dati_prezzi = ws_prezzi.get_all_records(numericise_ignore=['all'])
            if dati_prezzi:
                df_prezzi = pd.DataFrame(dati_prezzi)
                if 'Ticker' in df_prezzi.columns:
                    df_prezzi_ticker = df_prezzi[df_prezzi['Ticker'] == ticker_selezionato].copy()
                    
                    if not df_prezzi_ticker.empty:
                        def to_float_safe(val):
                            if isinstance(val, str):
                                val = val.replace(',', '.')
                            try:
                                return float(val)
                            except:
                                return 0.0
                        df_prezzi_ticker['Prezzo'] = df_prezzi_ticker['Prezzo'].apply(to_float_safe)
                        df_prezzi_ticker['Data_Ora'] = pd.to_datetime(df_prezzi_ticker['Data_Ora'])
                        
                        # Cerca il prezzo di acquisto (Prezzo_Entrata) per il ticker selezionato
                        prezzo_acquisto = None
                        if not df_attive.empty:
                            df_target = df_attive[df_attive['Ticker'] == ticker_selezionato]
                            if not df_target.empty:
                                prezzo_acquisto = to_float_safe(df_target.iloc[-1].get('Prezzo_Entrata', 0))
                        
                        if prezzo_acquisto is None and dati_storico:
                            df_stor_temp = pd.DataFrame(dati_storico)
                            if not df_stor_temp.empty and 'Ticker' in df_stor_temp.columns:
                                df_target = df_stor_temp[df_stor_temp['Ticker'] == ticker_selezionato]
                                if not df_target.empty:
                                    prezzo_acquisto = to_float_safe(df_target.iloc[-1].get('Prezzo_Entrata', 0))
                        
                        ultimo_prezzo = df_prezzi_ticker['Prezzo'].iloc[-1]
                        
                        # Determina colore e visualizza banner informativo
                        if prezzo_acquisto is not None and prezzo_acquisto > 0:
                            guadagno = ultimo_prezzo >= prezzo_acquisto
                            chart_color = '#2ecc71' if guadagno else '#e74c3c'
                            pnl_val = ((ultimo_prezzo - prezzo_acquisto) / prezzo_acquisto) * 100
                            
                            # Mostra un messaggio di stato colorato
                            if guadagno:
                                st.success(f"📈 **Azione in Guadagno!** | Prezzo Acquisto: **{prezzo_acquisto:.2f}** | Ultimo Rilevato: **{ultimo_prezzo:.2f}** (**{pnl_val:+.2f}%**)")
                            else:
                                st.error(f"📉 **Azione in Perdita!** | Prezzo Acquisto: **{prezzo_acquisto:.2f}** | Ultimo Rilevato: **{ultimo_prezzo:.2f}** (**{pnl_val:+.2f}%**)")
                        else:
                            chart_color = '#3498db'
                            st.info(f"ℹ️ Prezzo di acquisto non trovato per questo ticker nelle posizioni attive o storiche. | Ultimo Prezzo: **{ultimo_prezzo:.2f}**")
                        
                        # Creazione grafico base della linea dei prezzi
                        base_chart = alt.Chart(df_prezzi_ticker).mark_line(
                            point=True,
                            color=chart_color,
                            strokeWidth=3
                        ).encode(
                            x=alt.X('Data_Ora:T', title='Data e Ora'),
                            y=alt.Y('Prezzo:Q', title='Prezzo Registrato', scale=alt.Scale(zero=False)),
                            tooltip=['Data_Ora', 'Prezzo']
                        ).properties(height=350)
                        
                        final_chart = base_chart
                        
                        # Aggiunge la linea del prezzo di acquisto (se disponibile)
                        if prezzo_acquisto is not None and prezzo_acquisto > 0:
                            # Linea orizzontale
                            rule_df = pd.DataFrame({'Prezzo_Acquisto': [prezzo_acquisto]})
                            rule_chart = alt.Chart(rule_df).mark_rule(
                                color='#f39c12',
                                strokeDash=[6, 4],
                                strokeWidth=2
                            ).encode(
                                y='Prezzo_Acquisto:Q'
                            )
                            
                            # Label per la linea posizionata alla fine del grafico (data più recente)
                            max_date = df_prezzi_ticker['Data_Ora'].max()
                            text_df = pd.DataFrame({
                                'Data_Ora': [max_date],
                                'Prezzo_Acquisto': [prezzo_acquisto],
                                'Label': [f"Acquisto: {prezzo_acquisto:.2f}"]
                            })
                            text_chart = alt.Chart(text_df).mark_text(
                                align='right',
                                dx=-10,
                                dy=-15,
                                color='#f39c12',
                                fontSize=11,
                                fontWeight='bold'
                            ).encode(
                                x='Data_Ora:T',
                                y='Prezzo_Acquisto:Q',
                                text='Label:N'
                            )
                            
                            final_chart = alt.layer(base_chart, rule_chart, text_chart)
                        
                        st.altair_chart(final_chart, use_container_width=True)
                    else:
                        st.info(f"Nessun prezzo registrato ancora per {ticker_selezionato}. Verrà registrato al prossimo aggiornamento (se l'azione è attiva).")
            else:
                st.info("Il database dei prezzi è ancora vuoto. Inizierà a riempirsi nei prossimi minuti.")
    else:
        st.info("Aggiungi un'azione per iniziare a tracciarne il prezzo.")

# --- TAB 2: NUOVA POSIZIONE ---
with tab2:
    st.header("Aggiungi Nuova Posizione")
    
    st.subheader("🤖 Assistente IA (Generatore Prompt e Import)")
    with st.expander("Usa l'Intelligenza Artificiale per compilare in automatico"):
        import locale
        import pytz
        try:
            locale.setlocale(locale.LC_TIME, "it_IT.UTF-8")
        except:
            pass # Ignora se la lingua italiana non è installata nel sistema
            
        tz_rome = pytz.timezone("Europe/Rome")
        now_rome = datetime.now(tz_rome)
        
        oggi_str = now_rome.strftime("%d %B %Y")
        ora_str = now_rome.strftime("%H:%M")
        
        # Selectbox for strategy
        strategia_scelta = st.selectbox("🎯 Scegli l'orizzonte temporale / Strategia per la ricerca:", 
            ["Speculativo", "Breve termine", "Medio termine", "Lungo termine"])
            
        descrizione_strategia = ""
        if strategia_scelta == "Speculativo":
            descrizione_strategia = "Ricerca almeno 3 titoli ad altissima volatilità, breakout veloci o meme stocks da acquistare per pura speculazione."
        elif strategia_scelta == "Breve termine":
            descrizione_strategia = "Ricerca almeno 3 titoli per un'operatività swing trading da acquistare e rivendere nel giro di qualche giorno o poche settimane, basati su catalyst imminenti."
        elif strategia_scelta == "Medio termine":
            descrizione_strategia = "Ricerca almeno 3 titoli (Value o Growth) con solide basi fondamentali per un investimento di medio termine (qualche mese)."
        elif strategia_scelta == "Lungo termine":
            descrizione_strategia = "Ricerca almeno 3 titoli per un investimento Buy and Hold a lungo termine (anni) basati su mega-trend strutturali."

        # Logica orari mercato USA (considerando Pre e After market: 10:00 - 02:00 orario italiano)
        is_weekend = now_rome.weekday() >= 5
        is_closed_hours = now_rome.hour >= 2 and now_rome.hour < 10
        
        if is_weekend or is_closed_hours:
            frase_entrata = "I mercati americani (incluso l'intero pre e after market) in questo momento sono CHIUSI. L'ipotetica entrata a mercato dovrà per forza avvenire al primo giorno utile e alla primissima ora utile della riapertura ufficiale dei mercati."
        else:
            frase_entrata = f"I mercati sono attualmente in contrattazione. L'ipotetica entrata a mercato sarebbe esattamente oggi {oggi_str} alle ore {ora_str}."
        
        prompt_ia = f"""{descrizione_strategia} Esponi il rendimento atteso e il rischio sottostante. Valuta e stima anche l'orizzonte in durata di giorni dell'investimento.
Attenzione: in Italia siamo al {oggi_str} ore {ora_str}. Prendi notizie aggiornate e, se disponibili, guardati i valori di pre-market e after-market odierni.
{frase_entrata}
In passato hai selezionato azioni giuste se fossero state prese però 1 o 2 giorni indietro. Non fare questo errore.

IMPORTANTE: Alla fine della tua analisi, DEVI fornire i dati delle azioni che hai scelto per l'investimento ESCLUSIVAMENTE in questo formato JSON, racchiuso in un blocco di codice. Sostituisci i valori ma mantieni rigorosamente questa struttura:
```json
{{
  "ticker": "AAPL",
  "sl": 150.5,
  "tp": 190.0,
  "range_min": 160.0,
  "range_max": 165.0,
  "suggeritore": "Inserisci il tuo nome (es. Gemini o Claude)",
  "modello": "Inserisci la tua versione esatta (es. Gemini 1.5 Pro, Claude 3 Opus)",
  "strategia": "{strategia_scelta}",
  "orizzonte_giorni": 14
}}
```"""
        st.markdown("**1. Copia questo prompt (con le date di oggi aggiornate) e incollalo su Gemini o Claude:**")
        st.code(prompt_ia, language="text")
        
        st.markdown("**2. Incolla qui sotto il codice JSON che ti restituisce l'IA:**")
        json_input = st.text_area("JSON dell'IA", height=150, label_visibility="collapsed")
        
        if st.button("🔽 Importa Dati IA nel Modulo"):
            import json
            import re
            try:
                # Cerca e prova a estrarre solo il JSON anche se c'è testo intorno
                match = re.search(r'\{.*\}', json_input, re.DOTALL)
                if match:
                    dati_ia = json.loads(match.group())
                    st.session_state.form_ticker = dati_ia.get("ticker", "")
                    st.session_state.form_sl = float(dati_ia.get("sl", 0.0))
                    st.session_state.form_tp = float(dati_ia.get("tp", 0.0))
                    st.session_state.form_suggeritore = dati_ia.get("suggeritore", "IA")
                    st.session_state.form_modello = dati_ia.get("modello", "AI Generated")
                    st.session_state.form_range_min = float(dati_ia.get("range_min", 0.0))
                    st.session_state.form_range_max = float(dati_ia.get("range_max", 0.0))
                    st.session_state.form_strategia = dati_ia.get("strategia", "Speculativo")
                    st.session_state.form_orizzonte = int(dati_ia.get("orizzonte_giorni", 0))
                    st.success("Dati importati con successo! Scorri giù per cercare il prezzo e confermare.")
                else:
                    st.error("Nessun JSON valido trovato nel testo incollato.")
            except Exception as e:
                st.error(f"Errore nella lettura del JSON: {e}")
                
    st.markdown("---")
    
    ticker_input = st.text_input("Ticker Azione (es. TSLA, AAPL, UCG.MI)", key="form_ticker").upper()
    valuta_input = st.selectbox("Valuta di riferimento per i prezzi", ["USD", "EUR"])
    
    col1, col2, col_tp2, col_perc = st.columns(4)
    with col1:
        sl_input = st.number_input("Stop Loss", min_value=0.0, format="%.2f", step=0.5, key="form_sl")
    with col2:
        tp_input = st.number_input("TP 1", min_value=0.0, format="%.2f", step=0.5, key="form_tp")
    with col_tp2:
        tp2_input = st.number_input("TP 2", min_value=0.0, format="%.2f", step=0.5, key="form_tp2")
    with col_perc:
        perc_tp1_input = st.number_input("% Vendi TP1", min_value=0, max_value=100, step=10, key="form_perc_tp1")
        
    col3, col4 = st.columns(2)
    with col3:
        strategia_input = st.selectbox("Strategia", ["Speculativo", "Breve termine", "Medio termine", "Lungo termine"], key="form_strategia")
    with col4:
        orizzonte_input = st.number_input("Orizzonte (Giorni)", min_value=0, step=1, key="form_orizzonte")
        
    st.markdown("---")
    st.subheader("Range di Entrata (Ordini Pending)")
    st.markdown("Imposta un range per far entrare il bot automaticamente. Se inserisci 0, non verrà considerato. Spunta la casella sotto per un range ±1% automatico.")
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        range_min_input = st.number_input("Prezzo Minimo di Entrata", min_value=0.0, format="%.2f", step=0.5, key="form_range_min")
    with col_r2:
        range_max_input = st.number_input("Prezzo Massimo di Entrata", min_value=0.0, format="%.2f", step=0.5, key="form_range_max")
    with col_r3:
        st.markdown("<br>", unsafe_allow_html=True)
        auto_range = st.checkbox("Attiva Range ±1% automatico dal prezzo attuale", value=False)

    st.markdown("---")
    st.subheader("Informazioni Aggiuntive")
    col6, col7 = st.columns(2)
    with col6:
        suggeritore_input = st.text_input("Suggeritore (es. Nome, Telegram, Analisi Tecnica)", key="form_suggeritore")
    with col7:
        modello_input = st.text_input("Modello o Strategia (es. Breakout, RSI, Scalping)", key="form_modello")

    st.markdown("---")
    st.subheader("Dettagli di Entrata")
    st.markdown("Se non conosci il prezzo di entrata, lascia `0.00` e clicca su **Cerca Prezzo Attuale**. Altrimenti inserisci tu i valori per operazioni passate.")
    
    col3, col4, col5 = st.columns(3)
    with col3:
        prezzo_input = st.number_input("Prezzo di Entrata", min_value=0.0, format="%.2f", step=0.5)
    with col4:
        data_input = st.date_input("Data di Entrata", value=datetime.today())
    with col5:
        ora_input = st.time_input("Ora di Entrata", value=datetime.now().time())
        
    data_ora_str = f"{data_input.strftime('%Y-%m-%d')} {ora_input.strftime('%H:%M:%S')}"
    
    if prezzo_input == 0.0:
        # Modalità Automatica (Prezzo = 0)
        if st.button("Calcola Prezzo Attuale 🔍"):
            if not ticker_input:
                st.error("Inserisci un ticker valido.")
            else:
                with st.spinner(f"Recupero prezzo attuale per {ticker_input}..."):
                    prezzo_borsa = get_current_price(ticker_input)
                    
                    if prezzo_borsa is None:
                        st.error(f"Impossibile trovare il ticker {ticker_input} su Yahoo Finance.")
                    else:
                        # Gestione valuta
                        valuta_borsa = get_stock_currency(ticker_input)
                        tasso = get_conversion_rate(valuta_borsa, valuta_input)
                        prezzo_entrata = round(prezzo_borsa * tasso, 2)
                        
                        st.session_state['pending_position'] = {
                            'ticker': ticker_input,
                            'prezzo': prezzo_entrata,
                            'valuta': valuta_input
                        }
                        
        # Mostra la conferma se c'è una posizione in attesa
        if 'pending_position' in st.session_state:
            p = st.session_state['pending_position']
            if p['ticker'] == ticker_input and p['valuta'] == valuta_input:
                st.info(f"📊 Il prezzo attuale per **{p['ticker']}** è di **{p['prezzo']} {p['valuta']}**.")
                
                if sl_input == 0 or tp_input == 0:
                    st.warning("Inserisci i valori di **Stop Loss** e **Take Profit** nei campi sopra per poter confermare l'apertura.")
                else:
                    is_pending = False
                    p_min = range_min_input
                    p_max = range_max_input
                    
                    if auto_range:
                        p_min = round(p['prezzo'] * 0.99, 2)
                        p_max = round(p['prezzo'] * 1.01, 2)
                        is_pending = True
                    elif range_min_input > 0 or range_max_input > 0:
                        is_pending = True
                        
                    if is_pending:
                        st.write(f"Vuoi inviare l'ordine ai **PENDING** con range di ingresso [{p_min} - {p_max}], SL a {sl_input}, TP1 a {tp_input}, TP2 a {tp2_input}?")
                        if st.button("⏳ Salva come Ordine Pending"):
                            nuova_riga = [p['ticker'], p_min, p_max, p['valuta'], sl_input, tp_input, tp2_input, perc_tp1_input, data_ora_str, suggeritore_input, modello_input, strategia_input, orizzonte_input]
                            try:
                                ws_pending.append_row(nuova_riga, value_input_option='USER_ENTERED')
                                st.success(f"Ordine pending su {p['ticker']} aggiunto con successo!")
                                del st.session_state['pending_position']
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore durante il salvataggio su Google Sheets: {e}")
                    else:
                        st.write(f"Vuoi confermare l'apertura **IMMEDIATA** a questo prezzo con SL a {sl_input}, TP1 a {tp_input}, TP2 a {tp2_input}?")
                        if st.button("✅ Conferma e Apri Posizione"):
                            # Aggiungiamo anche il flag TP1_Raggiunto = "FALSE"
                            nuova_riga = [p['ticker'], p['prezzo'], p['valuta'], sl_input, tp_input, tp2_input, perc_tp1_input, "FALSE", data_ora_str, suggeritore_input, modello_input, strategia_input, orizzonte_input]
                            try:
                                ws_attive.append_row(nuova_riga, value_input_option='USER_ENTERED')
                                st.success(f"Posizione su {p['ticker']} aggiunta con successo! Aggiornamento dashboard...")
                                del st.session_state['pending_position']
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore durante il salvataggio su Google Sheets: {e}")
            else:
                del st.session_state['pending_position']
                
    else:
        # Modalità Manuale (Prezzo > 0)
        is_pending = (range_min_input > 0 or range_max_input > 0) or auto_range
        label_btn = "⏳ Salva come Ordine Pending" if is_pending else "✅ Salva Posizione Manuale"
        
        if st.button(label_btn):
            if not ticker_input:
                st.error("Inserisci un ticker valido.")
            elif sl_input == 0 or tp_input == 0:
                st.error("Inserisci valori validi per Stop Loss e Take Profit.")
            else:
                if is_pending:
                    p_min = range_min_input
                    p_max = range_max_input
                    if auto_range:
                        p_min = round(prezzo_input * 0.99, 2)
                        p_max = round(prezzo_input * 1.01, 2)
                        
                    nuova_riga = [ticker_input, p_min, p_max, valuta_input, sl_input, tp_input, tp2_input, perc_tp1_input, data_ora_str, suggeritore_input, modello_input, strategia_input, orizzonte_input]
                    try:
                        ws_pending.append_row(nuova_riga, value_input_option='USER_ENTERED')
                        st.success(f"Ordine pending su {ticker_input} aggiunto con successo!")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante il salvataggio: {e}")
                else:
                    # Aggiungiamo anche il flag TP1_Raggiunto = "FALSE"
                    nuova_riga = [ticker_input, prezzo_input, valuta_input, sl_input, tp_input, tp2_input, perc_tp1_input, "FALSE", data_ora_str, suggeritore_input, modello_input, strategia_input, orizzonte_input]
                    try:
                        ws_attive.append_row(nuova_riga, value_input_option='USER_ENTERED')
                        st.success(f"Posizione manuale su {ticker_input} aggiunta con successo! Aggiornamento dashboard...")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante il salvataggio: {e}")

# --- TAB 3: STATISTICHE E GRAFICI ---
with tab3:
    st.header("Statistiche e Grafici di Portafoglio")
    
    # Pulizia e conversione dati
    def to_float_safe(val):
        if isinstance(val, str):
            val = val.replace(',', '.')
        try:
            return float(val)
        except:
            return 0.0

    # Carichiamo lo storico (posizioni chiuse)
    dati_stats = ws_storico.get_all_records(numericise_ignore=['all'])
    df_stats = pd.DataFrame(dati_stats) if dati_stats else pd.DataFrame()
    if not df_stats.empty:
        df_stats['P_L_Perc'] = df_stats.get('P_L_Perc', pd.Series([0]*len(df_stats))).apply(to_float_safe)
        if 'Data_Ora_Entrata' in df_stats.columns:
            df_stats.rename(columns={'Data_Ora_Entrata': 'Data_Ora'}, inplace=True)
        if 'Strategia' not in df_stats.columns:
            df_stats['Strategia'] = ''
        
    # Carichiamo le posizioni aperte dalla dashboard (se esistono)
    df_aperte_stats = pd.DataFrame()
    if 'df_display' in locals() and not df_display.empty and 'P/L %' in df_display.columns:
        colonne_da_prendere = ['Ticker', 'P/L %', 'Suggeritore', 'Modello', 'Data_Ora']
        if 'Strategia' in df_display.columns:
            colonne_da_prendere.append('Strategia')
        df_aperte_stats = df_display[colonne_da_prendere].copy()
        if 'Strategia' not in df_aperte_stats.columns:
            df_aperte_stats['Strategia'] = ''
        df_aperte_stats.rename(columns={'P/L %': 'P_L_Perc'}, inplace=True)
        df_aperte_stats = df_aperte_stats.dropna(subset=['P_L_Perc'])
        
    # Unione dei due dataframe
    df_combined = pd.concat([df_stats, df_aperte_stats], ignore_index=True)
    
    # Definizione funzione di matching per le strategie tollerante a variazioni
    def match_strategia(val):
        if not isinstance(val, str):
            return False
        val_clean = val.strip().lower()
        filtro_clean = strategia_filtro.strip().lower()
        
        if val_clean == filtro_clean:
            return True
        if "breve" in filtro_clean and "breve" in val_clean:
            return True
        if "medio" in filtro_clean and "medio" in val_clean:
            return True
        if "lungo" in filtro_clean and "lungo" in val_clean:
            return True
        if "speculativo" in filtro_clean and "speculativo" in val_clean:
            return True
        return False

    # Menu a tendina e Date Picker per filtrare le statistiche in 3 colonne
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        tipo_operazioni = st.selectbox("📊 Seleziona le operazioni da analizzare:", 
                                       ["Totale (Media)", "Posizioni Aperte", "Posizioni Chiuse"])
                                       
    with col_f2:
        # Raccogliamo in modo sicuro TUTTE le strategie esistenti in TUTTI i fogli Google Sheet
        strategie_presenti = ["Tutte"]
        all_strategies = set()
        
        # Carica i dati dai vari fogli usando le variabili locali o interrogando i fogli direttamente
        d_att = dati_attive if 'dati_attive' in locals() else (ws_attive.get_all_records(numericise_ignore=['all']) if ws_attive else [])
        d_st = dati_stats if 'dati_stats' in locals() else (ws_storico.get_all_records(numericise_ignore=['all']) if ws_storico else [])
        d_pend = dati_pending if 'dati_pending' in locals() else (ws_pending.get_all_records(numericise_ignore=['all']) if ws_pending else [])
        
        for dataset in [d_att, d_st, d_pend]:
            if dataset:
                for row in dataset:
                    strat = row.get('Strategia') or row.get('strategia')
                    if strat:
                        all_strategies.add(str(strat).strip())
                        
        # Aggiungiamo anche le strategie predefinite per garantire che non manchino mai
        strategie_predefinite = ["Speculativo", "Breve termine", "Medio termine", "Lungo termine"]
        for s in strategie_predefinite:
            all_strategies.add(s)
            
        # Pulisce, deduplica e ordina
        unique_strats = sorted(list(set(
            s for s in all_strategies if s and s.strip() != ""
        )))
        seen_lower = set()
        deduped_strats = []
        for s in unique_strats:
            if s.lower() not in seen_lower:
                seen_lower.add(s.lower())
                deduped_strats.append(s)
        deduped_strats.sort(key=str.lower)
        strategie_presenti.extend(deduped_strats)
        
        strategia_filtro = st.selectbox("🎯 Filtra per strategia:", strategie_presenti)
                                       
    # Filtriamo provvisoriamente i dati in base alla tipologia selezionata
    if tipo_operazioni == "Posizioni Aperte":
        df_base = df_aperte_stats.copy() if not df_aperte_stats.empty else pd.DataFrame()
    elif tipo_operazioni == "Posizioni Chiuse":
        df_base = df_stats.copy() if not df_stats.empty else pd.DataFrame()
    else:
        df_base = df_combined.copy() if not df_combined.empty else pd.DataFrame()
        
    # Filtriamo per strategia prima di calcolare i limiti temporali
    if strategia_filtro != "Tutte" and not df_base.empty and 'Strategia' in df_base.columns:
        df_base = df_base[df_base['Strategia'].apply(match_strategia)]
        
    date_range = None
    if not df_base.empty and 'Data_Ora' in df_base.columns:
        df_base['Data_Ora_parsed'] = pd.to_datetime(df_base['Data_Ora'], errors='coerce')
        df_base = df_base.dropna(subset=['Data_Ora_parsed'])
        
        if not df_base.empty:
            min_date = df_base['Data_Ora_parsed'].min().date()
            max_date = df_base['Data_Ora_parsed'].max().date()
        else:
            min_date = datetime.today().date()
            max_date = datetime.today().date()
            
        with col_f3:
            valore_iniziale = (min_date, max_date)
            date_range = st.date_input(
                "📅 Filtra per data di acquisto (Range):",
                value=valore_iniziale,
                min_value=min_date,
                max_value=max_date
            )
    else:
        with col_f3:
            st.info("Nessuna data di acquisto disponibile per questa selezione.")
            
    # Filtriamo definitivamente df_filtered in base a tipologia + strategia + range di date
    df_filtered = df_base.copy() if not df_base.empty else pd.DataFrame()
    
    if not df_filtered.empty and date_range:
        if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
            start_date, end_date = date_range
            start_ts = pd.Timestamp(start_date)
            end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            df_filtered = df_filtered[
                (df_filtered['Data_Ora_parsed'] >= start_ts) & 
                (df_filtered['Data_Ora_parsed'] <= end_ts)
            ]
        elif isinstance(date_range, (tuple, list)) and len(date_range) == 1:
            start_ts = pd.Timestamp(date_range[0])
            df_filtered = df_filtered[df_filtered['Data_Ora_parsed'] >= start_ts]

    if df_filtered.empty:
        st.info(f"Non ci sono operazioni per la selezione '{tipo_operazioni}', strategia '{strategia_filtro}' e range selezionato.")
    else:
        # Metriche in alto
        totale = len(df_filtered)
        vincenti = len(df_filtered[df_filtered['P_L_Perc'] > 0])
        win_rate = (vincenti / totale * 100) if totale > 0 else 0
        profitto_medio = df_filtered[df_filtered['P_L_Perc'] > 0]['P_L_Perc'].mean()
        perdita_media = df_filtered[df_filtered['P_L_Perc'] <= 0]['P_L_Perc'].mean()
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric(f"Operazioni ({tipo_operazioni})", totale)
        col_m2.metric("Win Rate", f"{win_rate:.1f}%")
        col_m3.metric("Profitto Medio (Winner)", f"+{profitto_medio:.2f}%" if pd.notna(profitto_medio) else "0%")
        col_m4.metric("Perdita Media (Loser)", f"{perdita_media:.2f}%" if pd.notna(perdita_media) else "0%")
        
        st.divider()
        st.subheader("Andamento Portafoglio nel Tempo")
        
        # Scegliamo la colonna e il titolo in base al filtro
        colonna_y = 'P_L_Complessivo'
        titolo_y = 'P&L Complessivo %'
        if tipo_operazioni == 'Posizioni Aperte':
            colonna_y = 'P_L_Aperto'
            titolo_y = 'P&L Aperto %'
        elif tipo_operazioni == 'Posizioni Chiuse':
            colonna_y = 'P_L_Chiuso'
            titolo_y = 'P&L Chiuso %'
            
        st.markdown(f"Tracciamento reale del controvalore **{titolo_y}** registrato ogni 10 minuti dal bot.")
        if ws_portafoglio:
            dati_portafoglio = ws_portafoglio.get_all_records(numericise_ignore=['all'])
            if dati_portafoglio:
                df_portafoglio = pd.DataFrame(dati_portafoglio)
                df_portafoglio['Data_Ora'] = pd.to_datetime(df_portafoglio['Data_Ora'])
                df_portafoglio[colonna_y] = df_portafoglio[colonna_y].apply(to_float_safe)
                
                # Filtro per strategia
                if 'Strategia' in df_portafoglio.columns:
                    if strategia_filtro == "Tutte":
                        df_portafoglio = df_portafoglio[(df_portafoglio['Strategia'] == 'Tutte') | (df_portafoglio['Strategia'] == '') | (df_portafoglio['Strategia'].isna())]
                    else:
                        df_portafoglio = df_portafoglio[df_portafoglio['Strategia'].apply(match_strategia)]
                else:
                    if strategia_filtro != "Tutte":
                        st.info("Nota: I dati storici temporali per singole strategie saranno registrati a partire dalle prossime esecuzioni del bot.")
                
                # Filtro per data
                if date_range and not df_portafoglio.empty:
                    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
                        start_date, end_date = date_range
                        start_ts = pd.Timestamp(start_date)
                        end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                        df_portafoglio = df_portafoglio[
                            (df_portafoglio['Data_Ora'] >= start_ts) & 
                            (df_portafoglio['Data_Ora'] <= end_ts)
                        ]
                    elif isinstance(date_range, (tuple, list)) and len(date_range) == 1:
                        start_ts = pd.Timestamp(date_range[0])
                        df_portafoglio = df_portafoglio[df_portafoglio['Data_Ora'] >= start_ts]
                
                if not df_portafoglio.empty:
                    chart_portafoglio = alt.Chart(df_portafoglio).mark_area(
                        line={'color':'#2ecc71'},
                        color=alt.Gradient(
                            gradient='linear',
                            stops=[alt.GradientStop(color='#2ecc71', offset=0),
                                   alt.GradientStop(color='rgba(46, 204, 113, 0.1)', offset=1)],
                            x1=1, x2=1, y1=1, y2=0
                        )
                    ).encode(
                        x=alt.X('Data_Ora:T', title='Data e Ora'),
                        y=alt.Y(f'{colonna_y}:Q', title=titolo_y, scale=alt.Scale(zero=False)),
                        tooltip=['Data_Ora', 'P_L_Complessivo', 'P_L_Aperto', 'P_L_Chiuso']
                    ).properties(height=350)
                    st.altair_chart(chart_portafoglio, width="stretch")
                else:
                    st.info("Nessun dato registrato nell'intervallo temporale o per la strategia selezionata.")
            else:
                st.info("Nessun dato registrato nello Storico Portafoglio. Il bot inizierà a popolarlo a breve.")
                
        # Mostriamo il cumulativo solo se NON stiamo guardando solo le posizioni aperte
        if tipo_operazioni != "Posizioni Aperte":
            st.divider()
            st.subheader("P/L Cumulativo (Solo Operazioni Chiuse)")
            
            # Filtra lo storico in base a strategia e data di acquisto selezionate
            df_stats_filtered = df_stats.copy() if not df_stats.empty else pd.DataFrame()
            
            # Filtra per strategia
            if strategia_filtro != "Tutte" and not df_stats_filtered.empty and 'Strategia' in df_stats_filtered.columns:
                df_stats_filtered = df_stats_filtered[df_stats_filtered['Strategia'].apply(match_strategia)]
                
            # Filtra per data
            if not df_stats_filtered.empty and date_range:
                df_stats_filtered['Data_Ora_parsed'] = pd.to_datetime(df_stats_filtered['Data_Ora'], errors='coerce')
                df_stats_filtered = df_stats_filtered.dropna(subset=['Data_Ora_parsed'])
                if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
                    start_date, end_date = date_range
                    start_ts = pd.Timestamp(start_date)
                    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                    df_stats_filtered = df_stats_filtered[
                        (df_stats_filtered['Data_Ora_parsed'] >= start_ts) & 
                        (df_stats_filtered['Data_Ora_parsed'] <= end_ts)
                    ]
                elif isinstance(date_range, (tuple, list)) and len(date_range) == 1:
                    start_ts = pd.Timestamp(date_range[0])
                    df_stats_filtered = df_stats_filtered[df_stats_filtered['Data_Ora_parsed'] >= start_ts]

            # Grafico andamento cumulativo con Altair Premium
            if not df_stats_filtered.empty and 'Data_Ora_Uscita' in df_stats_filtered.columns:
                df_sort = df_stats_filtered.sort_values(by='Data_Ora_Uscita').copy()
                df_sort['Cumulativo'] = df_sort['P_L_Perc'].cumsum()
                
                chart_cum = alt.Chart(df_sort).mark_line(point=True, color='#2ecc71').encode(
                    x=alt.X('Data_Ora_Uscita:T', title='Data di Chiusura'),
                    y=alt.Y('Cumulativo:Q', title='P&L Cumulativo %'),
                    tooltip=['Data_Ora_Uscita', 'Ticker', 'P_L_Perc', 'Cumulativo']
                ).properties(height=350)
                st.altair_chart(chart_cum, width="stretch")
            else:
                st.warning("Nessuna operazione chiusa trovata in questo intervallo di date o storico vuoto.")
            
        st.divider()
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("Profitto Medio per Suggeritore")
            if 'Suggeritore' in df_filtered.columns:
                df_sugg_clean = df_filtered[df_filtered['Suggeritore'].notna() & (df_filtered['Suggeritore'] != '')]
                if not df_sugg_clean.empty:
                    df_sugg = df_sugg_clean.groupby('Suggeritore')['P_L_Perc'].mean().reset_index()
                    if not df_sugg.empty:
                        chart_sugg = alt.Chart(df_sugg).mark_bar().encode(
                            x=alt.X('Suggeritore', sort='-y', title='Chi ha dato il segnale?'),
                            y=alt.Y('P_L_Perc', title='Profitto/Perdita Media %'),
                            color=alt.condition(alt.datum.P_L_Perc > 0, alt.value('#2ecc71'), alt.value('#e74c3c')),
                            tooltip=['Suggeritore', alt.Tooltip('P_L_Perc', format='.2f')]
                        ).properties(height=300)
                        st.altair_chart(chart_sugg, width="stretch")
                    else:
                        st.info("Nessun suggeritore con performance calcolabili.")
                else:
                    st.info("Nessun suggeritore inserito nelle operazioni.")
        
        with col_g2:
            st.subheader("Performance per Modello")
            if 'Modello' in df_filtered.columns:
                df_mod_clean = df_filtered[df_filtered['Modello'].notna() & (df_filtered['Modello'] != '')]
                if not df_mod_clean.empty:
                    df_mod = df_mod_clean.groupby('Modello')['P_L_Perc'].mean().reset_index()
                    if not df_mod.empty:
                        chart_mod = alt.Chart(df_mod).mark_bar().encode(
                            x=alt.X('Modello', sort='-y', title='Strategia usata'),
                            y=alt.Y('P_L_Perc', title='Profitto/Perdita Media %'),
                            color=alt.condition(alt.datum.P_L_Perc > 0, alt.value('#2ecc71'), alt.value('#e74c3c')),
                            tooltip=['Modello', alt.Tooltip('P_L_Perc', format='.2f')]
                        ).properties(height=300)
                        st.altair_chart(chart_mod, width="stretch")
                    else:
                        st.info("Nessun modello con performance calcolabili.")
                else:
                    st.info("Nessun modello inserito nelle operazioni.")
