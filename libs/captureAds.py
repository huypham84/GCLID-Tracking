from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, NoSuchFrameException
from selenium.webdriver.common.keys import Keys
import pyperclip

from libs.dbProcess import insert_ads_element, insert_ads_information



MARKER = ".adblocked-marker, .acceptablead-marker, .possiblead-marker, .adnetwork-marker"

import time
import json


from urllib.parse import urlparse


import requests, re
from bs4 import BeautifulSoup


def get_taboola_sponsor_name(driver, ad_element):
    js = """
    var el = arguments[0];

    var brandEl = el.querySelector('.branding-inner.inline-branding');
    if (brandEl) {
        return brandEl.textContent.trim();
    }

    var ariaEl = el.querySelector('[aria-label*="Taboola advertising section"]');
    if (ariaEl) {
        return ariaEl.textContent.trim();
    }

    return null;
    """
    try:
        return driver.execute_script(js, ad_element)
    except Exception as e:
        #print("[WARN] Failed to extract Taboola sponsor:", e)
        return None



def fetch_taboola_why_this_ad(url, timeout=15):

    result = ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")


    main_div = soup.select_one("div.main")
    if main_div:
        result = " ".join(main_div.stripped_strings)


    why_div = soup.select_one("div.why-content")
    if why_div:
        result = result + ". " + " ".join(why_div.stripped_strings)


    return result


# ========= START GET WHY THIS ADS ================================
def get_html_soup(url: str, timeout: int = 15) -> BeautifulSoup:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    return BeautifulSoup(resp.text, "html.parser")

def extract_by_label(soup, label_text):
    label_text = label_text.lower()

    for div in soup.find_all("div"):
        text = div.get_text(strip=True).lower()

        if text == label_text:
            parent = div.parent
            if not parent:
                continue

            # value thường nằm trong div kế tiếp
            siblings = parent.find_all("div", recursive=False)
            for sib in siblings:
                if sib is not div:
                    return sib.get_text(strip=True)

    return None

def extract_why_this_ad(html):
    soup = BeautifulSoup(html, "html.parser")

    reasons = []

    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True).lower() == "why this ad?":
            ul = h2.find_next("ul")
            if not ul:
                return []

            for li in ul.find_all("li"):
                reasons.append(li.get_text(strip=True))
            break

    return reasons


def extract_advertiser_location(html):
    soup = BeautifulSoup(html, "html.parser")

    advertiser_raw = extract_by_label(soup, "advertiser")
    location = extract_by_label(soup, "location")

    advertiser = None
    if advertiser_raw:
        advertiser = re.sub(r"paid for by", "", advertiser_raw, flags=re.I).strip()

    return {
        "advertiser": advertiser,
        "location": location
    }



def extract_see_more_ads(html):
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        if "see more ads" in a.get_text(strip=True).lower():
            return a["href"]

    return None



def extract_google_why_this_ad(html, url):
    soup = BeautifulSoup(html, "html.parser")

    advertiser_raw = extract_by_label(soup, "advertiser")
    location = extract_by_label(soup, "location")

    advertiser = None
    if advertiser_raw:
        advertiser = advertiser_raw.replace("Paid for by", "").strip()

    reasons = extract_why_this_ad(html)
    see_more = extract_see_more_ads(html)

    return {
        "adds_info_url": url,
        "advertiser": advertiser,
        "location": location,
        "why_this_ad": reasons,
        "see_more_ads_url": see_more
    }

# ========= END GET WHY THIS ADS ================================


