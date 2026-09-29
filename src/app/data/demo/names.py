"""Fictional player names for the demo world.

Given names are common first names; surnames are *invented* by joining regional
fragments, so a generated player is (with overwhelming probability) not a real
one. Accents are included on purpose - search and matching must cope with them.
"""

from __future__ import annotations

import random

FIRST_NAMES = {
    "en": ["Jack", "Callum", "Owen", "Reece", "Tyler", "Noah", "Ollie", "Kai", "Elliot", "Harvey", "Josh", "Ryan", "Connor", "Declan", "Ashton"],
    "es": ["Álvaro", "Iñaki", "Mateo", "Sergio", "Adrián", "Rubén", "Jesús", "Nacho", "Ismael", "Gonzalo", "Unai", "Xavi", "Borja"],
    "fr": ["Théo", "Lucas", "Maxime", "Rémy", "Enzo", "Yanis", "Baptiste", "Corentin", "Loïc", "Killian", "Anthony", "Florian"],
    "de": ["Jonas", "Lukas", "Felix", "Niklas", "Moritz", "Tobias", "Florian", "Jannik", "Leon", "Fabian", "Kilian", "Nico"],
    "it": ["Matteo", "Federico", "Lorenzo", "Alessio", "Davide", "Riccardo", "Emanuele", "Simone", "Nicolò", "Gianluca"],
    "pt": ["Rúben", "Tiago", "João", "Diogo", "Gonçalo", "Rafael", "Nuno", "Vasco", "André", "Bernardo"],
    "af": ["Kwame", "Ibrahima", "Mamadou", "Chidi", "Sékou", "Yaw", "Emeka", "Bakary", "Tunde", "Moussa", "Abdoulaye", "Nabil"],
    "nl": ["Daan", "Sven", "Joost", "Bram", "Stijn", "Ruud", "Teun", "Wout"],
    "nordic": ["Henrik", "Anders", "Mikael", "Sander", "Oskar", "Emil", "Jesper", "Viktor"],
    "balkan": ["Luka", "Marko", "Nikola", "Stefan", "Dario", "Ivo", "Filip", "Milos"],
}

# region -> (prefixes, suffixes); surname = prefix + suffix
SURNAME_PARTS = {
    "en": (["Ash", "Brad", "Cald", "Dun", "Fair", "Gar", "Hol", "Kirk", "Lang", "Mar", "Nor", "Pen", "Rad", "Sut", "Thorn", "Wen", "Hart", "Whit"],
           ["ford", "well", "ley", "ton", "by", "wick", "ham", "shaw", "field", "worth", "combe", "stow"]),
    "es": (["Bal", "Cor", "Domin", "Esp", "Fer", "Gal", "Iba", "Mon", "Nav", "Ort", "Paz", "Que", "Sal", "Tor", "Val", "Zub"],
           ["ñez", "rra", "dez", "guez", "llo", "ndo", "zar", "ral", "ndez", "sco", "rrán", "ola"]),
    "fr": (["Beau", "Cha", "Dela", "Fon", "Gau", "Lam", "Mont", "Pel", "Roux", "Sau", "Tir", "Vau", "Bou", "Ren"],
           ["mont", "lier", "chet", "vin", "teau", "quet", "lard", "ière", "nier", "ault", "ette", "ffre"]),
    "de": (["Bach", "Dörr", "Eich", "Fried", "Gru", "Heil", "Käm", "Lin", "Möl", "Rau", "Sten", "Weiß", "Zim", "Hüb"],
           ["ner", "mann", "berg", "stein", "ler", "hardt", "rich", "dorf", "bauer", "feld", "ling", "meyer"]),
    "it": (["Bar", "Cala", "Dal", "Fio", "Gio", "Lom", "Man", "Pon", "Rus", "Sca", "Tes", "Vit", "Zan", "Ros"],
           ["ldi", "cci", "tti", "nelli", "zzo", "ni", "ssi", "rini", "gna", "letti", "roni", "ardi"]),
    "pt": (["Alm", "Cabr", "Fonse", "Gouv", "Lou", "Mend", "Ne", "Pest", "Quar", "Sanch", "Tav", "Vas", "Rib", "Cost"],
           ["eida", "al", "ca", "eia", "renço", "onça", "ves", "ana", "esma", "ares", "iro", "ela"]),
    "af": (["Adebi", "Bamid", "Dialu", "Ekwun", "Fofan", "Gnamb", "Kouas", "Mbeku", "Ndomb", "Okonu", "Sangur", "Tramb", "Yebul"],
           ["ola", "ené", "ari", "ouma", "izi", "ando", "ege", "oyo", "umé", "ali", "ombo", "aké"]),
    "nl": (["Kuip", "Bos", "Hoek", "Dijk", "Smit", "Veld", "Brink", "Kamp", "Zwart", "Wolt"],
           ["er", "huis", "stra", "sma", "aar", "ens", "hof", "erik", "waard", "ink"]),
    "nordic": (["Lind", "Berg", "Hell", "Sjö", "Nyg", "Ström", "Eng", "Ols", "Häg"],
               ["gren", "qvist", "strand", "holm", "lund", "borg", "dahl", "vik", "ström"]),
    "balkan": (["Ilić", "Jov", "Kov", "Mil", "Pet", "Sav", "Tod", "Vuk", "Đur", "Rad", "Stoj"],
               ["anović", "ić", "ović", "ak", "čić", "ković", "ošević", "ilo"]),
}

REGION_WEIGHTS = {
    "EPL": {"en": 0.52, "af": 0.10, "fr": 0.06, "pt": 0.06, "es": 0.06, "nl": 0.05, "nordic": 0.05, "de": 0.04, "balkan": 0.03, "it": 0.03},
    "La_liga": {"es": 0.58, "pt": 0.08, "fr": 0.06, "af": 0.08, "en": 0.05, "it": 0.05, "balkan": 0.04, "de": 0.03, "nl": 0.03},
    "Bundesliga": {"de": 0.50, "nordic": 0.08, "en": 0.07, "af": 0.09, "nl": 0.06, "balkan": 0.08, "fr": 0.05, "es": 0.04, "pt": 0.03},
    "Serie_A": {"it": 0.55, "es": 0.06, "af": 0.09, "balkan": 0.09, "fr": 0.05, "pt": 0.05, "en": 0.04, "nl": 0.04, "nordic": 0.03},
    "Ligue_1": {"fr": 0.50, "af": 0.20, "es": 0.05, "pt": 0.07, "en": 0.04, "it": 0.04, "balkan": 0.04, "de": 0.03, "nl": 0.03},
}


class NameFactory:
    """Deterministic, collision-free fictional names."""

    def __init__(self, seed: int):
        self._rng = random.Random(seed)
        self._used: set[str] = set()

    def make(self, league: str) -> str:
        weights = REGION_WEIGHTS[league]
        regions, probs = zip(*weights.items())
        for _ in range(50):
            region = self._rng.choices(regions, probs)[0]
            first = self._rng.choice(FIRST_NAMES[region])
            prefixes, suffixes = SURNAME_PARTS[region]
            last = self._rng.choice(prefixes) + self._rng.choice(suffixes)
            last = last[0].upper() + last[1:]
            name = f"{first} {last}"
            if name not in self._used:
                self._used.add(name)
                return name
        raise RuntimeError("name pool exhausted")
