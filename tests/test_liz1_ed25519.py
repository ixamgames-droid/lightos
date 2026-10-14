"""LIZ-1: Ed25519 in reinem Python gegen die Testvektoren aus RFC 8032, 7.1."""
from __future__ import annotations

import pytest

from src.core import ed25519

# (geheim, oeffentlich, nachricht, signatur) — RFC 8032 Abschnitt 7.1, TEST 1-3
# und TEST SHA(abc).
VEKTOREN = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    ("833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
     "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
     "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
     "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
     "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
     "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704"),
]


@pytest.mark.parametrize("geheim,oeffentlich,nachricht,signatur", VEKTOREN)
def test_rfc8032_vektor(geheim, oeffentlich, nachricht, signatur):
    g, o = bytes.fromhex(geheim), bytes.fromhex(oeffentlich)
    n, s = bytes.fromhex(nachricht), bytes.fromhex(signatur)
    assert ed25519.oeffentlicher_schluessel(g) == o
    assert ed25519.signiere(g, n) == s
    assert ed25519.pruefe(o, n, s) is True


def test_veraenderte_nachricht_oder_signatur_faellt_durch():
    g, o, n, s = (bytes.fromhex(x) for x in VEKTOREN[2])
    assert ed25519.pruefe(o, n + b"x", s) is False
    kaputt = bytearray(s)
    kaputt[5] ^= 0x01
    assert ed25519.pruefe(o, n, bytes(kaputt)) is False
    fremd = bytes.fromhex(VEKTOREN[1][1])
    assert ed25519.pruefe(fremd, n, s) is False


@pytest.mark.parametrize("oeffentlich,signatur", [
    (b"", b""),
    (b"\x00" * 31, b"\x00" * 64),
    (b"\x00" * 32, b"\x00" * 63),
    (b"\xff" * 32, b"\xff" * 64),          # kein Punkt, s zu gross
    (None, None),
])
def test_unsinn_wirft_nicht(oeffentlich, signatur):
    assert ed25519.pruefe(oeffentlich, b"abc", signatur) is False


def test_s_muss_kleiner_als_gruppenordnung_sein():
    """Signatur mit s + L ist dieselbe Gleichung, aber nicht kanonisch."""
    g, o, n, s = (bytes.fromhex(x) for x in VEKTOREN[0])
    gross = int.from_bytes(s[32:], "little") + ed25519._L
    assert ed25519.pruefe(o, n, s[:32] + gross.to_bytes(32, "little")) is False
