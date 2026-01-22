#!/usr/bin/env python3
"""GPU Price Scraper for CoreIndex - Fetches pricing from cloud GPU providers."""

import argparse
import json
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict, field
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    sys.exit("Error: 'requests' not installed. Run: pip install requests")

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

OUTPUT_DIR = Path(__file__).parent / "data"
TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0"}


@dataclass
class GPUOffer:
    source: str
    gpu_name: str
    num_gpus: int = 1
    gpu_ram_gb: float = 0.0
    price_per_hour: float = 0.0
    cpu_cores: float = 0.0
    ram_gb: float = 0.0
    storage_gb: float = 0.0
    reliability: float = 0.0
    location: str = "Unknown"
    cuda_version: str = "Unknown"
    availability: str = "Available"
    provider_type: str = "marketplace"
    scraped_at: str = field(default="")

    def __post_init__(self):
        self.scraped_at = self.scraped_at or datetime.now().isoformat()


# =============================================================================
# API SCRAPERS
# =============================================================================

def scrape_vastai(limit=100):
    """Vast.ai public API."""
    print("Fetching Vast.ai GPU prices...")
    try:
        params = {"q": json.dumps({"verified": {"eq": True}, "rentable": {"eq": True}, "rented": {"eq": False}})}
        resp = requests.get("https://cloud.vast.ai/api/v0/bundles/", params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        offers = resp.json().get("offers", [])[:limit]
    except requests.RequestException as e:
        print(f"  Error: {e}")
        return []

    data = [asdict(GPUOffer(
        source="vast.ai",
        gpu_name=o.get("gpu_name", "Unknown"),
        num_gpus=o.get("num_gpus", 1),
        gpu_ram_gb=round(o.get("gpu_ram", 0) / 1024, 1),
        price_per_hour=round(o.get("dph_total", 0), 4),
        cpu_cores=o.get("cpu_cores_effective", 0),
        ram_gb=round(o.get("cpu_ram", 0) / 1024, 1),
        storage_gb=round(o.get("disk_space", 0), 1),
        reliability=round(o.get("reliability", 0), 4),
        location=o.get("geolocation", "Unknown"),
        cuda_version=str(o.get("cuda_max_good", "Unknown")),
    )) for o in offers]

    print(f"  Found {len(data)} offers")
    return data


def scrape_runpod(limit=100):
    """RunPod GraphQL API."""
    print("Fetching RunPod GPU prices...")
    query = """query { gpuTypes { id displayName memoryInGb communityPrice securePrice } }"""

    try:
        resp = requests.post("https://api.runpod.io/graphql", json={"query": query},
                            headers={**HEADERS, "Content-Type": "application/json"}, timeout=TIMEOUT)
        resp.raise_for_status()
        gpus = resp.json().get("data", {}).get("gpuTypes", [])[:limit]
    except (requests.RequestException, KeyError, TypeError) as e:
        print(f"  Error: {e}")
        return []

    data = []
    for g in gpus:
        name = g.get("displayName", g.get("id", "Unknown"))
        mem = float(g.get("memoryInGb", 0))
        if g.get("communityPrice"):
            data.append(asdict(GPUOffer(source="runpod", gpu_name=name, gpu_ram_gb=mem,
                                        price_per_hour=round(float(g["communityPrice"]), 4))))
        if g.get("securePrice"):
            data.append(asdict(GPUOffer(source="runpod-secure", gpu_name=name, gpu_ram_gb=mem,
                                        price_per_hour=round(float(g["securePrice"]), 4), provider_type="cloud")))

    print(f"  Found {len(data)} offers")
    return data


def scrape_tensordock(limit=100):
    """TensorDock marketplace API with fallback."""
    print("Fetching TensorDock GPU prices...")

    for url in ["https://marketplace.tensordock.com/api/v0/client/stock",
                "https://console.tensordock.com/api/v0/client/stock"]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code == 200:
                stock = resp.json()
                break
        except requests.RequestException:
            continue
    else:
        print("  API unavailable, using reference data")
        return _reference_data("tensordock", [
            ("H100 SXM5", 80, 2.25), ("H100 PCIe", 80, 2.00), ("A100 SXM4", 80, 1.80),
            ("A100 PCIe", 80, 1.50), ("A100 PCIe", 40, 1.10), ("RTX 4090", 24, 0.35),
            ("RTX 3090", 24, 0.20), ("RTX A6000", 48, 0.45), ("L40S", 48, 1.00), ("L40", 48, 0.80),
        ])

    data = []
    if isinstance(stock, dict):
        for loc, gpus in stock.items():
            if isinstance(gpus, dict):
                for model, info in gpus.items():
                    if isinstance(info, dict) and info.get("price"):
                        data.append(asdict(GPUOffer(
                            source="tensordock", gpu_name=model, price_per_hour=round(float(info["price"]), 4),
                            location=loc, availability="Available" if info.get("available", 0) > 0 else "Out of Stock"
                        )))

    print(f"  Found {len(data)} offers")
    return data[:limit] if data else _reference_data("tensordock", [])


# =============================================================================
# REFERENCE PRICING (hardcoded from provider websites)
# =============================================================================

def _reference_data(source, prices, provider_type="reference"):
    """Build GPU offers from (name, vram, price) tuples."""
    return [asdict(GPUOffer(source=source, gpu_name=p[0], gpu_ram_gb=float(p[1]),
                            price_per_hour=p[2], availability="Reference", provider_type=provider_type))
            for p in prices]


def _cloud_data(source, prices, location="Unknown"):
    """Build GPU offers from (instance, gpu_name, num_gpus, vram, price) tuples."""
    return [asdict(GPUOffer(source=source, gpu_name=f"{p[1]} ({p[0]})", num_gpus=p[2],
                            gpu_ram_gb=float(p[3]), price_per_hour=p[4], location=location,
                            availability="on-demand", provider_type="cloud"))
            for p in prices]


def scrape_lambda():
    print("Fetching Lambda Labs GPU prices...")
    data = _reference_data("lambda", [
        ("H100 PCIe", 80, 2.49), ("A100 PCIe", 40, 1.29), ("A10", 24, 0.60),
        ("RTX 6000 Ada", 48, 0.99), ("H100 SXM", 80, 1.99), ("A100 SXM", 80, 1.10),
    ], "cloud")
    print(f"  Found {len(data)} offers (reference)")
    return data


def scrape_coreweave():
    print("Fetching CoreWeave GPU prices...")
    data = _reference_data("coreweave", [
        ("H100 SXM", 80, 4.76), ("H100 PCIe", 80, 4.25), ("A100 SXM", 80, 2.39),
        ("A100 PCIe", 80, 2.21), ("A100 PCIe", 40, 2.06), ("A40", 48, 1.28),
        ("RTX A6000", 48, 1.28), ("RTX A5000", 24, 0.77), ("RTX A4000", 16, 0.61),
    ], "cloud")
    print(f"  Found {len(data)} offers (reference)")
    return data


def scrape_aws():
    print("Fetching AWS EC2 GPU prices...")
    data = _cloud_data("aws", [
        ("p5.48xlarge", "H100 SXM", 8, 80, 98.32), ("p4d.24xlarge", "A100 SXM", 8, 40, 32.77),
        ("p4de.24xlarge", "A100 SXM", 8, 80, 40.97), ("p3.2xlarge", "V100", 1, 16, 3.06),
        ("p3.16xlarge", "V100", 8, 16, 24.48), ("g5.xlarge", "A10G", 1, 24, 1.006),
        ("g5.12xlarge", "A10G", 4, 24, 5.672), ("g4dn.xlarge", "T4", 1, 16, 0.526),
    ], "us-east-1")
    print(f"  Found {len(data)} offers (reference)")
    return data


def scrape_gcp():
    print("Fetching GCP GPU prices...")
    data = _reference_data("gcp", [
        ("H100 80GB", 80, 3.93), ("A100 80GB", 80, 3.67), ("A100 40GB", 40, 2.93),
        ("L4", 24, 0.81), ("T4", 16, 0.35), ("V100", 16, 2.48),
    ], "cloud")
    print(f"  Found {len(data)} offers (reference)")
    return data


def scrape_azure():
    print("Fetching Azure GPU prices...")
    data = _cloud_data("azure", [
        ("ND96asr_v4", "A100 80GB", 8, 80, 27.197), ("NC24ads_A100_v4", "A100 80GB", 1, 80, 3.673),
        ("NC96ads_A100_v4", "A100 80GB", 4, 80, 14.692), ("NV36ads_A10_v5", "A10", 1, 24, 1.80),
        ("NC6s_v3", "V100", 1, 16, 3.06), ("NC4as_T4_v3", "T4", 1, 16, 0.526),
    ], "East US")
    print(f"  Found {len(data)} offers (reference)")
    return data


# =============================================================================
# PLAYWRIGHT SCRAPERS (for JS-rendered sites)
# =============================================================================

def _scrape_with_playwright(url):
    """Fetch page content using Playwright."""
    if not PLAYWRIGHT_AVAILABLE:
        return ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        print(f"  Playwright error: {e}")
        return ""


def _extract_gpu_name(text):
    """Extract GPU model from text using regex."""
    patterns = [
        r"(RTX\s*(?:PRO\s*)?[3456]0[789]0(?:\s*(?:Ti|S))?)", r"(RTX\s*[AB]?[456]000(?:\s*Ada)?)",
        r"([AHL]100(?:\s*(?:PCIe|SXM|NVL))?(?:\s*\d+GB)?)", r"(H200|B200)", r"(V100|L40S?|L4|A10G?|T4)",
    ]
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE):
            return match.group(1).strip()
    return "Unknown GPU"


