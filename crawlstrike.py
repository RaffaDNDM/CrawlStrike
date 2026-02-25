import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque, defaultdict
import argparse
from termcolor import colored

ABSOLUTE_URL_PATTERN = r'https?://[^\s"\'<>]+'
RELATIVE_PATTERN = r'["\'](\/[a-zA-Z0-9_\-\/\.]+)["\']'
PARENT_REL_PATTERN = r'["\'](\.\.\/[a-zA-Z0-9_\-\/\.]+)["\']'

def get_status_color(status_code):
    if isinstance(status_code, int):
        if 200 <= status_code < 300:
            return "green"
        elif 300 <= status_code < 400:
            return "yellow"
        else:
            return "red"
    return "red"

def normalize(url):
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()

def is_in_scope(netloc, base_domain):
    netloc = netloc.lower().split(":")[0]

    if netloc == base_domain:
        return True
    if netloc.endswith("." + base_domain):
        return True
    return False

def add_link(link, source_url, base_domain, found_links, visited, queue):
    link = normalize(link)
    found_links[link].add(source_url)

    parsed = urlparse(link)

    if is_in_scope(parsed.netloc, base_domain):
        if link not in visited and link not in queue:
            queue.append(link)

def extract_with_regex(content, base_url, base_domain, found_links, visited, queue):
    for match in re.findall(ABSOLUTE_URL_PATTERN, content):
        add_link(match, base_url, base_domain, found_links, visited, queue)

    for match in re.findall(RELATIVE_PATTERN, content):
        add_link(urljoin(base_url, match), base_url, base_domain, found_links, visited, queue)

    for match in re.findall(PARENT_REL_PATTERN, content):
        add_link(urljoin(base_url, match), base_url, base_domain, found_links, visited, queue)

def extract_with_bs4(soup, base_url, base_domain, found_links, visited, queue):
    tags_attrs = {
        "a": "href",
        "script": "src",
        "link": "href",
        "iframe": "src",
        "img": "src",
        "form": "action"
    }

    for tag, attr in tags_attrs.items():
        for element in soup.find_all(tag):
            if element.get(attr):
                add_link(urljoin(base_url, element[attr]), base_url, base_domain, found_links, visited, queue)

def get_link_color(link, status_codes, base_domain, domain_filter):
    parsed = urlparse(link)
    netloc = parsed.netloc.lower()
    
    if netloc == base_domain:
        color = "green"
    elif netloc.endswith("." + base_domain):
        color = "yellow"
    elif domain_filter and domain_filter and domain_filter.lower() in netloc:
        color = "yellow"
    else:
        color = "red"
    
    return color

def write_link_to_file(link, status_codes, fd, show_status=False):
    if show_status:
        if link in status_codes:
            fd.write(f"{link},{status_codes[link]}\n")
        else:
            fd.write(f"{link},SKIPPED\n")

    else:
        fd.write(f"{link}\n")


def main():
    parser = argparse.ArgumentParser(description="CrawlStrike - Recursive Scoped Crawler (HTTP/2)")
    parser.add_argument("--source", action="store_true", help="Show source pages")
    parser.add_argument("--proxy", help="Proxy (http://127.0.0.1:8080)")
    parser.add_argument("-f", "--domain-filter", help="Extra domain filter")
    parser.add_argument("-sc", action="store_true", help="Generate files with identified links, grouped by status codes (i.e. 2xx.txt, 3xx.txt, error.txt)")
    parser.add_argument("url", help="Starting URL")
    args = parser.parse_args()

    START_URL = args.url
    SOURCES = args.source
    SHOW_STATUS = args.sc


    client_args = {
        "http2": True,
        "follow_redirects": True,
        "verify": False,
        "timeout": 10.0,
        "headers": {
            "User-Agent": "Mozilla/5.0"
        }
    }

    if args.proxy:
        proxy_url = args.proxy
        if not proxy_url.startswith(("http://", "https://")):
            proxy_url = "http://" + proxy_url
        client_args["proxies"] = proxy_url
        print(f"[+] Using proxy: {proxy_url}")

    session = httpx.Client(**client_args)


    visited = set()
    queue = deque([START_URL])
    found_links = defaultdict(set)
    status_codes = {}

    base_domain = urlparse(START_URL).netloc.lower().split(":")[0]

    while queue:
        url = queue.popleft()

        if url in visited:
            continue

        visited.add(url)
        parsed = urlparse(url)

        if not is_in_scope(parsed.netloc, base_domain):
            continue

        try:
            response = session.get(url)
            status_codes[url] = response.status_code

            sc_color = get_status_color(response.status_code)

            print(f"[+] Visiting: {url} ({colored(response.status_code, sc_color)})")

        except Exception as e:
            error_text = f"ERROR - {type(e).__name__}"
            status_codes[url] = error_text
            print(f"[!] Visiting: {url} ({error_text})")
            continue

        try:
            content = response.text
        except Exception:
            continue

        content_type = response.headers.get("Content-Type", "").lower()
        
        if any(x in content_type for x in [
            "text/html",
            "application/javascript",
            "text/javascript",
            "application/json",
            "text/json",
            "text/plain",
            "application/xml",
            "text/xml",
        ]):
            extract_with_regex(content, url, base_domain, found_links, visited, queue)

            if "text/html" in content_type:
                soup = BeautifulSoup(content, "html.parser")
                extract_with_bs4(soup, url, base_domain, found_links, visited, queue)

    print("\n==== FOUND LINKS ====\n")

    if SHOW_STATUS:
        with open("2xx.txt", "w") as f2xx, open("3xx.txt", "w") as f3xx, open("error.txt", "w") as ferr, open("skipped.txt", "w") as fskip:
            for link, sources in found_links.items():
                parsed = urlparse(link)
                netloc = parsed.netloc.lower()

                output = link

                if link in status_codes:
                    sc = status_codes[link]

                    if 200 <= sc < 300:
                        f2xx.write(f"{link},{sc}\n")
                    elif 300 <= sc < 400:
                        f3xx.write(f"{link},{sc}\n")
                    else:
                        ferr.write(f"{link},{sc}\n")
                else:
                    fskip.write(f"{link},SKIPPED\n")

                if SOURCES:
                    for src in sources:
                        print(f"\tFound on: {src}")

    fds={}
    with open("in_scope.txt", "w") as fds["green"], open("oos.txt", "w") as fds["red"], open("subdomains_filter.txt", "w") as fds["yellow"]:

        for link, sources in found_links.items():
            color = get_link_color(link, status_codes, base_domain, args.domain_filter)
            write_link_to_file(link, status_codes, fds[color])

            output = link

            if SHOW_STATUS:
                if link in status_codes:
                    sc_color = get_status_color(status_codes[link])
                    output = f"[{colored(status_codes[link], sc_color)}] {colored(link, color)}"

                else:
                    output = f"[SKIPPED] {colored(link, color)}"
            else:
                output = colored(link, color)

            print(output)

            if SOURCES:
                for src in sources:
                    print(f"\tFound on: {src}")
                    fds[color].write(f"\tFound on: {src}\n")


if __name__ == "__main__":
    main()