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
sheet = client.open_by_key("1Y4qUgzJvrF6IE0Bv9DQzAo-SOkHqsx2CHQW-fBEoR3w")

# Controlla se il foglio esiste già
try:
    ws = sheet.worksheet("Storico_Prezzi")
    print("Il foglio 'Storico_Prezzi' esiste già.")
except gspread.exceptions.WorksheetNotFound:
    print("Creo il nuovo foglio 'Storico_Prezzi'...")
    ws = sheet.add_worksheet(title="Storico_Prezzi", rows="1000", cols="3")
    ws.update('A1:C1', [['Ticker', 'Prezzo', 'Data_Ora']])
    print("Foglio creato con successo e intestazioni aggiunte!")