def extract_ad_url_without_click(webdriver, ad_element):
    found_urls = []

    # Function to execute a script and return links
    def execute_script_and_get_links(script, *args):
        try:
            return webdriver.execute_script(script, *args)
        except Exception as e:
            # print(f"Error executing script: {e}")
            return []

    # Extract links directly within the ad_element
    direct_links_script = """
        var links = [];
        var elements = arguments[0].querySelectorAll('a');
        elements.forEach(function(element) {
            var href = element.href;
            if (href) links.push(href);
        });
        return links;
    """
    direct_links = execute_script_and_get_links(direct_links_script, ad_element)
    found_urls.extend(direct_links)

    # Function to recursively find links within iframes
    def find_links_in_iframes(iframe_elements):
        for iframe in iframe_elements:
            try:
                webdriver.switch_to.frame(iframe)
                # Now that we're inside the iframe, look for links directly in this context
                links_in_iframe = execute_script_and_get_links(
                    """
                    var links = [];
                    document.querySelectorAll('a').forEach(function(element) {
                        var href = element.href;
                        if (href) links.push(href);
                    });
                    return links;
                """
                )
                found_urls.extend(links_in_iframe)

                # Look for nested iframes recursively
                nested_iframes = webdriver.find_elements(By.TAG_NAME, "iframe")
                find_links_in_iframes(nested_iframes)

                webdriver.switch_to.parent_frame()
            except Exception as e:
                # print(f"Error processing iframe: {e}")
                webdriver.switch_to.parent_frame()

    # Start by looking for iframes within the ad_element
    iframes_in_ad = ad_element.find_elements(By.TAG_NAME, "iframe")
    find_links_in_iframes(iframes_in_ad)

    # Ensure we're back at the top-level context after all processing
    webdriver.switch_to.default_content()

    return found_urls



def run_get_e(driver, el):
    print("Get link ")

    result = click_and_capture_full_redirect_chain_e(driver, el)

    print("Opened new tab:", result["opened_new_tab"])

    print("\n[PRE-NAVIGATION CHAIN] (ads / trackers / SSP)")
    for item in result["pre_navigation_chain"]:
        print(f" -> {item['url']}  ({item['type']})")

    print("\n[NAVIGATION CHAIN] (Document redirects)")
    for url in result["navigation_chain"]:
        print(" ->", url)
                    
    print("\nFinal landing:", result["final_landing"])
    print("----")


    print("\n~DEVTOOL [PRE-NAVIGATION CHAIN]")
    for item in result["pre_navigation_chain"]:
        initiator = item.get("initiator", {})
        itype = initiator.get("type", "unknown")
        print(f" -> {item['url']}  [{item['type']}, initiator={itype}]")
                    
    print("----"*10)


def run_Click_and_getLog(driver, el):
    result = click_and_capture_full_redirect_chain(driver, el)

    print("Opened new tab:", result["opened_new_tab"])

    print("\n[PRE-NAVIGATION CHAIN]")
    for item in result["pre_navigation_chain"]:
        print(f" -> {item['url']}  ({item['type']})")

        init = item.get("initiator", {})
        if init:
            print(f"    initiator: {init.get('type')} | {init.get('url')}")

        for frame in item.get("stackTrace", []):
            print(
                f"      at {frame['function']} "
                f"({frame['url']}:{frame['line']}:{frame['column']})"
            )

    print("\n[NAVIGATION CHAIN]")
    for url in result["navigation_chain"]:
        print(" ->", url)

    print("\nFinal landing:", result["final_landing"])
    print("----")


