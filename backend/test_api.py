import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
symbol = "AAPL"
res = requests.get("https://api.twelvedata.com/quote", params={"symbol": symbol, "apikey": API_KEY})
print(res.json())
