"""Lexer fuer die Command-Line (MA-/Avolites-Style).

Zerlegt einen Eingabe-String in eine Liste von Tokens, die der Parser
in eine ausfuehrbare Aktion umwandelt.
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass


class TokenType(Enum):
    NUMBER = "NUMBER"
    KEYWORD = "KEYWORD"     # thru, at, plus, minus, all, full, off, ...
    STRING = "STRING"       # "in Anfuehrungszeichen"
    OPERATOR = "OPERATOR"   # + - @
    EOF = "EOF"


@dataclass
class Token:
    type: TokenType
    value: str
    pos: int


# Bekannte Keywords. Alles andere wird trotzdem als KEYWORD ausgegeben
# (z.B. ein Cue-Name), aber der Parser unterscheidet ueber den .value.
KEYWORDS = {
    "thru", "at", "all", "full", "off", "ff",
    "clear", "cl",
    "record", "cue", "scene",
    "go", "g", "back", "stop", "blackout", "bo",
    "highlight", "hi", "lowlight", "lo",
    "page", "next", "prev",
    "intensity", "dim",
    "r", "red", "g", "green", "b", "blue", "w", "white",
    "pan", "tilt", "zoom", "focus", "strobe", "shutter",
    "plus", "minus",
}


def tokenize(text: str) -> list[Token]:
    """Tokenisiert den Eingabe-String. Defensive — wirft nie."""
    tokens: list[Token] = []
    try:
        i = 0
        text = (text or "").strip()
        while i < len(text):
            c = text[i]
            if c.isspace():
                i += 1
                continue
            if c in "+-@":
                tokens.append(Token(TokenType.OPERATOR, c, i))
                i += 1
                continue
            if c == '"':
                end = text.find('"', i + 1)
                if end < 0:
                    end = len(text)
                tokens.append(Token(TokenType.STRING, text[i + 1:end], i))
                i = end + 1
                continue
            # Number oder Word
            j = i
            while j < len(text) and not text[j].isspace() and text[j] not in "+-@\"":
                j += 1
            tok = text[i:j].lower()
            if tok.replace(".", "", 1).isdigit() and tok.count(".") <= 1 and tok != ".":
                tokens.append(Token(TokenType.NUMBER, tok, i))
            elif tok in KEYWORDS:
                tokens.append(Token(TokenType.KEYWORD, tok, i))
            else:
                # Unbekannte Worte als KEYWORD durchreichen (z.B. Scene-Namen
                # ausserhalb von Anfuehrungszeichen).
                tokens.append(Token(TokenType.KEYWORD, tok, i))
            i = j
    except Exception as e:
        # Niemals crashen — wir liefern was wir bisher haben.
        print(f"[cmdline.lexer] tokenize error: {e}")
    tokens.append(Token(TokenType.EOF, "", len(text or "")))
    return tokens