def click_and_capture_full_redirect_chain(
    driver,
    element,
    timeout=10.0,
    pre_click_window=0.3
):
    """
    Capture full ad click chain:
    - PRE-navigation: JS / iframe / SSP / Google Ads / trackers
    - POST-navigation: Document redirect chain
    """

    original_window = driver.current_window_handle
    original_windows = set(driver.window_handles)

    pre_chain = []
    nav_chain = []
    seen_req = set()

    # clear old logs
    driver.get_log("performance")

    click_ts = time.time()

    # CLICK
    element.click()

    # ===========================
    # Phase A — PRE-navigation
    # ===========================
    while time.time() - click_ts < pre_click_window:
        logs = driver.get_log("performance")

        for entry in logs:
            msg = json.loads(entry["message"])["message"]
            if msg.get("method") != "Network.requestWillBeSent":
                continue

            params = msg["params"]
            req = params["request"]
            req_id = params["requestId"]

            if req_id in seen_req:
                continue
            seen_req.add(req_id)

            initiator = params.get("initiator", {})
            stack = initiator.get("stack", {})
            call_frames = stack.get("callFrames", [])

            pre_chain.append({
                "url": req.get("url"),
                "type": params.get("type"),
                "initiator": {
                    "type": initiator.get("type"),
                    "url": initiator.get("url"),
                },
                "stackTrace": [
                    {
                        "function": f.get("functionName"),
                        "url": f.get("url"),
                        "line": f.get("lineNumber"),
                        "column": f.get("columnNumber"),
                    }
                    for f in call_frames[:8]   # giới hạn depth
                ]
            })

        time.sleep(0.005)

    # ===========================
    # Phase B — POST-navigation
    # ===========================
    start = time.time()
    opened_new_tab = False
    target_window = original_window

    while time.time() - start < timeout:
        current_windows = set(driver.window_handles)
        new_windows = current_windows - original_windows

        if new_windows:
            target_window = new_windows.pop()
            driver.switch_to.window(target_window)
            opened_new_tab = True

        logs = driver.get_log("performance")

        for entry in logs:
            msg = json.loads(entry["message"])["message"]
            method = msg.get("method")

            if method == "Network.requestWillBeSent":
                params = msg["params"]
                if params.get("type") == "Document":
                    url = params["request"]["url"]
                    if url not in nav_chain:
                        nav_chain.append(url)

            if method == "Network.responseReceived":
                params = msg["params"]
                if params.get("type") == "Document":
                    resp = params["response"]
                    if resp.get("status") == 200:
                        final_url = resp.get("url")
                        if final_url not in nav_chain:
                            nav_chain.append(final_url)

                        if opened_new_tab:
                            driver.close()
                            driver.switch_to.window(original_window)

                        return {
                            "pre_navigation_chain": pre_chain,
                            "navigation_chain": nav_chain,
                            "final_landing": final_url,
                            "opened_new_tab": opened_new_tab
                        }

        time.sleep(0.01)

    # fallback
    if opened_new_tab:
        driver.close()
        driver.switch_to.window(original_window)

    return {
        "pre_navigation_chain": pre_chain,
        "navigation_chain": nav_chain,
        "final_landing": nav_chain[-1] if nav_chain else None,
        "opened_new_tab": opened_new_tab
    }


