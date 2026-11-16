"""Manually check existing service access without sending email or writing data."""

import os
import smtplib
import socket
from urllib.parse import urlparse

import requests
from supabase import create_client


def check_supabase():
    url = os.environ["SUPABASE_URL"]
    socket.getaddrinfo(urlparse(url).hostname, 443)
    client = create_client(url, os.environ["SUPABASE_SECRET_KEY"])
    rows = client.table("chunks").select("chunk_id").limit(1).execute().data
    print(f"Supabase: connected and read chunks table ({len(rows)} sample rows).")


def check_openalex():
    params = {"search": "military artificial intelligence", "per_page": 1, "page": 2}
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    response = requests.get("https://api.openalex.org/works", params=params, timeout=30)
    if response.status_code != 200:
        print(f"OpenAlex: HTTP {response.status_code}.")
        if response.status_code == 429:
            print("OpenAlex: request budget or rate limit reached. Check the API key and usage budget.")
        return False
    print(f"OpenAlex: basic page 2 returned {len(response.json().get('results', []))} results.")
    return True


def check_gmail():
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(os.environ["EMAIL_ADDRESS"], os.environ["EMAIL_PASSWORD"])
    print("Gmail: SMTP login succeeded. No email was sent.")


def main():
    failed = False
    for name, check in [("Supabase", check_supabase), ("OpenAlex", check_openalex), ("Gmail", check_gmail)]:
        try:
            if check() is False:
                failed = True
        except socket.gaierror:
            print(f"{name}: hostname could not be resolved.")
            failed = True
        except smtplib.SMTPAuthenticationError as error:
            print(f"{name}: authentication rejected (SMTP {error.smtp_code}).")
            failed = True
        except Exception as error:
            # Exception messages can contain credential-bearing request URLs.
            print(f"{name}: connection failed ({type(error).__name__}).")
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
