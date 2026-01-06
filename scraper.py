from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import random
from playwright.sync_api import sync_playwright

def fetch_html(url, headers, max_retry=3):
    for attempt in range(1, max_retry + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )

                context = browser.new_context(
                    user_agent=headers["user-agent"],
                    locale="tr-TR",
                    viewport={"width": 1920, "height": 1080}
                )

                page = context.new_page()

                # -------------------------
                # RESOURCE BLOCKING
                # -------------------------
                def block_resources(route):
                    if route.request.resource_type in ["image", "font", "media"]:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", block_resources)

                # -------------------------
                # NAVIGATION
                # -------------------------
                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # -------------------------
                # FBref: COMMENT İÇİNDEKİ TABLOLARI DOM'A ÇIKAR
                # -------------------------
                page.evaluate("""
                () => {
                  const walker = document.createTreeWalker(
                    document,
                    NodeFilter.SHOW_COMMENT,
                    null,
                    false
                  );

                  let node;
                  const toReplace = [];

                  while (node = walker.nextNode()) {
                    if (node.nodeValue && node.nodeValue.includes('table_container')) {
                      toReplace.push(node);
                    }
                  }

                  toReplace.forEach(comment => {
                    const wrapper = document.createElement('div');
                    wrapper.innerHTML = comment.nodeValue;
                    comment.replaceWith(...wrapper.childNodes);
                  });
                }
                """)

                # -------------------------
                # SON TABLE_CONTAINER GERÇEKTEN GELDİ Mİ?
                # -------------------------
                page.wait_for_function("""
                () => {
                  const tables = document.querySelectorAll('div.table_container');
                  if (!tables.length) return false;
                  const last = tables[tables.length - 1];
                  return last.querySelector('table') !== null;
                }
                """, timeout=20000)

                # küçük settle (CI için)
                page.wait_for_timeout(1000)

                html = page.content()

                context.close()
                browser.close()

                return html

        except TimeoutError:
            print(f"[{attempt}/{max_retry}] Timeout: {url}")
            time.sleep(2 * attempt)

        except Exception as e:
            print(f"[{attempt}/{max_retry}] Error: {e}")
            time.sleep(2 * attempt)

    raise RuntimeError(f"Page could not be loaded after {max_retry} attempts: {url}")

def fetch_data(url, league_id, league_name, url_add_str):
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-arch': '"x86"',
        'sec-ch-ua-bitness': '"64"',
        'sec-ch-ua-full-version': '"143.0.7499.170"',
        'sec-ch-ua-full-version-list': '"Google Chrome";v="143.0.7499.170", "Chromium";v="143.0.7499.170", "Not A(Brand";v="24.0.0.0"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-model': '""',
        'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua-platform-version': '"19.0.0"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }
    
    html = fetch_html(url, headers)

    if league_id == "Big5":
        soup = BeautifulSoup(html, 'html.parser')

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
        soup = BeautifulSoup(re.sub("<!--|-->", "", html), 'html.parser')
        
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
    df = df.drop(columns=['Matches'], errors='ignore')

    if 'Age' in df.columns:
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
'''
leagues = {
    "Big5": "Big-5-European-Leagues",
    "23": "Eredivisie",
    "32": "Primeira-Liga",
    "37": "Belgian-Pro-League",
    "18": "Serie-B",
    "31": "Liga-MX",
    "22": "Major-League-Soccer",
    "10": "Championship",
    "24": "Serie-A",
    "21": "Liga-Profesional-Argentina"
}
'''

leagues = {
    "Big5": "Big-5-European-Leagues"
}

all_dfs = []

for league_id, league_name in leagues.items():
    if league_id == "Big5":
        url_add_str = "players/"
    else:
        url_add_str = ""

    season_name = "2025-2026"
        
    urls = [
        f'https://fbref.com/en/comps/{league_id}/{season_name}/stats/{url_add_str}{season_name}-{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/{season_name}/shooting/{url_add_str}{season_name}-{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/{season_name}/passing/{url_add_str}{season_name}-{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/{season_name}/passing_types/{url_add_str}{season_name}-{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/{season_name}/gca/{url_add_str}{season_name}-{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/{season_name}/defense/{url_add_str}{season_name}-{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/{season_name}/possession/{url_add_str}{season_name}-{league_name}-Stats',
        f'https://fbref.com/en/comps/{league_id}/{season_name}/misc/{url_add_str}{season_name}-{league_name}-Stats'
    ]

    dfs = []
    for url in urls:
        success = False
        tries = 0
        while not success and tries < 3:
            try:
                df = fetch_data(url, league_id, league_name, url_add_str)
                print(df)
                if not df.empty:
                    dfs.append(df)
                success = True
                time.sleep(random.uniform(3, 6))
            except Exception as e:
                print(f"{url} için hata: {e}. Tekrar deneniyor...")
                time.sleep(random.uniform(3, 6))
                tries += 1

    if dfs:
        df_merged = pd.concat(dfs, axis=1)
        df_merged = df_merged.loc[:, ~df_merged.columns.duplicated()]
        if league_id != "Big5":
            df_merged = df_merged.drop_duplicates(subset=["Rk", "Player"], keep=False)
            df_merged = df_merged.drop("Rk", axis=1, errors='ignore')
            df_merged["Comp"] = league_name
        all_dfs.append(df_merged)
        print(f"Done! -> {league_name}")

# Tüm ligleri birleştir
final_df = pd.concat(all_dfs, axis=0)

# CSV'ye yaz
final_df.to_csv("all_leagues_stats_25_26.csv", encoding="utf-8-sig", index=False)

print("Tüm ligler için veri çekme işlemi başarıyla tamamlandı!")
