import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import argparse
from termcolor import colored
import os
import pickle
import signal
import time
from multiprocessing import Process, Manager, Queue, cpu_count, Event
import queue as queue_module
import pyfiglet

# -------------------------
# Constants
# -------------------------
ABSOLUTE_URL_PATTERN = r'https?://[^\s"\'<>]+'
RELATIVE_PATTERN = r'["\'](\/[a-zA-Z0-9_\-\/\.]+)["\']'
PARENT_REL_PATTERN = r'["\'](\.\.\/[a-zA-Z0-9_\-\/\.]+)["\']'

# -------------------------
# State handling
# -------------------------
def save_state(visited, status_codes, pending_list, filename):
    state = {
        "visited": dict(visited),
        "status_codes": dict(status_codes),
        "queue": list(pending_list)
    }
    with open(filename, "wb") as f:
        pickle.dump(state, f)
    print(colored(f"\n[+] State saved to {filename} ({len(state['visited'])} visited, {len(state['queue'])} pending)", "cyan"))

def load_state(filename):
    state = None
    if os.path.exists(filename):
        choice = ''
        while choice.lower() not in ['y', 'n']:
            choice = input(f"{colored(filename, 'yellow')} exists. Do you want to resume it (y/n)? ")

        if choice.lower() == 'y':
            with open(filename, "rb") as f:
                state = pickle.load(f)
                print(colored(f"[+] Resuming previous scan ({len(state['visited'])} visited)", "cyan"))
        else:
            os.remove(filename)
    
    return state

# -------------------------
# Utilities
# -------------------------
def normalize(url):
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()

def get_status_color(code):
    if isinstance(code, int):
        if 200 <= code < 300: return "green"
        elif 300 <= code < 400: return "yellow"
        else: return "red"
    return "red"

def is_in_scope(netloc, base_domain, allow_subdomains=True):
    netloc = netloc.lower().split(":")[0]
    if netloc == base_domain: return True
    if allow_subdomains and netloc.endswith("." + base_domain): return True
    return False

def add_link(link, base_domain, visited, queue, pending_list, allow_subdomains):
    link = normalize(link)
    parsed = urlparse(link)
    if is_in_scope(parsed.netloc, base_domain, allow_subdomains):
        if link not in visited:
            visited[link] = False 
            pending_list.append(link)
            queue.put(link)

# -------------------------
# Extraction
# -------------------------
def extract_content(content, content_type, url, base_domain, visited, queue, pending_list, allow_subdomains):
    for match in re.findall(ABSOLUTE_URL_PATTERN, content):
        add_link(match, base_domain, visited, queue, pending_list, allow_subdomains)
    for match in re.findall(RELATIVE_PATTERN, content):
        add_link(urljoin(url, match), base_domain, visited, queue, pending_list, allow_subdomains)
    for match in re.findall(PARENT_REL_PATTERN, content):
        add_link(urljoin(url, match), base_domain, visited, queue, pending_list, allow_subdomains)
    
    if "html" in content_type:
        soup = BeautifulSoup(content, "html.parser")
        tags_attrs = {"a":"href","script":"src","link":"href","iframe":"src","img":"src","form":"action"}
        for tag, attr in tags_attrs.items():
            for element in soup.find_all(tag):
                val = element.get(attr)
                if val:
                    add_link(urljoin(url, val), base_domain, visited, queue, pending_list, allow_subdomains)

# -------------------------
# Result writer
# -------------------------
def result_writer(results_queue, output_folder):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    files = {
        "2xx": open(os.path.join(output_folder, "2xx.txt"), "a"),
        "3xx": open(os.path.join(output_folder, "3xx.txt"), "a"),
        "4xx": open(os.path.join(output_folder, "4xx.txt"), "a"),
        "5xx": open(os.path.join(output_folder, "5xx.txt"), "a"),
        "err": open(os.path.join(output_folder, "error.txt"), "a")
    }
    
    while True:
        try:
            item = results_queue.get(timeout=1)
            if item == "__STOP__": break
            
            url, status, size = item # Unpack 3 values
            
            if isinstance(status, int):
                cat = f"{str(status)[0]}xx"
                if cat in files: 
                    files[cat].write(f"{url},{status},{size}\n")
            else:
                files["err"].write(f"{url},{status},0\n")
        except queue_module.Empty:
            continue

    for f in files.values(): f.close()

