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

def get_worksheet(client, ws_name):
    try:
        # Usiamo l'ID univoco così non importa se cambi il nome o togli gli spazi
        sheet = client.open_by_key("1Y4qUgzJvrF6IE0Bv9DQzAo-SOkHqsx2CHQW-fBEoR3w")
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

def get_stock_currency(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        return info.get("currency", "USD")
    except:
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
                        
                        chart_prezzi = alt.Chart(df_prezzi_ticker).mark_line(point=True, color='#3498db').encode(
                            x=alt.X('Data_Ora:T', title='Data e Ora'),
                            y=alt.Y('Prezzo:Q', title='Prezzo Registrato', scale=alt.Scale(zero=False)),
                            tooltip=['Data_Ora', 'Prezzo']
                        ).properties(height=350)
                        st.altair_chart(chart_prezzi, width="stretch")
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
        
        # Logica orari mercato USA (considerando Pre e After market: 10:00 - 02:00 orario italiano)
        is_weekend = now_rome.weekday() >= 5
        is_closed_hours = now_rome.hour >= 2 and now_rome.hour < 10
        
        if is_weekend or is_closed_hours:
            frase_entrata = "I mercati americani (incluso l'intero pre e after market) in questo momento sono CHIUSI. L'ipotetica entrata a mercato dovrà per forza avvenire al primo giorno utile e alla primissima ora utile della riapertura ufficiale dei mercati."
        else:
            frase_entrata = f"I mercati sono attualmente in contrattazione. L'ipotetica entrata a mercato sarebbe esattamente oggi {oggi_str} alle ore {ora_str}."
        
        prompt_ia = f"""Ricerca almeno 3 titoli a rendimento esplosivo in long da acquistare da rivendere nel giro di qualche giorno massimo qualche settimana. Esponi il rendimento atteso e il rischio sottostante.
Attenzione: in Italia siamo al {oggi_str} ore {ora_str}. Prendi notizie aggiornate e, se disponibili, guardati i valori di pre-market e after-market odierni.
{frase_entrata}
In passato hai selezionato azioni giuste se fossero state prese però 1 o 2 giorni indietro. Non fare questo errore.

IMPORTANTE: Alla fine della tua analisi, DEVI fornire i dati dell'azione che hai scelto per l'investimento ESCLUSIVAMENTE in questo formato JSON, racchiuso in un blocco di codice. Sostituisci i valori ma mantieni rigorosamente questa struttura:
```json
{{
  "ticker": "AAPL",
  "sl": 150.5,
  "tp": 190.0,
  "range_min": 160.0,
  "range_max": 165.0,
  "suggeritore": "Inserisci il tuo nome (es. Gemini o Claude)",
  "modello": "Inserisci la tua versione esatta (es. Gemini 1.5 Pro, Claude 3 Opus)"
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
                    st.success("Dati importati con successo! Scorri giù per cercare il prezzo e confermare.")
                else:
                    st.error("Nessun JSON valido trovato nel testo incollato.")
            except Exception as e:
                st.error(f"Errore nella lettura del JSON: {e}")
                
    st.markdown("---")
    
    ticker_input = st.text_input("Ticker Azione (es. TSLA, AAPL, UCG.MI)", key="form_ticker").upper()
    valuta_input = st.selectbox("Valuta di riferimento per i prezzi", ["USD", "EUR"])
    
    col1, col2 = st.columns(2)
    with col1:
        sl_input = st.number_input("Stop Loss (Prezzo)", min_value=0.0, format="%.2f", step=0.5, key="form_sl")
    with col2:
        tp_input = st.number_input("Take Profit (Prezzo)", min_value=0.0, format="%.2f", step=0.5, key="form_tp")
        
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
                    elif range_min_input > 0 and range_max_input > 0:
                        is_pending = True
                        
                    if is_pending:
                        st.write(f"Vuoi inviare l'ordine ai **PENDING** con range di ingresso [{p_min} - {p_max}], SL a {sl_input} e TP a {tp_input}?")
                        if st.button("⏳ Salva come Ordine Pending"):
                            nuova_riga = [p['ticker'], p_min, p_max, p['valuta'], sl_input, tp_input, data_ora_str, suggeritore_input, modello_input]
                            try:
                                ws_pending.append_row(nuova_riga, value_input_option='USER_ENTERED')
                                st.success(f"Ordine pending su {p['ticker']} aggiunto con successo!")
                                del st.session_state['pending_position']
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore durante il salvataggio su Google Sheets: {e}")
                    else:
                        st.write(f"Vuoi confermare l'apertura **IMMEDIATA** a questo prezzo con SL a {sl_input} e TP a {tp_input}?")
                        if st.button("✅ Conferma e Apri Posizione"):
                            nuova_riga = [p['ticker'], p['prezzo'], p['valuta'], sl_input, tp_input, data_ora_str, suggeritore_input, modello_input]
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
        is_pending = (range_min_input > 0 and range_max_input > 0) or auto_range
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
                        
                    nuova_riga = [ticker_input, p_min, p_max, valuta_input, sl_input, tp_input, data_ora_str, suggeritore_input, modello_input]
                    try:
                        ws_pending.append_row(nuova_riga, value_input_option='USER_ENTERED')
                        st.success(f"Ordine pending su {ticker_input} aggiunto con successo!")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante il salvataggio: {e}")
                else:
                    nuova_riga = [ticker_input, prezzo_input, valuta_input, sl_input, tp_input, data_ora_str, suggeritore_input, modello_input]
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

    # Carichiamo lo storico
    dati_stats = ws_storico.get_all_records(numericise_ignore=['all'])
    df_stats = pd.DataFrame(dati_stats) if dati_stats else pd.DataFrame()
    if not df_stats.empty:
        df_stats['P_L_Perc'] = df_stats.get('P_L_Perc', pd.Series([0]*len(df_stats))).apply(to_float_safe)
        
    # Carichiamo le posizioni aperte dalla dashboard (se esistono)
    df_aperte_stats = pd.DataFrame()
    if 'df_display' in locals() and not df_display.empty and 'P/L %' in df_display.columns:
        df_aperte_stats = df_display[['Ticker', 'P/L %', 'Suggeritore', 'Modello']].copy()
        df_aperte_stats.rename(columns={'P/L %': 'P_L_Perc'}, inplace=True)
        df_aperte_stats = df_aperte_stats.dropna(subset=['P_L_Perc'])
        
    # Unione dei due dataframe
    df_combined = pd.concat([df_stats, df_aperte_stats], ignore_index=True)
    
    if df_combined.empty:
        st.info("Non ci sono operazioni (né attive né chiuse) per poter generare le statistiche.")
    else:
        # Metriche in alto
        totale = len(df_combined)
        vincenti = len(df_combined[df_combined['P_L_Perc'] > 0])
        win_rate = (vincenti / totale * 100) if totale > 0 else 0
        profitto_medio = df_combined[df_combined['P_L_Perc'] > 0]['P_L_Perc'].mean()
        perdita_media = df_combined[df_combined['P_L_Perc'] <= 0]['P_L_Perc'].mean()
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Totale Operazioni (Aperte+Chiuse)", totale)
        col_m2.metric("Win Rate Globale", f"{win_rate:.1f}%")
        col_m3.metric("Profitto Medio (Winner)", f"+{profitto_medio:.2f}%" if pd.notna(profitto_medio) else "0%")
        col_m4.metric("Perdita Media (Loser)", f"{perdita_media:.2f}%" if pd.notna(perdita_media) else "0%")
        
        st.divider()
        st.subheader("Andamento Portafoglio nel Tempo (Incluso Open P&L)")
        st.markdown("Tracciamento reale del controvalore P&L registrato ogni 10 minuti dal bot.")
        if ws_portafoglio:
            dati_portafoglio = ws_portafoglio.get_all_records(numericise_ignore=['all'])
            if dati_portafoglio:
                df_portafoglio = pd.DataFrame(dati_portafoglio)
                df_portafoglio['Data_Ora'] = pd.to_datetime(df_portafoglio['Data_Ora'])
                df_portafoglio['P_L_Complessivo'] = df_portafoglio['P_L_Complessivo'].apply(to_float_safe)
                
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
                    y=alt.Y('P_L_Complessivo:Q', title='P&L Complessivo %', scale=alt.Scale(zero=False)),
                    tooltip=['Data_Ora', 'P_L_Complessivo', 'P_L_Aperto', 'P_L_Chiuso']
                ).properties(height=350)
                st.altair_chart(chart_portafoglio, width="stretch")
            else:
                st.info("Nessun dato registrato nello Storico Portafoglio. Il bot inizierà a popolarlo a breve.")
                
        st.divider()
        st.subheader("P/L Cumulativo (Solo Operazioni Chiuse)")
        
        # Grafico andamento cumulativo
        if 'Data_Ora_Uscita' in df_stats.columns:
            df_sort = df_stats.sort_values(by='Data_Ora_Uscita').copy()
            df_sort['Cumulativo'] = df_sort['P_L_Perc'].cumsum()
            st.line_chart(df_sort.set_index('Data_Ora_Uscita')['Cumulativo'])
        else:
            st.warning("Data Uscita mancante nello storico.")
            
        st.divider()
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("Profitto Medio per Suggeritore")
            if 'Suggeritore' in df_combined.columns:
                df_sugg = df_combined[df_combined['Suggeritore'] != ''].groupby('Suggeritore')['P_L_Perc'].mean().reset_index()
                if not df_sugg.empty:
                    chart_sugg = alt.Chart(df_sugg).mark_bar().encode(
                        x=alt.X('Suggeritore', sort='-y', title='Chi ha dato il segnale?'),
                        y=alt.Y('P_L_Perc', title='Profitto/Perdita Media %'),
                        color=alt.condition(alt.datum.P_L_Perc > 0, alt.value('#2ecc71'), alt.value('#e74c3c'))
                    ).properties(height=300)
                    st.altair_chart(chart_sugg, width="stretch")
                else:
                    st.info("Nessun suggeritore inserito nelle operazioni.")
        
        with col_g2:
            st.subheader("Performance per Modello")
            if 'Modello' in df_combined.columns:
                df_mod = df_combined[df_combined['Modello'] != ''].groupby('Modello')['P_L_Perc'].mean().reset_index()
                if not df_mod.empty:
                    chart_mod = alt.Chart(df_mod).mark_bar().encode(
                        x=alt.X('Modello', sort='-y', title='Strategia usata'),
                        y=alt.Y('P_L_Perc', title='Profitto/Perdita Media %'),
                        color=alt.condition(alt.datum.P_L_Perc > 0, alt.value('#2ecc71'), alt.value('#e74c3c'))
                    ).properties(height=300)
                    st.altair_chart(chart_mod, width="stretch")
                else:
                    st.info("Nessun modello inserito nelle operazioni.")