def _extract_price(text):
    """Extract hourly price from text."""
    for pattern in [r"\$(\d+\.?\d*)\s*/?\s*(?:hr|hour)", r"(\d+\.?\d*)\s*\$/?\s*(?:hr|hour)"]:
        if match := re.search(pattern, text, re.IGNORECASE):
            try:
                return round(float(match.group(1)), 4)
            except ValueError:
                pass
    return 0.0


def _scrape_js_site(name, url):
    """Generic scraper for JS-rendered GPU pricing sites."""
    print(f"Fetching {name} GPU prices...")
    if not PLAYWRIGHT_AVAILABLE:
        print("  Skipped: Playwright not installed")
        return []

    html = _scrape_with_playwright(url)
    if not html or not BeautifulSoup:
        return []

    soup = BeautifulSoup(html, "html.parser")
    data, seen = [], set()
    gpu_keywords = ["RTX", "A100", "H100", "H200", "V100", "L40", "3090", "4090"]

    for elem in soup.find_all(["div", "tr", "td", "span", "p", "article"]):
        text = elem.get_text(strip=True)
        if any(gpu in text.upper() for gpu in gpu_keywords) and ("$" in text or "/hr" in text.lower()):
            if 20 < len(text) < 400:
                gpu, price = _extract_gpu_name(text), _extract_price(text)
                if (gpu, price) not in seen:
                    seen.add((gpu, price))
                    data.append(asdict(GPUOffer(source=name, gpu_name=gpu, price_per_hour=price)))

    print(f"  Found {len(data)} offers")
    return data[:50]