# -------------------------
# Worker
# -------------------------
def crawler_worker(worker_id, queue, visited, status_codes, pending_list, results_queue, base_domain, allow_subdomains, proxy_url, socks_url, headers, follow_redirect, stop_event):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    selected_proxy = socks_url or proxy_url
    client_args = {
        "http2": True, 
        "follow_redirects": follow_redirect, 
        "verify": False, 
        "timeout": 12, 
        "headers": headers
    }
    
    if selected_proxy:
        client_args["proxy"] = selected_proxy
    
    with httpx.Client(**client_args) as client:
        while not stop_event.is_set():
            try:
                url = queue.get(timeout=1)
            except queue_module.Empty:
                continue

            if visited.get(url) is True:
                if url in pending_list: pending_list.remove(url)
                continue
                
            try:
                response = client.get(url)
                status = response.status_code
                
                # Extract content length
                content_len = response.headers.get("Content-Length")
                if content_len is None:
                    content_len = len(response.content)
                
                status_codes[url] = status
                results_queue.put((url, status, content_len))
                print(f"[W{worker_id}] {url} ({colored(status, get_status_color(status))}) [{content_len} bytes]")
                
                content_type = response.headers.get("Content-Type", "").lower()
                if any(x in content_type for x in ["text/", "json", "xml", "javascript"]):
                    extract_content(response.text, content_type, url, base_domain, visited, queue, pending_list, allow_subdomains)
                
            except Exception as e:
                err = f"ERROR-{type(e).__name__}"
                status_codes[url] = err
                results_queue.put((url, err, 0))
            finally:
                visited[url] = True
                if url in pending_list: pending_list.remove(url)

# -------------------------
# Main
# -------------------------
def main():
    finished_cleanly = False 
    
    parser = argparse.ArgumentParser(description="CrawlStrike")
    parser.add_argument("url")
    parser.add_argument("-w","--workers", type=int, default=cpu_count())
    parser.add_argument("--no-subdomains", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--proxy", help="Proxy (http://127.0.0.1:8080)")
    parser.add_argument("--socks", help="SOCKS Proxy (e.g., socks5://127.0.0.1:9050)")
    parser.add_argument("--header", action="append", help="Custom HTTP header, format: 'Key: Value'")
    parser.add_argument("--follow-redirect", action="store_true", help="Follow redirects")
    args = parser.parse_args()

    title = pyfiglet.figlet_format("CrawlStrike", font="slant")
    print(colored(title, "green"))

    START_URL = args.url
    allow_subdomains = not args.no_subdomains
    base_domain = urlparse(START_URL).netloc.lower().split(":")[0]
    output_folder = args.output or base_domain
    os.makedirs(output_folder, exist_ok=True)
    
    state_filename = (output_folder.rstrip("/\\") + ".pkl")

    headers = {"User-Agent": "Mozilla/5.0"}
    if args.header:
        for h in args.header:
            if ":" in h:
                k, v = h.split(":", 1)
                headers[k.strip()] = v.strip()

    manager = Manager()
    visited = manager.dict()
    status_codes = manager.dict()
    pending_list = manager.list()
    queue = manager.Queue()
    stop_event = manager.Event()

    results_queue = Queue()

    state = load_state(state_filename)
    if state:
        for k, v in state["visited"].items(): visited[k] = v
        for k, v in state["status_codes"].items(): status_codes[k] = v
        for url in state["queue"]:
            pending_list.append(url)
            queue.put(url)
    else:
        add_link(START_URL, base_domain, visited, queue, pending_list, allow_subdomains)

    writer = Process(target=result_writer, args=(results_queue, output_folder))
    writer.start()

    workers = []
    for i in range(args.workers):
        p = Process(target=crawler_worker, args=(
            i, queue, visited, status_codes, pending_list, results_queue, 
            base_domain, allow_subdomains, args.proxy, args.socks, 
            headers, args.follow_redirect, stop_event,
        ))
        p.start()
        workers.append(p)

    try:
        while any(p.is_alive() for p in workers):
            time.sleep(1)
            
            if queue.empty():
                is_working = any(visited[url] is False for url in pending_list)
                if not is_working:
                    time.sleep(2) 
                    if queue.empty() and not any(visited[url] is False for url in pending_list):
                        print(colored("\n[+] All URLs processed. Finishing...", "green"))
                        finished_cleanly = True
                        stop_event.set()
                        break

    except KeyboardInterrupt:
        print(colored("\n[!] Ctrl+C detected! Shutting down...", "yellow"))
        stop_event.set()

    for p in workers: p.join()
    results_queue.put("__STOP__")
    writer.join()

    if finished_cleanly:
        print(colored(f"[+] Crawl completed successfully. Removing {state_filename}", "green"))
        if os.path.exists(state_filename):
            os.remove(state_filename)
    else:
        save_state(visited, status_codes, pending_list, state_filename)

if __name__=="__main__":
    main()