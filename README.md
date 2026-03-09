# CrawlStrike
**CrawlStrike** is a Python-based recursive web crawler designed for reconnaissance, surface mapping, and link discovery.
It performs BFS crawling, extracts links from HTML and JavaScript, and visits all discovered internal URLs.

## Features
- Recursive internal crawling (BFS-based and regex-based):
  - HTML links (`a`, `script`, `img`, `iframe`, `form`, etc.)
  - Inline JavaScript URLs
  - External JavaScript URLs
  - Absolute & relative URLs via regex in `javascript`, `json`, `xml`, `txt`, `html` files

- Tracks where each link was found (`--source`)

- Proxy support (`--proxy`)

- URLs in output are colored as follows:
  - 🟢: Same domain (stored also in `in_scope.txt`)
  - 🟡: Subdomains & domains containing the string specified in `-f` parameter (stored also in `subdomains_filter.txt`)
  - 🔴: External domain (stored also in `oos.txt`)

# Installation
```bash
pip3 install -r requirements.txt
```

# Usage
```bash
python3 crawlstrike.py [--source] [--proxy PROXY] [-f DOMAIN_FILTER] [-sc] [--output OUTPUT] url
```

## Example
```bash
python crawlstrike.py https://example.com
```

## Arguments
| **Argument** | **Description** |
| ------------ | --------------- |
| `--source` | Show source pages for each identified url |
| `--proxy PROXY` | Forward request to a proxy (`http://127.0.0.1:8080`) |
| `-f DOMAIN_FILTER`, `--domain-filter DOMAIN_FILTER` | Extra domain filter |
| `-sc` | Generate files with identified links, grouped by status codes (i.e. `2xx.txt`, `3xx.txt`, `error.txt`, `skipped.txt`) |
| `--output OUTPUT` | Output folder |

# TO DO
- Multiple input analysis (via URLs in input TXT file)
- Pause management via CTRL+P and intermediate state save
- Results stored in DB
- Define OoS filter 