def scrape_compute_exchange():
    return _scrape_js_site("compute.exchange", "https://compute.exchange")


def scrape_silicondata():
    return _scrape_js_site("silicondata.com", "https://silicondata.com")


# =============================================================================
# OUTPUT
# =============================================================================

def save_json(data, filename):
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} items to {path}")


def save_csv(data, filename):
    if not data:
        return
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    fields = ["source", "gpu_name", "num_gpus", "gpu_ram_gb", "price_per_hour", "cpu_cores",
              "ram_gb", "storage_gb", "reliability", "location", "cuda_version", "availability",
              "provider_type", "scraped_at"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    print(f"Saved {len(data)} items to {path}")


def print_summary(data):
    if not data:
        return

    print("\n" + "=" * 60)
    print("GPU PRICE SUMMARY")
    print("=" * 60)

    by_source = {}
    for item in data:
        by_source.setdefault(item["source"], []).append(item)

    for source, items in sorted(by_source.items()):
        prices = [i["price_per_hour"] for i in items if i["price_per_hour"] > 0]
        print(f"\n{source}: {len(items)} offers", end="")
        if prices:
            print(f" | ${min(prices):.4f} - ${max(prices):.4f}/hr | avg ${sum(prices)/len(prices):.4f}/hr")
        else:
            print()

    priced = [d for d in data if d["price_per_hour"] > 0 and d.get("num_gpus", 1) == 1]
    if priced:
        print("\n" + "-" * 60)
        print("Top 10 Cheapest (single GPU):")
        for item in sorted(priced, key=lambda x: x["price_per_hour"])[:10]:
            print(f"  ${item['price_per_hour']:>7.4f}/hr  {item['gpu_name']:<25} ({item['source']})")


# =============================================================================
# MAIN
# =============================================================================

SCRAPERS = {
    "vastai": scrape_vastai, "runpod": scrape_runpod, "tensordock": scrape_tensordock,
    "lambda": scrape_lambda, "coreweave": scrape_coreweave, "aws": scrape_aws,
    "gcp": scrape_gcp, "azure": scrape_azure, "compute": scrape_compute_exchange,
    "silicon": scrape_silicondata,
}
GROUPS = {"live": ["vastai", "runpod", "tensordock"], "cloud": ["lambda", "coreweave", "aws", "gcp", "azure"]}


def main():
    parser = argparse.ArgumentParser(description="Scrape GPU prices from cloud providers")
    parser.add_argument("--source", "-s", default="all", help="Source: all|live|cloud|vastai|runpod|...")
    parser.add_argument("--output", "-o", choices=["json", "csv", "both"], default="both")
    parser.add_argument("--limit", "-l", type=int, default=200, help="Max offers per source")
    parser.add_argument("--no-summary", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("GPU Price Scraper for CoreIndex")
    print("=" * 60 + "\n")

    sources = GROUPS.get(args.source, [args.source] if args.source != "all" else list(SCRAPERS.keys()))
    if not PLAYWRIGHT_AVAILABLE:
        sources = [s for s in sources if s not in ["compute", "silicon"]]

    all_data = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(SCRAPERS[s], args.limit) if s in ["vastai", "runpod", "tensordock"]
                   else executor.submit(SCRAPERS[s]): s for s in sources if s in SCRAPERS}
        for future in as_completed(futures):
            try:
                all_data.extend(future.result())
            except Exception as e:
                print(f"  Error: {e}")

    print(f"\n{'=' * 60}\nTotal: {len(all_data)} items\n{'=' * 60}")

    if all_data:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if args.output in ["json", "both"]:
            save_json(all_data, "gpu_prices.json")
            save_json(all_data, f"gpu_prices_{ts}.json")
        if args.output in ["csv", "both"]:
            save_csv(all_data, "gpu_prices.csv")
        if not args.no_summary:
            print_summary(all_data)

    print("\nDone!")


if __name__ == "__main__":
    main()
