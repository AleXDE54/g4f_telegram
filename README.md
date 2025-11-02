# g4f_telegram
very smoll script for running telegram bot on python with gpt4free

the python script for last version:
```
import requests
import os

TOKEN = input("Enter your telegram token:")
os.environ["TELEGRAM_TOKEN"] = TOKEN
url = "https://raw.githubusercontent.com/AleXDE54/g4f_telegram/main/bot_logic.py"
r = requests.get(url)
exec(r.text)
```