def click_and_capture_full_redirect_chain_e(
    driver,
    element,
    timeout=10.0,
    pre_click_window=0.3   # 300ms cho Google Ads click
):
    """
    Capture full ad click chain:
    - PRE-navigation: Google / SSP click (iframe, XHR, Image, Fetch)
    - POST-navigation: Document redirect chain to final landing
    """

    original_window = driver.current_window_handle
    original_windows = set(driver.window_handles)

    pre_chain = []     # Google / SSP / tracking
    nav_chain = []     # Document redirects
    seen_req = set()

    # clear logs
    driver.get_log("performance")

    # timestamp before click
    click_ts = time.time()

    # CLICK
    element.click()

    # ---------------------------
    # Phase A — PRE-navigation
    # ---------------------------
    while time.time() - click_ts < pre_click_window:
        logs = driver.get_log("performance")

        for entry in logs:
            msg = json.loads(entry["message"])["message"]
            if msg.get("method") != "Network.requestWillBeSent":
                continue

            params = msg["params"]
            req = params["request"]
            req_id = params["requestId"]

            if req_id in seen_req:
                continue
            seen_req.add(req_id)

            # BẮT TẤT CẢ (KHÔNG filter Document)
            pre_chain.append({
                "url": req["url"],
                "type": params.get("type"),
                "initiator": params.get("initiator")
            })

        time.sleep(0.005)

    # ---------------------------
    # Phase B — POST-navigation
    # ---------------------------
    start = time.time()
    opened_new_tab = False
    target_window = original_window

    while time.time() - start < timeout:
        # detect new tab/window
        current_windows = set(driver.window_handles)
        new_windows = current_windows - original_windows

        if new_windows:
            target_window = new_windows.pop()
            driver.switch_to.window(target_window)
            opened_new_tab = True

        logs = driver.get_log("performance")

        for entry in logs:
            msg = json.loads(entry["message"])["message"]
            method = msg.get("method")

            if method == "Network.requestWillBeSent":
                params = msg["params"]

                if params.get("type") == "Document":
                    url = params["request"]["url"]
                    if url not in nav_chain:
                        nav_chain.append(url)

            if method == "Network.responseReceived":
                params = msg["params"]

                if params.get("type") == "Document":
                    resp = params["response"]
                    if resp.get("status") == 200:
                        final_url = resp.get("url")
                        if final_url not in nav_chain:
                            nav_chain.append(final_url)

                        # DONE
                        if opened_new_tab:
                            driver.close()
                            driver.switch_to.window(original_window)

                        return {
                            "pre_navigation_chain": pre_chain,
                            "navigation_chain": nav_chain,
                            "final_landing": final_url,
                            "opened_new_tab": opened_new_tab
                        }

        time.sleep(0.01)

    # fallback
    if opened_new_tab:
        driver.close()
        driver.switch_to.window(original_window)

    return {
        "pre_navigation_chain": pre_chain,
        "navigation_chain": nav_chain,
        "final_landing": nav_chain[-1] if nav_chain else None,
        "opened_new_tab": opened_new_tab
    }


def click_and_capture_full_redirect_chain_SIMPLE(
    driver,
    element,
    timeout=10.0
):
    """
    Click element, capture full redirect chain until final landing page.
    Handles new tab/window automatically.
    
    Returns:
        {
          "chain": [url1, url2, ..., final_url],
          "final_url": str,
          "opened_new_tab": bool
        }
    """

    original_window = driver.current_window_handle
    original_windows = set(driver.window_handles)

    redirect_chain = []
    seen_request_ids = set()

    # clear old logs
    driver.get_log("performance")

    # click
    element.click()

    start = time.time()
    target_window = original_window
    opened_new_tab = False

    while time.time() - start < timeout:
        # detect new tab/window
        current_windows = set(driver.window_handles)
        new_windows = current_windows - original_windows

        if new_windows:
            target_window = new_windows.pop()
            driver.switch_to.window(target_window)
            opened_new_tab = True

        logs = driver.get_log("performance")

        for entry in logs:
            msg = json.loads(entry["message"])["message"]
            method = msg.get("method")

            # Capture redirect
            if method == "Network.requestWillBeSent":
                params = msg["params"]
                request = params["request"]

                if params.get("type") == "Document":
                    req_id = params.get("requestId")

                    if req_id not in seen_request_ids:
                        seen_request_ids.add(req_id)
                        redirect_chain.append(request["url"])

            # Detect final landing (200 Document)
            if method == "Network.responseReceived":
                params = msg["params"]

                if params.get("type") == "Document":
                    response = params["response"]
                    status = response.get("status")

                    if status == 200:
                        final_url = response.get("url")

                        if final_url not in redirect_chain:
                            redirect_chain.append(final_url)

                        # DONE
                        result = {
                            "chain": redirect_chain,
                            "final_url": final_url,
                            "opened_new_tab": opened_new_tab
                        }

                        # cleanup
                        if opened_new_tab:
                            driver.close()
                            driver.switch_to.window(original_window)

                        return result

        time.sleep(0.01)

    # timeout fallback
    if opened_new_tab:
        driver.close()
        driver.switch_to.window(original_window)

    return {
        "chain": redirect_chain,
        "final_url": redirect_chain[-1] if redirect_chain else None,
        "opened_new_tab": opened_new_tab
    }



