from app.links import extract_pvid, first_url, looks_like_zepto

PVID = "579bf27b-6d7a-4aa8-83d2-2d3455e515d8"


def test_web_url():
    assert extract_pvid(f"https://www.zepto.com/pn/amul-rabri-cup/pvid/{PVID}") == PVID


def test_legacy_zeptonow_url():
    assert extract_pvid(f"https://www.zeptonow.com/pn/x/pvid/{PVID}?utm=share") == PVID


def test_share_text_blob():
    text = f"Check this out on Zepto! https://www.zepto.com/pn/amul-rabri-cup/pvid/{PVID} \U0001f6d2"
    assert extract_pvid(text) == PVID
    assert first_url(text) == f"https://www.zepto.com/pn/amul-rabri-cup/pvid/{PVID}"


def test_branch_deep_link_value():
    url = f"https://zepto.app.link/abc?deep_link_value={PVID}&pid=share"
    assert extract_pvid(url) == PVID


def test_uppercase_normalized():
    assert extract_pvid(f"https://www.zepto.com/pn/x/pvid/{PVID.upper()}") == PVID


def test_no_pvid():
    assert extract_pvid("https://www.zepto.com/") is None
    assert extract_pvid("hello") is None


def test_looks_like_zepto():
    assert looks_like_zepto("https://zepto.app.link/abc")
    assert looks_like_zepto("https://www.zeptonow.com/pn/x")
    assert not looks_like_zepto("https://example.com/pvid/abc")
