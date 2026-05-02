import ast
from urllib.parse import urlparse, parse_qsl, unquote
import tldextract
import csv
from libs.dbProcess import get_db_conn
import pandas as pd
import os
import argparse
import hashlib
import base64
import urllib.parse



def deduplicate(results):
    seen = set()
    output = []

    for row in results:
        id_csv = row["id_csv"]
        domain = extract_reached_domain(row["advertiser_url"])

        key = (id_csv, domain)

        if key not in seen:
            seen.add(key)
            output.append(row)

    return output


def multi_decode(url, max_rounds=5):
    """
    Decode URL nhiều lần cho đến khi không đổi nữa
    """
    previous = url
    for _ in range(max_rounds):
        decoded = unquote(previous)
        if decoded == previous:
            break
        previous = decoded
    return previous

def loadSitesFromCSV(csv_path):
    sites = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sites.append({
                "id_csv": int(row["id_site"]),
                "url": row["ads_url"]
            })
    return sites


def is_first_party(cookie_domain, advertiser_domain):
    cookie_domain = str(cookie_domain).lstrip(".")
    if cookie_domain == advertiser_domain:
        return True

    if cookie_domain.endswith("." + advertiser_domain):
        return True

    return False

def get_data_cookies_by_id_csv(conn, value, id_csv):
    curr = conn.cursor()

    query = f"""
        SELECT run_no, name, value, domain, current_url
        FROM cookies 
        WHERE id_csv = {id_csv} AND (value LIKE '%{value}%')
    """
    
    curr.execute(query)
    data = curr.fetchall()
    return data


def get_data_request_by_id_csv_test(conn, value, id_csv):
    curr = conn.cursor()

    query_notJOIN = f"""
        SELECT request_url, run_no
        FROM network_requests
        WHERE id_csv = {id_csv} 
        AND
        (request_url LIKE '%{value}%'
        OR headers LIKE '%{value}%'
        OR post_data LIKE '%{value}%')
    """

    query_JOIN = f"""
        SELECT nr.request_url, nr.run_no
        FROM network_requests nr JOIN network_request_extra_info nre
        ON nr.cdp_request_id = nre.cdp_request_id
        WHERE nr.id_csv = {id_csv} 
        AND
        (nr.request_url LIKE '%{value}%'
        OR nr.headers LIKE '%{value}%'
        OR nr.post_data LIKE '%{value}%'
        OR nre.headers LIKE '%{value}%'
        OR nre.cookies LIKE '%{value}%')
    """

    query_FULL_JOIN = f"""
        SELECT 
        nreq.request_url, 
        nreq.run_no, 
        nres.headers, 
        nres.response_body, 
        nresExtra.headers, 
        nresExtra.cookies, 
        nreq.headers, 
        nreq.post_data, 
        nreqExtra.headers, 
        nreqExtra.cookies,
        s.reached_url,
        nreq.easylist,
        nreq.privacylist
        FROM sites s JOIN network_responses nres ON s.id_site = nres.id_site
        JOIN network_response_extra_info nresExtra ON nres.cdp_request_id = nresExtra.cdp_request_id 
        JOIN network_requests nreq ON nreq.cdp_request_id = nres.cdp_request_id 
        JOIN network_request_extra_info nreqExtra ON nreqExtra.cdp_request_id = nreq.cdp_request_id 
        WHERE s.id_csv = {id_csv}
        AND s.crawl_status = 'success'
        AND (nres.headers LIKE '%{value}%' 
        OR nres.response_body like '%{value}%' 
        OR nresExtra.headers LIKE '%{value}%' 
        OR nresExtra.cookies LIKE '%{value}%' 
        OR nreq.request_url LIKE '%{value}%' 
        OR nreq.headers LIKE '%{value}%' 
        OR nreq.post_data LIKE '%{value}%' 
        OR nreqExtra.headers LIKE '%{value}%' 
        OR nreqExtra.cookies LIKE '%{value}%') 
    """

    curr.execute(query_FULL_JOIN)
    data = curr.fetchall()
    return data

