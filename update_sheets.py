import gspread
from google.oauth2.service_account import Credentials
import toml

with open(".streamlit/secrets.toml", "r") as f:
    secrets = toml.load(f)

skey = secrets["gcp_service_account"]
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_info(skey, scopes=scopes)
client = gspread.authorize(credentials)

print("Mi sto collegando al tuo Google Sheets...")
# Usa l'ID univoco che abbiamo trovato prima per evitare problemi di spazi nel nome
sheet = client.open_by_key("1Y4qUgzJvrF6IE0Bv9DQzAo-SOkHqsx2CHQW-fBEoR3w")

# Aggiorna Posizioni_Attive
ws_attive = sheet.worksheet("Posizioni_Attive")
headers_attive = ws_attive.row_values(1)
if "Suggeritore" not in headers_attive:
    ws_attive.update_cell(1, len(headers_attive) + 1, "Suggeritore")
    ws_attive.update_cell(1, len(headers_attive) + 2, "Modello")
    print("Aggiunti Suggeritore e Modello in Posizioni_Attive!")
else:
    print("Colonne già presenti in Posizioni_Attive.")

# Aggiorna Storico
ws_storico = sheet.worksheet("Storico")
headers_storico = ws_storico.row_values(1)
if "Suggeritore" not in headers_storico:
    ws_storico.update_cell(1, len(headers_storico) + 1, "Suggeritore")
    ws_storico.update_cell(1, len(headers_storico) + 2, "Modello")
    print("Aggiunti Suggeritore e Modello nello Storico!")
else:
    print("Colonne già presenti in Storico.")

print("Tutto aggiornato con successo su Google Sheets!")
