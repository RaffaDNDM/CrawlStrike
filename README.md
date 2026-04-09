# CrawlStrike
**CrawlStrike** is a high-performance, multiprocessed recursive web crawler built for reconnaissance and surface mapping. It uses a **Manager-based shared state** to perform lightning-fast link discovery while ensuring no URL is processed twice.

## Key Features
- **Multiprocessed Engine:** Leverages all CPU cores for simultaneous request handling.
- **Deep Extraction:** - Parses HTML tags (`a`, `script`, `img`, `iframe`, `form`).
  - Regex-based discovery in `javascript`, `json`, `xml`, and `txt` for absolute/relative paths.
- **Resumable Scans:** Automated state saving to `.pkl` files. If a scan is interrupted with `Ctrl+C`, you can resume exactly where you left off by starting again the script with the same parameters.
- **Flexible Proxying:** Native support for both **HTTP** and **SOCKS5** (e.g., Tor integration).
- **Categorized Logging:** Automatically sorts findings into `2xx.csv`, `3xx.csv`, `4xx.csv`, `5xx.csv`, and `error.csv`.

## Installation
```bash
pip3 install -r requirements.txt
```

## Usage
```bash
python3 crawlstrike.py [URL] [OPTIONS]
```

![](https://3928478158-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FhjMjdRXwO33Lfo7uCpl6%2Fuploads%2Fgit-blob-1e1999fccd66d06e1e0a0810c949c8406011470c%2Frun.png?alt=media)

![](https://3928478158-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FhjMjdRXwO33Lfo7uCpl6%2Fuploads%2Fgit-blob-58d5551221b91c201b215833bd9df41551900506%2Fpause.png?alt=media)

### Arguments
| **Argument** | **Description** |
| ------------ | --------------- |
| `--follow-redirect`| Follow HTTP redirects (3xx) |
| `--header` | Add custom HTTP headers (Format: `"Key: Value"`) |
| `--no-subdomains` | Restrict crawl strictly to the main domain |
| `--output` | Specify output folder (Defaults to domain name) |
| `--proxy` | HTTP/HTTPS proxy (`http://127.0.0.1:8080`)<br>If SOCKS5 proxy is defined, HTTP proxy will be disabled. |
| `--socks` | SOCKS proxy (`socks5://127.0.0.1:9050`)|
| `-w`, `--workers` | Number of parallel processes (Default: CPU count) |
| `--wayback` | Retrieve Wayback Machine URLs at the beginning and use them as additional input |

### Examples
```bash
# Standard crawl with 20 workers
python3 crawlstrike.py https://example.com -w 20

# Crawl via Tor (SOCKS5)
python3 crawlstrike.py https://example.com --socks socks5://127.0.0.1:9050

# Custom headers and output folder
python3 crawlstrike.py https://example.com --header "Authorization: Bearer token" --output my_scan
```

## Output
By default the script will create an output folder named as the target URL domain:
```bash
python3 crawlstrike.py https://target.com -w 20
```

```bash
target.com/             <-- Default Folder
├── 2xx.csv             # Successes
├── 3xx.csv             # Redirects
├── 4xx.csv             # Client Errors (404, etc.)
├── 5xx.csv             # Server Errors
└── error.csv           # Network/Proxy/SOCKS Failures
target.com.pkl          # Session state (for resuming)
```

If output folder is specified, the script will use it for the output:
```bash
python3 crawlstrike.py https://target.com -w 20 --output myscan
```

```bash
myscan/             <-- Default Folder
├── 2xx.csv             # Successes
├── 3xx.csv             # Redirects
├── 4xx.csv             # Client Errors (404, etc.)
├── 5xx.csv             # Server Errors
└── error.csv           # Network/Proxy/SOCKS Failures
myscan.pkl          # Session state (for resuming)
```

### Error Handling (`error.csv`)
The `error.csv` file captures non-HTTP network failures:
* **Network:** `ConnectError`, `ConnectTimeout` (DNS or Firewall issues).
* **Protocol:** `SSLError`, `ProtocolError` (Encryption/Handshake failures).
* **Streaming:** `ReadTimeout`, `ReadError` (Interrupted data transfer).
* **Logic:** `InvalidURL`, `RemoteProtocolError`.