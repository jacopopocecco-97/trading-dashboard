import time
import os
import toml
import gspread
import yfinance as yf
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# Configurazione costanti
SHEET_KEY = "1Y4qUgzJvrF6IE0Bv9DQzAo-SOkHqsx2CHQW-fBEoR3w"
WORKSHEET_ATTIVE = "Posizioni_Attive"
WORKSHEET_STORICO = "Storico"
WORKSHEET_PREZZI = "Storico_Prezzi"
WORKSHEET_PENDING = "Ordini_Pending"
WORKSHEET_PORTAFOGLIO = "Storico_Portafoglio"

def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Se stiamo girando in locale usiamo secrets.toml
    if os.path.exists(".streamlit/secrets.toml"):
        with open(".streamlit/secrets.toml", "r") as f:
            secrets = toml.load(f)
        skey = secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(skey, scopes=scopes)
    else:
        # Su Render/Cloud, usiamo la variabile d'ambiente
        if "GCP_CREDENTIALS" in os.environ:
            # Leggiamo il testo TOML dalla variabile d'ambiente
            skey_full = toml.loads(os.environ["GCP_CREDENTIALS"])
            skey = skey_full["gcp_service_account"]
            credentials = Credentials.from_service_account_info(skey, scopes=scopes)
        else:
            raise FileNotFoundError("Credenziali non trovate! Configura secrets.toml o GCP_CREDENTIALS.")
        
    client = gspread.authorize(credentials)
    return client

def get_current_price(ticker):
    try:
        ticker_obj = yf.Ticker(ticker)
        # Scarica l'ultimo minuto disponibile includendo pre e post market
        data = ticker_obj.history(period="1d", interval="1m", prepost=True)
        if not data.empty:
            return data['Close'].iloc[-1]
        # Fallback se non ci sono dati intraday
        return ticker_obj.fast_info.last_price
    except Exception:
        return None

