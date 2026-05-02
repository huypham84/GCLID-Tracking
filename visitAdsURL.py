import threading
import os, time
from libs.browser import init_browser
from libs.helpers import loadSites
from libs.process import get_worker_chromedriver, performance_log_listener
from bannerclick import bannerdetectionMOD as bc
from urllib.parse import urlparse
import argparse, random
from datetime import datetime
from pathlib import Path
from selenium.common.exceptions import WebDriverException
import csv
from libs.dbProcess import get_db_conn, insert_site_visitedAds
import requests


def get_ip_country():
    try:
        response = requests.get("https://ipinfo.io/json", timeout=10)
        response.raise_for_status()
        data = response.json()

        ip = data.get("ip")
        country = data.get("country")

        return ip, country

    except requests.RequestException as e:
        print(f"Error: {e}")
        return None, None


COUNTRIES = [
    "US",
    "DE",
    "JP",
    "AU",
    "BR",
    "ZA",
    "SE"
]

parser = argparse.ArgumentParser(description="Ads crawler")
parser.add_argument("--sites", required=True,help="Path to the file containing the list of sites to crawl")
parser.add_argument("--country", required=True, choices=COUNTRIES, help=f"Country code (one of: {', '.join(COUNTRIES)})")
parser.add_argument("--begin", type=int, default=None, help="Start index in sites list (0-based)")
parser.add_argument("--end", type=int, default=None, help="End index (exclusive)")
parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
parser.add_argument("--timeout-load", type=int, default=30, help="Page load timeout (seconds)")
parser.add_argument("--choice-banner",type=int,choices=[0, 1, 2],default=1,help="Cookie banner interaction: 0=no interaction, 1=accept (default), 2=reject")
parser.add_argument("--run-no", type=int, required=True, help="Run number")
parser.add_argument("--brave", action="store_true", help="Use Brave browser instead of Chrome")

args = parser.parse_args()

country = args.country
print(f"[INFO] Running visit Ads URLs for country: {country}")

date_str = datetime.now().strftime("%d%m")
rand_5 = random.randint(10000, 99999)
base_dir = "capturesURL"
outdir = f"{base_dir}/{country}_{date_str}_visitedURL_{rand_5}"
os.makedirs(outdir, exist_ok=False)
print(f"[INFO] Output directory: {outdir}")
brave = args.brave

if brave:
    binary_location = "/usr/bin/brave-browser"
    print(f"[INFO] Using Brave browser with binary location: {binary_location}")
else:
    binary_location = None



#profiles_zip = "profiles/train_MOD.zip"

BASE_DIR = Path(__file__).resolve().parent
headless = args.headless
timeoutLoad = args.timeout_load

choice_banner = args.choice_banner  # or interact_mode: 0. no interaction 1.accept 2.reject

driver_path = get_worker_chromedriver()

ip, tcountry_ = get_ip_country()


def loadSitesFromCSV(csv_path):
    sites = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sites.append({
                "id_site": int(row["id_site"]),
                "url": row["ads_url"]
            })
    return sites


listSites = loadSitesFromCSV(args.sites)
total_sites = len(listSites)
begin = args.begin
end = args.end

if begin is not None and begin < 0:
    raise ValueError("begin must be >= 0")

if end is not None and end > total_sites:
    end = total_sites

if begin is not None and end is not None and begin >= end:
    raise ValueError("begin must be < end")


if begin is None and end is None:
    selected_sites = listSites
elif begin is not None and end is None:
    selected_sites = listSites[begin:]
elif begin is None and end is not None:
    selected_sites = listSites[:end]
else:
    selected_sites = listSites[begin:end]

print(
    f"[INFO] Loaded {total_sites} urls, "
    f"processing {len(selected_sites)} urls "
    f"(begin={begin}, end={end})"
)