def extract_marked_metadata_all_frames(driver):
    results = []

    def scan_frame(depth=0, frame_path="root"):
        nonlocal results

        # --- 1) scan phần tử đánh dấu trong frame hiện tại ---
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, MARKER)
            for el in elems:
                try:
                    rect = driver.execute_script("""
                        const r = arguments[0].getBoundingClientRect();
                        return {x:r.left, y:r.top, width:r.width, height:r.height};
                    """, el)

                    html = driver.execute_script("return arguments[0].outerHTML;", el)

                    results.append({
                        "tag": el.tag_name,
                        "class": el.get_attribute("class"),
                        "rect": rect,
                        "html": html,
                        "frame_path": frame_path,
                        "page_url": driver.current_url
                    })

                except WebDriverException:
                    continue

        except WebDriverException:
            pass

        # --- 2) tìm và duyệt qua toàn bộ iframe con ---
        iframes = driver.find_elements(By.TAG_NAME, "iframe")

        for idx, iframe in enumerate(iframes):
            sub_path = f"{frame_path} -> iframe[{idx}]"

            try:
                driver.switch_to.frame(iframe)
            except Exception:
                # iframe cross-origin, không truy cập DOM được
                results.append({
                    "tag": "iframe",
                    "class": iframe.get_attribute("class"),
                    "rect": None,
                    "html": "<!-- CROSS ORIGIN IFRAME -->",
                    "frame_path": sub_path,
                    "page_url": driver.current_url
                })
                continue

            # đệ quy xuống iframe con
            scan_frame(depth + 1, sub_path)

            # trở lại frame cha
            driver.switch_to.parent_frame()

    # bắt đầu scan root frame
    scan_frame()
    return results



def classify_url(u: str):
    image_ext = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tiff", ".ico", ".avif")
    video_ext = (".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v")
    audio_ext = (".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a")
    
    # Normalize
    low = u.lower().split("?")[0].split("#")[0]

    # Images
    if low.endswith(image_ext):
        return "image"

    # Media (video/audio)
    if low.endswith(video_ext) or low.endswith(audio_ext):
        return "image"

    # CSS background-image inline URL
    if any(x in u.lower() for x in ["data:image/", "base64,i"]):
        return "image"

    # Typical links or JS/CSS/API
    return "link"

def split_urls(urls):
    images = []
    links = []
    #media = []

    for u in urls:
        t = classify_url(u)
        if t == "image":
            images.append(u)
        # elif t == "media":
        #     media.append(u)
        else:
            links.append(u)

    return {
        "images": images,
        #"media": media,
        "links": links
    }


def extract_urls_from_html(html):
    import re
    if not html:
        return []

    url_pattern = re.compile(
        r"""(?i)
        (?:
            src\s*=\s*["']([^"']+)["'] |
            href\s*=\s*["']([^"']+)["'] |
            data-src\s*=\s*["']([^"']+)["'] |
            data-url\s*=\s*["']([^"']+)["'] |
            url\(\s*["']?([^"')]+)["']?\s*\) |
            (https?://[^\s"'<>]+)
        )
        """, re.VERBOSE
    )

    results = set()

    for match in url_pattern.findall(html):
        for u in match:
            if u:
                results.add(u)

    return list(results)

import time
from selenium.common.exceptions import WebDriverException

