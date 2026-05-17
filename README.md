# Dashboard Trading con Streamlit e Google Sheets

Questa è un'applicazione web gratuita per monitorare e gestire posizioni di trading azionario (con Stop Loss e Take Profit automatici simulati).

## Come Configurare il Database (Google Sheets)

1. Vai su Google Sheets e crea un nuovo foglio di calcolo.
2. Nominalo ESATTAMENTE: `TradingDashboard`
3. Crea **quattro fogli** (tabs in basso) e chiamali:
   - `Posizioni_Attive`
   - `Storico`
   - `Ordini_Pending`
   - `Storico_Portafoglio`
4. Nel foglio `Posizioni_Attive`, inserisci questa esatta intestazione (riga 1, da A a H):
   `Ticker` | `Prezzo_Entrata` | `Valuta_Entrata` | `Stop_Loss` | `Take_Profit` | `Data_Ora` | `Suggeritore` | `Modello`
5. Nel foglio `Storico`, inserisci questa esatta intestazione (riga 1, da A a J):
   `Ticker` | `Prezzo_Entrata` | `Prezzo_Uscita` | `Valuta` | `P_L_Perc` | `Causa_Uscita` | `Data_Ora_Entrata` | `Data_Ora_Uscita` | `Suggeritore` | `Modello`
6. Nel foglio `Ordini_Pending`, inserisci questa esatta intestazione (riga 1, da A a I):
   `Ticker` | `Prezzo_Min` | `Prezzo_Max` | `Valuta` | `Stop_Loss` | `Take_Profit` | `Data_Ora` | `Suggeritore` | `Modello`
7. Nel foglio `Storico_Portafoglio`, inserisci questa esatta intestazione (riga 1, da A a D):
   `Data_Ora` | `P_L_Aperto` | `P_L_Chiuso` | `P_L_Complessivo`
## Come Creare le Credenziali Google (Service Account)

1. Vai sulla [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un nuovo progetto.
3. Nel menu di sinistra, vai su **API e servizi > Libreria**. Cerca "Google Sheets API" e "Google Drive API" e **abilita entrambe**.
4. Vai su **API e servizi > Credenziali**. Clicca su "Crea credenziali" e scegli "Account di servizio" (Service Account).
5. Dai un nome (es. `streamlit-trading`) e crea l'account.
6. Clicca sull'account appena creato, vai nella tab "Chiavi" (Keys), clicca su "Aggiungi chiave" > "Crea nuova chiave" e scegli formato **JSON**.
7. Questo scaricherà un file `.json` sul tuo computer. **CUSTODISCILO GELOSAMENTE E NON CARICARLO MAI SU GITHUB!**
8. **IMPORTANTE:** Apri il file `.json` scaricato. Trova il campo `client_email` (es: `qualcosa@tuoprogetto.iam.gserviceaccount.com`).
9. Vai sul tuo file Google Sheets `TradingDashboard` e clicca su "Condividi" in alto a destra. Incolla quell'email e dalle i permessi di **Editor**. Questo permette allo script Python di scriverci!

## Come Pubblicare su Streamlit Cloud (Gratis)

1. Carica questi file (`app.py`, `requirements.txt`, `README.md`) in un tuo repository su **GitHub**. (NON caricare il file JSON).
2. Vai su [Streamlit Community Cloud](https://share.streamlit.io/) e accedi col tuo account GitHub.
3. Clicca su "New app". Scegli il repository, il branch (`main`) e il file (`app.py`).
4. **PRIMA di cliccare su Deploy:** Clicca su "Advanced settings" (Impostazioni avanzate).
5. Nella sezione **Secrets**, dovrai copiare il contenuto del tuo file `.json` seguendo questo formato speciale TOML. Cerca di indentare bene:

```toml
[gcp_service_account]
type = "service_account"
project_id = "IL_TUO_PROJECT_ID"
private_key_id = "LA_TUA_PRIVATE_KEY_ID"
private_key = "LA_TUA_PRIVATE_KEY"
client_email = "LA_TUA_CLIENT_EMAIL"
client_id = "IL_TUO_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "IL_TUO_CERT_URL"
```
*(In pratica, copia i valori dal tuo JSON nei campi corrispondenti, rispettando le virgolette).*

6. Clicca su Save e poi su **Deploy**.
7. La tua app è ora online! Salva il link tra i preferiti o sulla Home del tuo telefono!