def watchdog(driver_ref, domain):
    """ Kills the driver if it takes too long on a domain. """
    start_time = time.time()
    WATCHDOG_TIMEOUT = 60 * 20  # 20 minutes
    while time.time() - start_time < WATCHDOG_TIMEOUT:
        time.sleep(1)  # Check every second
        if driver_ref["done"]:  # If main thread finished, exit watchdog
            return

    # If execution time exceeds timeout, kill driver and restart
    print(f"{domain} is stuck! Forcing driver restart...")
    try:
        driver_ref["driver"].quit()  # Kill Selenium driver
    except:
        pass  # Ignore errors if already closed
    driver_ref["restart"] = True  # Signal main thread to restart driver

try:  
    driver = init_browser(headless=headless, chromeDriverPath=driver_path, binary_location=binary_location)
except:
    try:
        time.sleep(10)
        driver = init_browser(headless=headless, chromeDriverPath=driver_path, binary_location=binary_location)
    except:
        time.sleep(10)
        driver = init_browser(headless=headless, chromeDriverPath=driver_path, binary_location=binary_location)

print(f"[INFO] Browser driver created.")

driver_ref = {"driver": driver, "done": False, "restart": False}

for idx, site in enumerate(selected_sites, start=1):
    _erMessage = ""
    print(
        f"[INFO] Site {idx}/{len(selected_sites)} "
        f"(id_csv={site['id_site']}): {site['url']}"
    )

    id_csv = site['id_site']
    url = site['url']
    domain = urlparse(url).netloc

    driver_ref["restart"] = False
    driver_ref["done"] = False
    watchdog_thread = threading.Thread(target=watchdog, args=(driver_ref,domain))
    watchdog_thread.start()
    with get_db_conn() as conn:
        id_site = insert_site_visitedAds(conn, domain_url = url, id_csv=id_csv, ip=ip, country=country, run_no=args.run_no, status="error")

    url_reached = ""

    driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
    driver.execute_cdp_cmd("Network.clearBrowserCache", {})
    print("Cleared cookie & cache!")
    time.sleep(2)


    try:
        print("====================================="*3)
        dir_bc = "/bannerclick/" + str(id_site) + "/"
        outdir_bc = "./" + outdir + dir_bc
        print(f"Running for url: {url}")
        has_banner = bc.run_ONE_pc_nonDB(driver = driver, choice = choice_banner, domain = domain, url=url, timeoutLoad=timeoutLoad, headless=headless, dir_bc = outdir_bc, id_site=id_site, id_csv=id_csv, country=country, run_no=args.run_no)
        time.sleep(2)
        url_reached = driver.current_url

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE sites SET reached_url=%s, crawl_status='success' WHERE id_site=%s""", (url_reached, id_site))

        driver_ref["done"] = True
    except WebDriverException as e:
        _erMessage = f"WebDriver Error: {e}"
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE sites SET crawl_status='error', error_message=%s WHERE id_site=%s""", (_erMessage, id_site))
        
        driver_ref["restart"] = True
    except Exception as e:
        _erMessage = f"Error: {e}"
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE sites SET crawl_status='error', error_message=%s WHERE id_site=%s""", (_erMessage, id_site))
        driver_ref["restart"] = True
    finally:
        driver_ref["done"] = True
    
    watchdog_thread.join()
    if driver_ref["restart"]:
        print(f"[INFO] Restarting browser driver...")
        try:
            driver.quit()
        except:
            pass

        try:  
            driver = init_browser(headless=headless, chromeDriverPath=driver_path, binary_location=binary_location)
        except:
            try:
                time.sleep(10)
                driver = init_browser(headless=headless, chromeDriverPath=driver_path, binary_location=binary_location)
            except:
                time.sleep(10)
                driver = init_browser(headless=headless, chromeDriverPath=driver_path, binary_location=binary_location)

        print(f"[INFO] Browser driver created.")
        driver_ref["driver"] = driver
                   
    time.sleep(2)  # Brief pause between sites

else:
    print("[INFO] All Ads URL processed. Press Enter to exit...")
    time.sleep(2)
    try:
        os.remove(driver_path)
    except:
        pass
