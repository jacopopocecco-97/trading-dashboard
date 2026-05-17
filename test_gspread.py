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

print("Tentativo di leggere tutti i file condivisi con questo account di servizio...")
try:
    all_sheets = client.openall()
    if not all_sheets:
        print("Il service account non vede NESSUN file. Il file non è stato condiviso correttamente.")
    else:
        print(f"Il service account vede {len(all_sheets)} file(s):")
        for s in all_sheets:
            print(f" - Titolo esatto: '{s.title}' | ID: {s.id}")
except Exception as e:
    print(f"Errore fatale API: {e}")