def safe_element_screenshot_pro(driver, element, save_path, retries=3):
    """
    Chụp ảnh element một cách ổn định:
    - Tự scroll element vào giữa viewport
    - Ẩn overlay / popup / sticky bars
    - Tự đưa element lên top (z-index cực cao)
    - Kiểm tra 9 điểm xem còn bị che không
    - Retry nếu cần
    """

    def bring_to_view():
        try:
            driver.execute_script("""
                arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});
            """, element)
        except:
            pass
        time.sleep(0.3)

    def hide_overlays():
        # Ẩn tất cả overlay position fixed/sticky ngoại trừ element
        try:
            driver.execute_script("""
            const target = arguments[0];
            document.querySelectorAll('*').forEach(el => {
                try {
                    const s = window.getComputedStyle(el);
                    if (
                        (s.position === 'fixed' || s.position === 'sticky') &&
                        el !== target &&
                        !target.contains(el)
                    ) {
                        el.style.setProperty('display', 'none', 'important');
                    }
                } catch(e){}
            });
            """, element)
        except:
            pass
        time.sleep(0.2)

    def hide_iframes():
        # Iframe thường che element → tắt pointer-events
        try:
            driver.execute_script("""
            document.querySelectorAll('iframe').forEach(f => {
                f.style.setProperty('pointer-events', 'none', 'important');
            });
            """)
        except:
            pass
        time.sleep(0.1)

    def force_to_top():
        # Đưa element lên layer trên cùng
        try:
            driver.execute_script("""
            arguments[0].style.setProperty('position', 'relative', 'important');
            arguments[0].style.setProperty('z-index', '99999999', 'important');
            arguments[0].style.setProperty('pointer-events', 'auto', 'important');
            """, element)
        except:
            pass
        time.sleep(0.1)

    def is_blocked_9points():
        try:
            return driver.execute_script("""
            const el = arguments[0];
            const r = el.getBoundingClientRect();
            const pts = [
                [r.left+1, r.top+1],
                [r.right-1, r.top+1],
                [r.left+1, r.bottom-1],
                [r.right-1, r.bottom-1],
                [r.left + r.width/2, r.top+1],
                [r.left + r.width/2, r.bottom-1],
                [r.left+1, r.top + r.height/2],
                [r.right-1, r.top + r.height/2],
                [r.left + r.width/2, r.top + r.height/2]
            ];
            for (const [x,y] of pts) {
                const topEl = document.elementFromPoint(x, y);
                if (topEl !== el) return true;
            }
            return false;
            """, element)
        except:
            return False

    # ===================
    #  Main logic (retry)
    # ===================
    for attempt in range(1, retries+1):
        bring_to_view()
        hide_overlays()
        hide_iframes()
        force_to_top()

        blocked = is_blocked_9points()

        if blocked:
            print(f"[WARN] Attempt {attempt}: element vẫn bị che — retry...")
            time.sleep(0.3)
            continue

        # Try capture
        try:
            png = element.screenshot_as_png
            with open(save_path, "wb") as f:
                f.write(png)
            print(f"[OK] Screenshot saved: {save_path}")
            return True

        except WebDriverException:
            print(f"[ERR] Attempt {attempt} failed capturing element.")
            time.sleep(0.3)

    print("[FAIL] safe_element_screenshot_pro(): Không thể chụp chính xác element sau khi retry.")
    return False