def get_data_request_by_id_csv(conn, value, id_csv, tracking):
    curr = conn.cursor()

    query_FULL_JOIN_tracking = f"""
        SELECT 
        nreq.request_url, 
        nreq.run_no, 
        nres.headers, 
        nres.response_body, 
        nresExtra.headers, 
        nresExtra.cookies, 
        nreq.headers, 
        nreq.post_data, 
        nreqExtra.headers, 
        nreqExtra.cookies,
        s.reached_url,
        nreq.easylist,
        nreq.privacylist
        FROM sites s JOIN network_responses nres ON s.id_site = nres.id_site
        JOIN network_response_extra_info nresExtra ON nres.cdp_request_id = nresExtra.cdp_request_id 
        JOIN network_requests nreq ON nreq.cdp_request_id = nres.cdp_request_id 
        JOIN network_request_extra_info nreqExtra ON nreqExtra.cdp_request_id = nreq.cdp_request_id 
        WHERE s.id_csv = {id_csv}
        AND s.crawl_status = 'success'
        AND (nreq.easylist = True OR nreq.privacylist = True)
        AND (nres.headers LIKE '%{value}%' 
        OR nres.response_body like '%{value}%' 
        OR nresExtra.headers LIKE '%{value}%' 
        OR nresExtra.cookies LIKE '%{value}%' 
        OR nreq.request_url LIKE '%{value}%' 
        OR nreq.headers LIKE '%{value}%' 
        OR nreq.post_data LIKE '%{value}%' 
        OR nreqExtra.headers LIKE '%{value}%' 
        OR nreqExtra.cookies LIKE '%{value}%') 
    """


    query_FULL_JOIN = f"""
        SELECT 
        nreq.request_url, 
        nreq.run_no, 
        nres.headers, 
        nres.response_body, 
        nresExtra.headers, 
        nresExtra.cookies, 
        nreq.headers, 
        nreq.post_data, 
        nreqExtra.headers, 
        nreqExtra.cookies,
        s.reached_url,
        nreq.easylist,
        nreq.privacylist
        FROM sites s JOIN network_responses nres ON s.id_site = nres.id_site
        JOIN network_response_extra_info nresExtra ON nres.cdp_request_id = nresExtra.cdp_request_id 
        JOIN network_requests nreq ON nreq.cdp_request_id = nres.cdp_request_id 
        JOIN network_request_extra_info nreqExtra ON nreqExtra.cdp_request_id = nreq.cdp_request_id 
        WHERE s.id_csv = {id_csv}
        AND s.crawl_status = 'success'
        AND (nres.headers LIKE '%{value}%' 
        OR nres.response_body like '%{value}%' 
        OR nresExtra.headers LIKE '%{value}%' 
        OR nresExtra.cookies LIKE '%{value}%' 
        OR nreq.request_url LIKE '%{value}%' 
        OR nreq.headers LIKE '%{value}%' 
        OR nreq.post_data LIKE '%{value}%' 
        OR nreqExtra.headers LIKE '%{value}%' 
        OR nreqExtra.cookies LIKE '%{value}%') 
    """

    if tracking:
        curr.execute(query_FULL_JOIN_tracking)
    else:
        curr.execute(query_FULL_JOIN)
    data = curr.fetchall()
    return data


def get_data_sites(conn):
    curr = conn.cursor()

    # query = f"""
    #     SELECT DISTINCT id_csv, domain_url, reached_url
    #     FROM sites 
    #     WHERE crawl_status = 'success'
    # """

    query = f"""
        SELECT DISTINCT id_csv, domain_url
        FROM sites 
        WHERE crawl_status = 'success'
    """
    
    curr.execute(query)
    data = curr.fetchall()
    return data

def is_first_party(cookie_domain, advertiser_domain):
    cookie_domain = str(cookie_domain).lstrip(".")
    if cookie_domain == advertiser_domain:
        return True

    if cookie_domain.endswith("." + advertiser_domain):
        return True

    return False


