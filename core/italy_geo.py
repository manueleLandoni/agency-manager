from __future__ import annotations

REGION_ORDER_NORTH_TO_SOUTH = [
    'Valle d\'Aosta',
    'Piemonte',
    'Lombardia',
    'Trentino-Alto Adige',
    'Veneto',
    'Friuli-Venezia Giulia',
    'Liguria',
    'Emilia-Romagna',
    'Toscana',
    'Umbria',
    'Marche',
    'Lazio',
    'Abruzzo',
    'Molise',
    'Campania',
    'Puglia',
    'Basilicata',
    'Calabria',
    'Sicilia',
    'Sardegna',
]

REGION_TO_PROVINCES = {
    'Abruzzo': ['Chieti', "L'Aquila", 'Pescara', 'Teramo'],
    'Basilicata': ['Matera', 'Potenza'],
    'Calabria': ['Catanzaro', 'Cosenza', 'Crotone', 'Reggio Calabria', 'Vibo Valentia'],
    'Campania': ['Avellino', 'Benevento', 'Caserta', 'Napoli', 'Salerno'],
    'Emilia-Romagna': ['Bologna', 'Ferrara', 'Forli-Cesena', 'Modena', 'Parma', 'Piacenza', 'Ravenna', 'Reggio Emilia', 'Rimini'],
    'Friuli-Venezia Giulia': ['Gorizia', 'Pordenone', 'Trieste', 'Udine'],
    'Lazio': ['Frosinone', 'Latina', 'Rieti', 'Roma', 'Viterbo'],
    'Liguria': ['Genova', 'Imperia', 'La Spezia', 'Savona'],
    'Lombardia': ['Bergamo', 'Brescia', 'Como', 'Cremona', 'Lecco', 'Lodi', 'Mantova', 'Milano', 'Monza e Brianza', 'Pavia', 'Sondrio', 'Varese'],
    'Marche': ['Ancona', 'Ascoli Piceno', 'Fermo', 'Macerata', 'Pesaro e Urbino'],
    'Molise': ['Campobasso', 'Isernia'],
    'Piemonte': ['Alessandria', 'Asti', 'Biella', 'Cuneo', 'Novara', 'Torino', 'Verbano-Cusio-Ossola', 'Vercelli'],
    'Puglia': ['Bari', 'Barletta-Andria-Trani', 'Brindisi', 'Lecce', 'Foggia', 'Taranto'],
    'Sardegna': ['Cagliari', 'Gallura Nord-Est Sardegna', 'Medio Campidano', 'Nuoro', 'Ogliastra', 'Oristano', 'Sassari', 'Sulcis Iglesiente'],
    'Sicilia': ['Agrigento', 'Caltanissetta', 'Catania', 'Enna', 'Messina', 'Palermo', 'Ragusa', 'Siracusa', 'Trapani'],
    'Toscana': ['Arezzo', 'Firenze', 'Grosseto', 'Livorno', 'Lucca', 'Massa-Carrara', 'Pisa', 'Pistoia', 'Prato', 'Siena'],
    'Trentino-Alto Adige': ['Bolzano', 'Trento'],
    'Umbria': ['Perugia', 'Terni'],
    'Valle d\'Aosta': ['Aosta'],
    'Veneto': ['Belluno', 'Padova', 'Rovigo', 'Treviso', 'Venezia', 'Verona', 'Vicenza'],
}


def list_regions_north_to_south() -> list[str]:
    return REGION_ORDER_NORTH_TO_SOUTH.copy()


def list_provinces_for_region(region: str) -> list[str]:
    return REGION_TO_PROVINCES.get(region, []).copy()


def is_valid_region(region: str) -> bool:
    return region in REGION_TO_PROVINCES


def is_valid_province_for_region(region: str, province: str) -> bool:
    return province in REGION_TO_PROVINCES.get(region, [])
