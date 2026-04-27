import requests
import browser_cookie3
from urllib.parse import urlparse
from requests import Session
from urllib.parse import urljoin
import os
from dotenv import load_dotenv

load_dotenv()

def get_base_url() -> str:
    base = os.getenv("BASE_URL", "https://database.beatymuseum.ubc.ca/").lower()
    if not base:
        raise RuntimeError(f"Missing BASE_URL in .env")
    return base.rstrip("/")

def _cookie_domain(base_url: str) -> str:
    host = urlparse(base_url).hostname
    if not host:
        raise ValueError(f"Bad base URL: {base_url}")
    return host

def make_session(
    preferred=("chrome", "firefox", "safari"),
    verify_tls=True,
) -> requests.Session:
    """
    Loads cookies from the user's browser cookie store and returns a requests.Session.
    User must already be logged in to base_url in that browser.
    """
    base_url = get_base_url()
    domain = _cookie_domain(base_url)

    print(f"Getting credentials for {base_url}")

    loaders = {
        "chrome": lambda: browser_cookie3.chrome(domain_name=domain),
        "firefox": lambda: browser_cookie3.firefox(domain_name=domain),
        "safari": lambda: browser_cookie3.safari(domain_name=domain),
        # Also available if you want later:
        # "edge": lambda: browser_cookie3.edge(domain_name=domain),
        # "chromium": lambda: browser_cookie3.chromium(domain_name=domain),
        # "opera": lambda: browser_cookie3.opera(domain_name=domain),
    }

    last_err = None
    for name in preferred:
        if name not in loaders:
            continue
        try:
            cj = loaders[name]()
            s = LiveServerSession(base_url=base_url)
            s.cookies = cj
            s.headers.update({"Accept": "application/json"})
            s.verify = verify_tls
            # lightweight auth check
            r = s.get(f"/context/user.json", timeout=20)
            if r.status_code == 200:
                return s
            last_err = RuntimeError(f"{name}: cookie load ok but auth check failed ({r.status_code}).")
        except Exception as e:
            last_err = e

    raise RuntimeError(
        "Could not obtain an authenticated session from browser cookies. "
        "Make sure you are logged in to Specify in one of these browsers: "
        f"{', '.join(preferred)}. Last error: {last_err}"
    )


class LiveServerSession(Session):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url.rstrip("/") + "/"

    def request(self, method, url, *args, **kwargs):
        url = str(url)
        joined_url = urljoin(self.base_url, url.lstrip("/"))
        return super().request(method, joined_url, *args, **kwargs)