def check_request(data, value):
    results = set()
    if data:
        for row in data:
            request = row[0]
            advertiser_url = row[10]
            easylist = row[11]
            privacylist = row[12]

            request_domain = extract_reached_domain(request)
            domain = extract_reached_domain(advertiser_url)

            if request_domain != "" and domain != "":
                if request_domain.lower() != domain.lower():
                    if value in request:
                        results.add((row[1], domain, request_domain, "URI"))
                    
                    bodies = [row[3], row[7]]
                    for body in bodies:
                        if body and value in body:
                            results.add((row[1], domain, request_domain, "PAYLOAD"))
                    
                    
                    headers = [row[2], row[4], row[6], row[8]]
                    for header in headers:
                        if not header:
                            continue
                        
                        try:
                            headers_dict = ast.literal_eval(header)
                        except:
                            headers_dict = None
                        
                        if headers_dict:
                            headers_dict = {k.lower(): v for k, v in headers_dict.items()}

                            referer = headers_dict.get("referer")
                            if referer and value in referer:
                                results.add((row[1], domain, request_domain, "REFERER"))
                        
                            cookies = headers_dict.get("cookie")
                            if cookies and value in cookies:
                                results.add((row[1], domain, request_domain, "COOKIE"))
                        
                            setCookies = headers_dict.get("set-cookie")
                            if setCookies and value in setCookies:
                                results.add((row[1], domain, request_domain, "COOKIE"))
                                                
                    
                    cookies = [row[5], row[9]]
                    for cookie in cookies:
                        if cookie and value in cookie:
                            results.add((row[1], domain, request_domain, "COOKIE"))
    
    
    return results

def extract_reached_domain(url):
    if not url:
        #print("Not url: ",url)
        return ""

    try:
        ext = tldextract.extract(url)
        if not ext.domain or not ext.suffix:
            #print("Error :",url)
            return ""
        return f"{ext.domain}.{ext.suffix}"
    except Exception as e:
        #print("Error :",url)
        #print (e)
        return ""



def extract_params_from_url(url):
    """
    Universal extractor:
    - Query parameters (?a=1&b=2)
    - Matrix parameters (;a=1;b=2)
    - Double/triple encoded URLs
    """

    all_params = []

    # 1️⃣ Decode nhiều vòng
    decoded_url = multi_decode(url)

    parsed = urlparse(decoded_url)

    # 2️⃣ Query parameters chuẩn
    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    for k, v in query_params:
        all_params.append({"name": k, "value": v})

    # 3️⃣ Matrix parameters (;param=value)
    if ";" in parsed.path:
        parts = parsed.path.split(";")[1:]  # bỏ phần path đầu
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                all_params.append({"name": k, "value": v})

    return all_params


def for_each_country_case(output_csv, tracking):
    results = []
    with get_db_conn() as conn:
        data_sites = get_data_sites(conn)

    i=0
    for row_site in data_sites:
        i=i+1
        id_csv = row_site[0]
        print(f"{i}/{len(data_sites)}: Processing id_csv: {id_csv}")
                
        ads_url = row_site[1]
        #advertiser_url = row_site[2]

        params = extract_params_from_url(ads_url)
        value_gclid = None
        for p in params:
            if p["name"].lower() == "gclid":
                value_gclid = p["value"]
                #print(value_gclid)
                break
        
        if value_gclid:
            with get_db_conn() as conn:
                data = get_data_request_by_id_csv(conn, value_gclid, id_csv, tracking)
                #data_cookies = get_data_cookies_by_id_csv(conn, value_gclid, id_csv)
            
            result = check_request(data, value_gclid)
            

            for r in result:
                results.append({
                    "id_csv": id_csv,
                    "gg_ads_url": ads_url,
                    "run_no": (r[0] - 1) % 5 + 1,
                    "advertiserDomain": r[1],
                    "third_domain": r[2],
                    "channel": r[3]
                })
        
        else:
                results.append({
                    "id_csv": id_csv,
                    "gg_ads_url": ads_url,
                    "run_no": "",
                    "advertiserDomain": "",
                    "third_domain": "",
                    "channel": ""
                })
    
    import csv

    fieldnames = ["id_csv", "gg_ads_url", "run_no", "advertiserDomain" ,"third_domain", "channel"]
    
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()   # ghi header
        writer.writerows(results)  # ghi data


def main(outdir, tracking=False):
    output_csv = f"{outdir}/3rdDomain_received.csv"
    for_each_country_case(output_csv, tracking)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch Data Processing - Get Domain received GCLID")
    parser.add_argument("--tracking", action="store_true", help="Check tracking")

    args = parser.parse_args()


    tracking = args.tracking

    if tracking:
        outdir = f"Report_Tracking_ListReceivedGCLID"
    else:
        outdir = f"Report_ListReceivedGCLID"
    os.makedirs(outdir, exist_ok=True)
    main(outdir, tracking)