"""
Test HistData single month download and parse verification script.
"""

import sys, os, zipfile, requests
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path

url = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/tick-data-quotes/gbpusd/2018/1"
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, 'html.parser')
form = soup.find('form', {'id': 'file_download'}) or soup.find('form')
payload = {inp.get('name'): inp.get('value', '') for inp in form.find_all('input') if inp.get('name')}

post_url = "https://www.histdata.com/get.php"
res = requests.post(post_url, data=payload, headers={'User-Agent': 'Mozilla/5.0', 'Referer': url}, stream=True)

test_zip = Path("scripts/test_gbpusd_201801.zip")
with open(test_zip, "wb") as f:
    for chunk in res.iter_content(chunk_size=1024*1024):
        f.write(chunk)

print("Downloaded test zip size:", test_zip.stat().st_size, "bytes")

with zipfile.ZipFile(test_zip, 'r') as z:
    csv_name = [f for f in z.namelist() if f.endswith('.csv') or f.endswith('.txt')][0]
    with z.open(csv_name) as f:
        line = f.readline().decode('utf-8')
        sep = ';' if ';' in line else ','
        print("Sample line:", line.strip(), "Detected sep:", sep)

    with z.open(csv_name) as f:
        df = pd.read_csv(f, sep=sep, header=None, names=['ts_raw', 'bid', 'ask', 'vol'])
        print("Raw head:\n", df.head(3))
        df['datetime'] = pd.to_datetime(df['ts_raw'], format='%Y%m%d %H%M%S%f', errors='coerce')
        df['mid'] = (df['bid'] + df['ask']) / 2.0
        df = df.dropna(subset=['datetime', 'mid']).set_index('datetime')
        h1 = df['mid'].resample('1h').ohlc().dropna()
        print("Resampled H1 head:\n", h1.head(3))
        print("Total H1 bars in Month 1 2018:", len(h1))

if test_zip.exists():
    test_zip.unlink()
