import json

from cyberdigest.feeds import _parse_cisa_kev_json


def test_parse_cisa_kev():
    payload = {
        "vulnerabilities": [
            {
                "cveID": "CVE-2024-9999",
                "vulnerabilityName": "Test Vuln",
                "vendorProject": "Vendor",
                "product": "Product",
                "dateAdded": "2024-01-15",
                "shortDescription": "A test issue",
                "dueDate": "2024-02-01",
                "notes": "See https://example.com/advisory for details",
            }
        ]
    }
    parsed = _parse_cisa_kev_json(json.dumps(payload).encode())
    assert len(parsed.entries) == 1
    e = parsed.entries[0]
    assert "CVE-2024-9999" in e["title"]
    assert e["link"].startswith("https://")
    assert "Vendor" in e["summary"]