def extract_marked_metadata(driver):
    """
    Trích xuất metadata của tất cả phần tử được extension đánh dấu.
    Trả về danh sách dict gồm:
        tag, class, rect, html, link, page_url
    """

    script_new = """
function getXPath(el) {
  if (el.id) return '//*[@id="' + el.id + '"]';

  var parts = [];
  while (el && el.nodeType === 1) {
    var idx = 1;
    var sib = el.previousSibling;
    while (sib) {
      if (sib.nodeType === 1 && sib.tagName === el.tagName) idx++;
      sib = sib.previousSibling;
    }
    parts.unshift(el.tagName.toLowerCase() + '[' + idx + ']');
    el = el.parentNode;
  }
  return '/' + parts.join('/');
}

function extractMarkedElementsKeepChild() {
  var markers = [
    'adblocked-marker',
    'acceptablead-marker',
    'possiblead-marker',
    'adnetwork-marker'
  ];

  var selector = '';
  for (var i = 0; i < markers.length; i++) {
    if (i > 0) selector += ',';
    selector += '.' + markers[i];
  }

  var elems = Array.prototype.slice.call(
    document.querySelectorAll(selector)
  );

  var withXPath = [];
  for (var i = 0; i < elems.length; i++) {
    withXPath.push({
      el: elems[i],
      xpath: getXPath(elems[i])
    });
  }

  // sort deepest first
  withXPath.sort(function(a, b) {
    return b.xpath.length - a.xpath.length;
  });

  var kept = [];

  for (var i = 0; i < withXPath.length; i++) {
    var item = withXPath[i];
    var isParent = false;

    for (var j = 0; j < kept.length; j++) {
      if (kept[j].xpath.indexOf(item.xpath + '/') === 0) {
        isParent = true;
        break;
      }
    }

    if (!isParent) {
      kept.push(item);
    }
  }

  var result = [];
  for (var i = 0; i < kept.length; i++) {
    var el = kept[i].el;
    result.push({
      tag: el.tagName.toLowerCase(),
      classes: el.className,
      xpath: kept[i].xpath,
      rect: el.getBoundingClientRect().toJSON(),
      html: el.outerHTML,
      link: el.src || el.href || ""
    });
  }

  return result;
}

return extractMarkedElementsKeepChild();
"""

    script_new_j = """
    function getXPath(el) {
      if (el.id) return '//*[@id="' + el.id + '"]';

      const parts = [];
      while (el && el.nodeType === 1) {
        let idx = 1;
        let sib = el.previousSibling;
        while (sib) {
          if (sib.nodeType === 1 && sib.tagName === el.tagName) idx++;
          sib = sib.previousSibling;
        }
        parts.unshift(el.tagName.toLowerCase() + '[' + idx + ']');
        el = el.parentNode;
      }
      return '/' + parts.join('/');
    }

    function extractMarkedElementsKeepChild() {
      const markers = [
        'adblocked-marker',
        'acceptablead-marker',
        'possiblead-marker',
        'adnetwork-marker'
      ];
      const elems = Array.from(document.querySelectorAll(
        markers.map(c => '.' + c).join(',')
      ));

      const withXPath = elems.map(el => ({
        el,
        xpath: getXPath(el)
      }));

      // deepest first
      withXPath.sort((a, b) => b.xpath.length - a.xpath.length);

      const kept = [];

      for (const item of withXPath) {
        const isParent = kept.some(
          k => k.xpath.startsWith(item.xpath + '/')
        );
        if (!isParent) {
          kept.push(item);
        }
      }

      return kept.map(({ el, xpath }) => ({
        tag: el.tagName.toLowerCase(),
        classes: el.className,
        xpath: xpath,
        rect: el.getBoundingClientRect().toJSON(),
        html: el.outerHTML,
        link: el.src || el.href || ""
      }));
    """
    script = """
    const elems = Array.from(document.querySelectorAll(
        '.adblocked-marker, .acceptablead-marker, .possiblead-marker, .adnetwork-marker'
    ));
    return elems.map(el => ({
        tag: el.tagName.toLowerCase(),
        classes: el.className,
        rect: el.getBoundingClientRect().toJSON(),
        html: el.outerHTML,
        //html: el.outerHTML.slice(0, 500),  // cắt ngắn nếu quá dài
        link: el.src || el.href || ""
    }));



    """
    elements = driver.execute_script(script_new)
    page_url = driver.current_url
    for el in elements:
        el["page_url"] = page_url
    print(f"[INFO] Found {len(elements)} marked elements on {page_url}")
    return elements


import time
from selenium.common.exceptions import WebDriverException

