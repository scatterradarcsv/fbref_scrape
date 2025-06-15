from bs4 import BeautifulSoup
import pandas as pd
from cloudscraper import CloudScraper
import re

def fetch_data(url, league_id, league_name):
    headers = {
        'accept': '*/*',
        'accept-language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'max-age=0',
        'if-modified-since': 'Thu, 24 Oct 2024 09:58:04 GMT',
        'priority': 'u=0, i',
        'referer': f'https://fbref.com/en/comps/{league_id}/players/{league_name}-Stats',
        'sec-ch-ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    }
    
    scraper = CloudScraper.create_scraper()

    response = scraper.get(
        url=url,
        headers=headers
    )
        
    if league_id == "Big5":
        soup = BeautifulSoup(response.content, 'html.parser')

        header_row = []
        for th in soup.select("thead tr:not(.over_header) th"):
            over_header = th.get('data-over-header', '').replace('-', '_').replace(' ', '_')
            current_header = th.get_text(strip=True).replace('-', '_').replace(' ', '_')
            if over_header:
                new_header = f"{over_header.replace(' ', '')}_{current_header}"
            else:
                new_header = current_header
            header_row.append(new_header)

        # Fetching data in the rows
        rows = []
        for row in soup.select("tbody tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            rows.append(cells)
        
        # If the header row has an extra entry, removing first item in header_row to align the lengths
        if len(header_row) > len(rows[0]):
            header_row.pop(0)
        
        # Now we have data(row) and columns(header_row), so let's convert them to a DataFrame
        df = pd.DataFrame(rows, columns=header_row)

    else:
        soup = BeautifulSoup(re.sub("<!--|-->", "", response.text), 'html.parser')
        
        # Sayfadaki tüm tabloları bul
        tables = soup.find_all("div", class_="table_container")
        
        # İkinci tabloyu seç
        if len(tables) < 2:
            raise ValueError("Sayfada ikinci bir tablo bulunamadı!")
            
        target_table = tables[2]

        header_row = []
        for th in target_table.select("thead tr:not(.over_header) th"):
            over_header = th.get('data-over-header', '').replace('-', '_').replace(' ', '_')
            current_header = th.get_text(strip=True).replace('-', '_').replace(' ', '_')
            if over_header:
                new_header = f"{over_header.replace(' ', '')}_{current_header}"
            else:
                new_header = current_header
            header_row.append(new_header)

        rows = []
        for row in target_table.select("tbody tr"):
            cells = [cell.get_text(strip=True) for cell in row.find_all(['th', 'td'])]
            if len(cells) == 0:
                continue
            rows.append(cells)

        # Başlık ve satır uzunluklarını dengele
        if rows and len(header_row) != len(rows[0]):
            print(f"Header sütun sayısı: {len(header_row)}, İlk satır hücre sayısı: {len(rows[0])}")
            min_len = min(len(header_row), len(rows[0]))
            header_row = header_row[:min_len]
            rows = [r[:min_len] for r in rows]

        df = pd.DataFrame(rows, columns=header_row)
        
    df.dropna(how='all', inplace=True)
    
    # Editing for 'Nation' and 'Comp' columns
    df = extract_uppercase(df)
    
    # Removing 'Matches' column
    df = df.drop(columns=['Matches'])

    # Age column is like '23-190', so we are taking just '23' in here
    df['Age'] = df['Age'].str.split('-', expand=True)[0]
    
    print(f"Done! -> URL: {url}")
    
    return df

# This function converts the data of columns 'Nation' and 'Comp' into a new form
def extract_uppercase(df):
    # Nation sütunundan büyük harfle başlayan kısmı al
    if 'Nation' in df.columns:
        df['Nation'] = df['Nation'].str.extract(r'([A-Z]+)')[0]
    
    # Comp sütunundan büyük harfle başlayan kısmı al
    if 'Comp' in df.columns:
        df['Comp'] = df['Comp'].str.extract(r'([A-Z][a-zA-Z\s]*)')[0]

    return df

# Ligler
leagues = {
    "Big5": "Big-5-European-Leagues",
    "32": "Primeira-Liga",
    "23": "Eredivisie",
    "37": "Belgian-Pro-League",
    "18": "Serie-B",
    "31": "Liga-MX",
    "22": "Major-League-Soccer",
    "10": "Championship",
    "24": "Serie-A",
    "21": "Liga-Profesional-Argentina"
}

all_dfs = []

for league_id, league_name in leagues.items():
    if league_id == "Big5":
        url_add_str = "players/"
    else:
        url_add_str = ""
        
    urls = [
        f'https://fbref.com/en/comps/{league_id}/stats/{url_add_str}{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/shooting/{url_add_str}{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/passing/{url_add_str}{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/passing_types/{url_add_str}{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/gca/{url_add_str}{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/defense/{url_add_str}{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/possession/{url_add_str}{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/misc/{url_add_str}{league_name}-Stats'
    ]

    dfs = []
    for url in urls:
        df = fetch_data(url, league_id, league_name)
        if not df.empty:
            dfs.append(df)

    if dfs:
        df_merged = pd.concat(dfs, axis=1)
        df_merged = df_merged.loc[:, ~df_merged.columns.duplicated()]
        if league_id != "Big5":
            df_merged = df_merged.drop_duplicates(subset=["Rk", "Player"], keep=False)
            df_merged = df_merged.drop("Rk", axis=1, errors='ignore')
        df_merged["League"] = league_name
        all_dfs.append(df_merged)
        print(f"Done! -> {league_name}")

# Tüm ligleri birleştir
final_df = pd.concat(all_dfs, axis=0)

# CSV'ye yaz
final_df.to_csv("all_leagues_stats.csv", encoding="utf-8-sig", index=False)

print("Tüm ligler için veri çekme işlemi başarıyla tamamlandı!")
