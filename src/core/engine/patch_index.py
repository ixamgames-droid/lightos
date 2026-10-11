"""ENG-30: Geraet zu einer fid nachschlagen statt suchen.

Szenen, Matrizen, EFX und gemappte Kanaele fragten je Wert bzw. je Zelle
„welches Geraet hat diese fid?" — und beantworteten es mit einem Durchlauf
durch die ganze Patch-Liste. Bei 80 Geraeten und einem Look aus neun Szenen
waren das rund 450 Durchlaeufe je DMX-Frame, jeder Vergleich ein Attributzugriff
auf ein Datenbank-Objekt: knapp die Haelfte der Frame-Zeit.

:class:`PatchListe` ist dieselbe Liste mit einer Tabelle ``fid -> Geraet``
daneben. Der ``FunctionManager`` baut sie, sobald sich die Patch-Liste aendert,
und reicht sie an ``write`` weiter. Wer eine gewoehnliche Liste hereingibt
(Vorschau, Tests), bekommt die bisherige Suche.

Gleiches Ergebnis wie die Suche: bei doppelter fid gewinnt das erste Geraet;
eine unbekannte fid ergibt ``None``.
"""
from __future__ import annotations


class PatchListe(list):
    """Patch-Liste mit Nachschlagetabelle ``fid -> Geraet``."""

    __slots__ = ("quelle", "_nach_fid", "_anzahl")

    def __init__(self, fixtures=()):
        super().__init__(fixtures or ())
        # Die Liste, aus der diese gebaut wurde (haelt sie am Leben — damit ist
        # der Vergleich ``quelle is ...`` sicher gegen wiederverwendete ids).
        self.quelle = fixtures
        self._baue()

    def _baue(self):
        tabelle: dict | None = {}
        try:
            for fx in self:
                fid = getattr(fx, "fid", None)
                if fid not in tabelle:          # das ERSTE gewinnt, wie die Suche
                    tabelle[fid] = fx
        except TypeError:
            tabelle = None                      # nicht hashbare fid -> Suche
        self._nach_fid = tabelle
        self._anzahl = len(self)

    def finde(self, fid):
        """Das Geraet mit dieser fid — oder ``None``."""
        if len(self) != self._anzahl:           # nachtraeglich veraendert
            self._baue()
        tabelle = self._nach_fid
        if tabelle is not None:
            try:
                return tabelle.get(fid)
            except TypeError:                   # nicht hashbare Frage
                pass
        for fx in self:
            if getattr(fx, "fid", None) == fid:
                return fx
        return None

    def passt_zu(self, patch_cache) -> bool:
        """Ob diese Liste noch dem Stand von ``patch_cache`` entspricht:
        dieselbe Quell-Liste UND dieselben Geraete an denselben Plaetzen (der
        Listenvergleich prueft je Platz zuerst die Identitaet — kein
        Attributzugriff, ein paar Mikrosekunden bei 80 Geraeten)."""
        return self.quelle is patch_cache and self == patch_cache