def safe_element_screenshot(driver, element, save_path):
    """
    Chụp ảnh một element một cách an toàn, tránh bị che bởi overlay.
    """


    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        time.sleep(0.3)
    except:
        pass


    try:
        driver.execute_script("""
        document.querySelectorAll('*').forEach(el => {
            const s = window.getComputedStyle(el);
            if (
                (s.position === 'fixed' || s.position === 'sticky') &&
                parseInt(s.zIndex) > 500 &&
                !el.contains(arguments[0])
            ) {
                el.style.setProperty('display', 'none', 'important');
            }
        });
        """, element)
        time.sleep(0.2)
    except:
        pass

    try:
        driver.execute_script("""
        arguments[0].style.setProperty('position', 'relative', 'important');
        arguments[0].style.setProperty('z-index', '9999999', 'important');
        arguments[0].style.setProperty('pointer-events', 'auto', 'important');
        """, element)
    except:
        pass


    try:
        is_blocked = driver.execute_script("""
        const el = arguments[0];
        const r = el.getBoundingClientRect();
        const cx = r.left + r.width/2;
        const cy = r.top + r.height/2;
        const topEl = document.elementFromPoint(cx, cy);
        return topEl !== el;
        """, element)

        if is_blocked:
            print("[WARN] Element is still blocked — but attempting screenshot with forced z-index.")
    except:
        pass
   

    try:
        png = element.screenshot_as_png
        with open(save_path, "wb") as f:
            f.write(png)
        return True
    except WebDriverException:
        return False


import time
import json

def click_and_abort_navigation(
    driver,
    element,
    timeout=2.0,
    stop_on_first_request=True
):
    """
    Click element, capture all network requests triggered by click,
    abort page navigation immediately.

    Returns: list of dict {url, method, timestamp, initiator}
    """

    requests = []
    start_time = time.time()

    # Clear old logs
    driver.get_log("performance")

    # Click thật
    element.click()

    while time.time() - start_time < timeout:
        logs = driver.get_log("performance")

        for entry in logs:
            message = json.loads(entry["message"])["message"]
            method = message.get("method")

            if method == "Network.requestWillBeSent":
                params = message["params"]
                request = params["request"]

                req_info = {
                    "url": request.get("url"),
                    "method": request.get("method"),
                    "timestamp": params.get("timestamp"),
                    "initiator": params.get("initiator", {})
                }

                requests.append(req_info)

                # 🛑 STOP NGAY khi thấy request đầu tiên
                if stop_on_first_request:
                    driver.execute_cdp_cmd("Page.stopLoading", {})
                    return requests

        time.sleep(0.01)

    # fallback stop
    driver.execute_cdp_cmd("Page.stopLoading", {})
    return requests




def capture_marked_elements_lite(driver, outdir, screenshot=False):
    import os
    import time

    os.makedirs(outdir, exist_ok=True)
    metadata = extract_marked_metadata(driver)

    for i, ad in enumerate(metadata):
        try:
            rect = ad["rect"]
            driver.execute_script("window.scrollTo(arguments[0], arguments[1]);", rect["x"], rect["y"] - 100)
            time.sleep(0.5)

            el = driver.execute_script(f"""return document.querySelectorAll('.adblocked-marker, .acceptablead-marker, .possiblead-marker, .adnetwork-marker')[arguments[0]];""", i)

            if el:
                if rect["width"] <= 2 or rect["height"] <= 2:
                    #print(f"[SKIP] Element {i} is too small ({rect['width']}x{rect['height']}) - skipping.")
                    continue
                if screenshot:
                    # Save screenshot
                    class_name = ad["classes"].split()[0] if ad["classes"] else "marked"
                    fname = os.path.join(outdir, f"{class_name}_{i}.png")
                    safe_element_screenshot(driver, el, fname)
                    #png = el.screenshot_as_png
                    #with open(fname, "wb") as f:
                    #    f.write(png)
                    print(f"[OK] Captured: {fname}")

                urls = extract_ad_url_without_click(driver, el)
                if urls:
                    fname = os.path.join(outdir, "Ads_URL.txt")
                    with open(fname, 'a', encoding='utf-8') as file:
                        for item in urls:
                            file.write(f"{item}\n") # Use an f-string to append a newline
                            
                #print("-----------------------------------------------")

        except Exception as e:
            pass

