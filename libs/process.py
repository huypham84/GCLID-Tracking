from anyio import Path
from libs.helpers import is_infinite_scroll_page, scroll_infinite, slow_scroll_page
from libs.captureAds import capture_marked_elements_lite
from libs.browser import init_browser, close_and_delete_profile
from libs.helpers import unzip_profile
from libs.internal import get_internal_links
import os, shutil, random



def get_worker_chromedriver():
    BASE_DIR = Path(__file__).parent.parent
    src = BASE_DIR / "drivers" / "chromedriver146"

    pid = os.getpid() 
    dst_dir = BASE_DIR / "drivers" / "workers"
    dst = dst_dir / f"chromedriver_{pid}"

    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(src, dst)
    os.chmod(dst, 0o755)
    
    print(f"[INFO] Chromedriver path for PID {pid}: {dst}")

    return str(dst)



def performance_log_listener(driver, events, stop_event,
                             after_flag,
                             poll_interval=0.25,
                             max_events=20000):
    import json, time
    from selenium.common.exceptions import WebDriverException

    while not stop_event.is_set():
        if len(events) >= max_events:
            break

        try:
            logs = driver.get_log("performance")
        except WebDriverException:
            break

        for entry in logs:
            if len(events) >= max_events:
                break
            try:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method", "").startswith("Network."):
                    msg["_after"] = after_flag["value"]
                    events.append(msg)
            except Exception:
                continue

        time.sleep(poll_interval)




def stepsEachUrl_lite(driver, url, outdir, timeoutLoad=60, timeoutVisit=60, subpage=False, screenshot=False):
    import time
    print(f"[INFO] Navigating to {url}...")
    if subpage:
        timeoutLoad = timeoutLoad
    else:
        timeoutLoad = timeoutLoad
    driver.set_page_load_timeout(timeoutLoad)

    
    try:
        driver.get(url)
    except:
        driver.execute_script("window.stop();")   # <<< Dừng load
    
    time.sleep(timeoutVisit)  # initial wait for page load

        
    js = """const style = document.createElement('style'); style.innerHTML = `#gateway-content,div[data-testid="gateway-content"] {display: none !important;visibility: hidden !important;opacity: 0 !important;} body {overflow: auto !important;}`;document.head.appendChild(style);"""
    driver.execute_script(js)


    scroll = True

    if scroll:
        if is_infinite_scroll_page(driver):
            print("Page detected as INFINITE SCROLL.")
            scroll_infinite(driver,lite_mode=True)
        else:
            print("Page is NORMAL scroll.")
            slow_scroll_page(driver,lite_mode=True)

    time.sleep(5)
    
    capture_marked_elements_lite(driver, outdir=outdir, screenshot=screenshot)



def runTest_lite(driver, target_url, outdir, max_Pages, timeoutLoad, timeoutVisit, screenshot=False):
    site = target_url.replace("https://", "").replace("http://","").replace("/","_")
    outdir_target = os.path.join(outdir, site)
    os.makedirs(outdir_target, exist_ok=True)

    visited = set()
    try:
        stepsEachUrl_lite(driver, target_url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit, screenshot=screenshot)
        visited.add(driver.current_url)
        pool = get_internal_links(driver, driver.current_url)

        if not pool:
            print("No internal links found.")
            return

        print(f"Found {len(pool)} internal links.")
        random.shuffle(pool)

        for url in pool:
            if len(visited) >= max_Pages:
                break

            if url in visited:
                continue

            print(f"[MASTER] Visiting next URL: {url}")
            try:
                stepsEachUrl_lite(driver, url, outdir_target, timeoutLoad=timeoutLoad, timeoutVisit=timeoutVisit, subpage=True, screenshot=screenshot)
            except Exception as e:
                print(f"[WARN] Failed to process {url}: {e}")

            visited.add(url)
        print(f"Finished visiting {len(visited)} pages.")
    
    except Exception as e:
        print("Error: ",e)


def create_driver(profile_zip, headless, testMac=False):
    from pathlib import Path

    BASE_DIR = Path(__file__).parent.parent
    EXT_PATH = BASE_DIR / "extensions" / "DetectAds"
    EXT_PATH = str(EXT_PATH)
    
    profile_dir = unzip_profile(profile_zip)

    try:
        if testMac:
            driver = init_browser(user_data_dir=profile_dir,headless=headless, extension_unpacked_folder=EXT_PATH)
        else:
            CHROME_DRIVER_PATH = get_worker_chromedriver()
            driver = init_browser(user_data_dir=profile_dir,headless=headless, extension_unpacked_folder=EXT_PATH, chromeDriverPath=CHROME_DRIVER_PATH)
    except:
        if testMac:
            driver = init_browser(user_data_dir=profile_dir,headless=headless, extension_unpacked_folder=EXT_PATH)
        else:
            CHROME_DRIVER_PATH = get_worker_chromedriver()
            driver = init_browser(user_data_dir=profile_dir,headless=headless, extension_unpacked_folder=EXT_PATH, chromeDriverPath=CHROME_DRIVER_PATH)
    
    #driver = init_browser(headless=headless, extension_unpacked_folder="/Users/huypham/AdsCrawler/extensions/DetectAds")
    if testMac:
        return [driver, profile_dir]
    else:
        return [driver, profile_dir, CHROME_DRIVER_PATH]


def get_public_ips():
    import requests
    ipv4 = requests.get("https://api.ipify.org", timeout=5).text
    #ipv6 = requests.get("https://api64.ipify.org", timeout=5).text

    return ipv4
    #return {
    #    "ipv4": ipv4,
    #    "ipv6": ipv6
    #}