def is_market_open(ticker):
    """
    Verifica se il mercato è aperto controllando se ci sono stati scambi 
    (dati yfinance) negli ultimi 30 minuti.
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        data = ticker_obj.history(period="1d", interval="1m", prepost=True)
        if not data.empty:
            last_time_utc = data.index[-1].tz_convert('UTC')
            now_utc = pd.Timestamp.now('UTC')
            diff_minutes = (now_utc - last_time_utc).total_seconds() / 60
            return diff_minutes < 30
        return False # Fallback prudenziale, se non abbiamo dati assumiamo chiuso
    except Exception:
        return False

def get_stock_currency(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        return ticker.info.get("currency", "USD")
    except:
        return "USD"

def get_conversion_rate(from_curr, to_curr):
    if from_curr == to_curr:
        return 1.0
    try:
        ticker = f"{from_curr}{to_curr}=X"
        return get_current_price(ticker)
    except:
        return 1.0

def to_float_safe(val):
    if isinstance(val, str):
        val = val.replace(',', '.')
    try:
        return float(val)
    except:
        return 0.0

def run_bot():
    print("🤖 Trading Bot avviato e in ascolto 24/7...")
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_KEY)
    
    ws_attive = sheet.worksheet(WORKSHEET_ATTIVE)
    ws_storico = sheet.worksheet(WORKSHEET_STORICO)
    ws_prezzi = sheet.worksheet(WORKSHEET_PREZZI)
    ws_pending = sheet.worksheet(WORKSHEET_PENDING)
    ws_portafoglio = sheet.worksheet(WORKSHEET_PORTAFOGLIO)
    
    last_price_log_time = datetime.min
    last_portfolio_log_time = datetime.min
    
    while True:
        try:
            now = datetime.now()
            print(f"[{now.strftime('%H:%M:%S')}] Scansione mercato in corso...")
            
            # --- GESTIONE ORDINI PENDING ---
            dati_pending = ws_pending.get_all_records(numericise_ignore=['all'])
            if dati_pending:
                df_pending = pd.DataFrame(dati_pending)
                righe_pending_da_spostare = []
                
                for index, row in df_pending.iterrows():
                    ticker = row.get("Ticker", "")
                    p_min = to_float_safe(row.get("Prezzo_Min", 0))
                    p_max = to_float_safe(row.get("Prezzo_Max", 0))
                    
                    prezzo_reale_borsa = get_current_price(ticker)
                    if prezzo_reale_borsa is None:
                        continue
                        
                    # Controlla se il prezzo attuale soddisfa i limiti impostati
                    condizione_prezzo = False
                    if p_min > 0 and p_max > 0:
                        condizione_prezzo = (p_min <= prezzo_reale_borsa <= p_max)
                    elif p_min > 0:
                        condizione_prezzo = (prezzo_reale_borsa >= p_min)
                    elif p_max > 0:
                        condizione_prezzo = (prezzo_reale_borsa <= p_max)
                        
                    if condizione_prezzo:
                        # Verifica se il mercato è effettivamente aperto
                        if not is_market_open(ticker):
                            continue
                            
                        range_str = f"[{p_min}, {p_max}]" if (p_min > 0 and p_max > 0) else (f">= {p_min}" if p_min > 0 else f"<= {p_max}")
                        print(f"✅ ORDINE PENDING ESEGUITO per {ticker}! Prezzo attuale {prezzo_reale_borsa:.2f} soddisfatto dalla condizione {range_str}")
                        valuta = row.get("Valuta", "USD")
                        sl = to_float_safe(row.get("Stop_Loss", 0))
                        tp = to_float_safe(row.get("Take_Profit", 0))
                        sugg = row.get("Suggeritore", "")
                        modello = row.get("Modello", "")
                        strategia = row.get("Strategia", "")
                        orizzonte = row.get("Orizzonte_Giorni", "")
                        
                        tasso = get_conversion_rate(get_stock_currency(ticker), valuta)
                        prezzo_entrata_convertito = prezzo_reale_borsa * tasso
                        
                        nuova_riga_attive = [ticker, round(prezzo_entrata_convertito, 2), valuta, sl, tp, now.strftime("%Y-%m-%d %H:%M:%S"), sugg, modello, strategia, orizzonte]
                        righe_pending_da_spostare.append({"row_index": index + 2, "dati_attive": nuova_riga_attive})
                        
                if righe_pending_da_spostare:
                    righe_pending_da_spostare.sort(key=lambda x: x["row_index"], reverse=True)
                    for riga in righe_pending_da_spostare:
                        ws_attive.append_row(riga["dati_attive"], value_input_option='USER_ENTERED')
                        ws_pending.delete_rows(riga["row_index"])
                    print(f"Spostati {len(righe_pending_da_spostare)} ordini pending in posizioni attive.")

            # --- GESTIONE POSIZIONI ATTIVE ---
            dati_attive = ws_attive.get_all_records(numericise_ignore=['all'])
            df_attive = pd.DataFrame(dati_attive) if dati_attive else pd.DataFrame()
            
            righe_da_chiudere = []
            righe_prezzi_da_loggare = []
            tickers_loggati_questo_giro = set() # Per evitare duplicati se ci sono 2 posizioni uguali
            totale_open_pnl = 0.0
            
            for index, row in df_attive.iterrows():
                ticker = row.get("Ticker", "")
                prezzo_ingresso = to_float_safe(row.get("Prezzo_Entrata", 0))
                sl = to_float_safe(row.get("Stop_Loss", 0))
                tp = to_float_safe(row.get("Take_Profit", 0))
                valuta_inserita = row.get("Valuta_Entrata", "USD")
                suggeritore = row.get("Suggeritore", "")
                modello = row.get("Modello", "")
                strategia = row.get("Strategia", "")
                orizzonte = row.get("Orizzonte_Giorni", "")
                
                prezzo_reale_borsa = get_current_price(ticker)
                if prezzo_reale_borsa is None:
                    continue
                    
                valuta_borsa = get_stock_currency(ticker)
                tasso = get_conversion_rate(valuta_borsa, valuta_inserita)
                prezzo_corrente_convertito = prezzo_reale_borsa * tasso
                
                # Prepara i dati per il log storico (solo se non lo abbiamo già loggato in questo minuto)
                if ticker and ticker not in tickers_loggati_questo_giro:
                    righe_prezzi_da_loggare.append([ticker, round(prezzo_corrente_convertito, 2), now.strftime("%Y-%m-%d %H:%M:%S")])
                    tickers_loggati_questo_giro.add(ticker)
                
                pnl = 0.0
                if prezzo_ingresso > 0:
                    pnl = ((prezzo_corrente_convertito - prezzo_ingresso) / prezzo_ingresso) * 100
                totale_open_pnl += pnl
                
                # Check Stop Loss / Take Profit
                if sl > 0 and prezzo_corrente_convertito <= sl:
                    print(f"⚠️ STOP LOSS HIT per {ticker}! Prezzo: {prezzo_corrente_convertito:.2f}")
                    righe_da_chiudere.append({
                        "row_index": index + 2,
                        "dati": [ticker, prezzo_ingresso, round(prezzo_corrente_convertito, 2), valuta_inserita, round(pnl, 2), "SL", row.get("Data_Ora", ""), now.strftime("%Y-%m-%d %H:%M:%S"), suggeritore, modello, strategia, orizzonte]
                    })
                elif tp > 0 and prezzo_corrente_convertito >= tp:
                    print(f"✅ TAKE PROFIT HIT per {ticker}! Prezzo: {prezzo_corrente_convertito:.2f}")
                    righe_da_chiudere.append({
                        "row_index": index + 2,
                        "dati": [ticker, prezzo_ingresso, round(prezzo_corrente_convertito, 2), valuta_inserita, round(pnl, 2), "TP", row.get("Data_Ora", ""), now.strftime("%Y-%m-%d %H:%M:%S"), suggeritore, modello, strategia, orizzonte]
                    })
            
            # Esegui la chiusura se necessario
            if righe_da_chiudere:
                # Ordinare per rimuovere dal basso in alto (evita sfasamenti degli indici)
                righe_da_chiudere.sort(key=lambda x: x["row_index"], reverse=True)
                for riga in righe_da_chiudere:
                    ws_storico.append_row(riga["dati"], value_input_option='USER_ENTERED')
                    ws_attive.delete_rows(riga["row_index"])
                print(f"Spostate {len(righe_da_chiudere)} posizioni nello storico.")

            # Log storico prezzi (ogni 5 minuti = 300 secondi per evitare limiti API Google)
            if (now - last_price_log_time).total_seconds() >= 300:
                if righe_prezzi_da_loggare:
                    ws_prezzi.append_rows(righe_prezzi_da_loggare, value_input_option='USER_ENTERED')
                    print(f"Salvato storico prezzi per {len(righe_prezzi_da_loggare)} ticker.")
                    last_price_log_time = now
                    
            # --- LOG PORTAFOGLIO P&L ---
            # Ogni 10 minuti (600 secondi)
            if (now - last_portfolio_log_time).total_seconds() >= 600:
                dati_storico = ws_storico.get_all_records(numericise_ignore=['all'])
                totale_closed_pnl = 0.0
                if dati_storico:
                    df_storico = pd.DataFrame(dati_storico)
                    df_storico['P_L_Perc'] = df_storico.get('P_L_Perc', pd.Series([0]*len(df_storico))).apply(to_float_safe)
                    totale_closed_pnl = df_storico['P_L_Perc'].sum()
                
                totale_complessivo = totale_open_pnl + totale_closed_pnl
                
                riga_portafoglio = [now.strftime("%Y-%m-%d %H:%M:%S"), round(totale_open_pnl, 2), round(totale_closed_pnl, 2), round(totale_complessivo, 2)]
                ws_portafoglio.append_row(riga_portafoglio, value_input_option='USER_ENTERED')
                print(f"Salvato storico portafoglio. Complessivo: {totale_complessivo:.2f}%")
                last_portfolio_log_time = now
            
        except Exception as e:
            print(f"❌ Errore durante il ciclo del bot: {e}")
            
        # Attesa di 60 secondi spaccati prima del prossimo giro
        time.sleep(60)

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")
        
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

def start_server():
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
    server.serve_forever()

if __name__ == "__main__":
    # Avvia un mini server web in un thread separato (necessario per host come Render)
    threading.Thread(target=start_server, daemon=True).start()
    # Avvia il bot vero e proprio
    run_bot()
