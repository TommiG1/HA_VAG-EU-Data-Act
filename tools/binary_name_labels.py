"""Multilingual entity names for all curated binary sensors (by translation_key).

Keyed by translation_key. English values match curated.name in data.py.
Regenerate coverage check: python tools/verify_binary_translations.py
"""

from __future__ import annotations

# en -> {de, fr, it, nl}
_BY_ENGLISH: dict[str, dict[str, str]] = {
    "Vehicle locked": {
        "de": "Fahrzeug verriegelt",
        "fr": "Véhicule verrouillé",
        "it": "Veicolo bloccato",
        "nl": "Voertuig vergrendeld",
    },
    "Vehicle open": {
        "de": "Fahrzeug offen",
        "fr": "Véhicule ouvert",
        "it": "Veicolo aperto",
        "nl": "Voertuig open",
    },
    "Parking brake": {
        "de": "Feststellbremse",
        "fr": "Frein de stationnement",
        "it": "Freno di stazionamento",
        "nl": "Parkeerrem",
    },
    "Parking light left": {
        "de": "Standlicht links",
        "fr": "Feu de position gauche",
        "it": "Luce di posizione sinistra",
        "nl": "Stadslicht links",
    },
    "Parking light right": {
        "de": "Standlicht rechts",
        "fr": "Feu de position droit",
        "it": "Luce di posizione destra",
        "nl": "Stadslicht rechts",
    },
    "Parking lights": {
        "de": "Standlichter",
        "fr": "Feux de position",
        "it": "Luci di posizione",
        "nl": "Stadslichten",
    },
    "Immediate charging": {
        "de": "Sofortladen",
        "fr": "Charge immédiate",
        "it": "Carica immediata",
        "nl": "Direct laden",
    },
    "Immediate discharging": {
        "de": "Sofort entladen",
        "fr": "Décharge immédiate",
        "it": "Scarica immediata",
        "nl": "Direct ontladen",
    },
    "Timer charging": {
        "de": "Timer-Laden",
        "fr": "Charge programmée",
        "it": "Carica a timer",
        "nl": "Timerladen",
    },
    "Timer charging climatization": {
        "de": "Timer-Laden mit Klima",
        "fr": "Charge programmée + clim",
        "it": "Carica timer con clima",
        "nl": "Timerladen met klimaat",
    },
    "Home storage charging": {
        "de": "Heimspeicher-Laden",
        "fr": "Charge stockage domestique",
        "it": "Carica accumulo domestico",
        "nl": "Thuisopslag laden",
    },
    "Only own current": {
        "de": "Nur eigener Strom",
        "fr": "Courant propre uniquement",
        "it": "Solo corrente propria",
        "nl": "Alleen eigen stroom",
    },
    "Preferred charging times": {
        "de": "Bevorzugte Ladezeiten",
        "fr": "Horaires de charge préférés",
        "it": "Orari di carica preferiti",
        "nl": "Voorkeurslaadtijden",
    },
    "Front left door lock": {
        "de": "Türschloss vorne links",
        "fr": "Serrure porte avant gauche",
        "it": "Serratura porta anteriore sinistra",
        "nl": "Deurslot voor links",
    },
    "Front right door lock": {
        "de": "Türschloss vorne rechts",
        "fr": "Serrure porte avant droite",
        "it": "Serratura porta anteriore destra",
        "nl": "Deurslot voor rechts",
    },
    "Rear left door lock": {
        "de": "Türschloss hinten links",
        "fr": "Serrure porte arrière gauche",
        "it": "Serratura porta posteriore sinistra",
        "nl": "Deurslot achter links",
    },
    "Rear right door lock": {
        "de": "Türschloss hinten rechts",
        "fr": "Serrure porte arrière droite",
        "it": "Serratura porta posteriore destra",
        "nl": "Deurslot achter rechts",
    },
    "Tailgate lock": {
        "de": "Heckklappenschloss",
        "fr": "Serrure hayon",
        "it": "Serratura portellone",
        "nl": "Achterklepvergrendeling",
    },
    "Hood lock": {
        "de": "Motorhaubenschloss",
        "fr": "Serrure capot",
        "it": "Serratura cofano",
        "nl": "Motorkapslot",
    },
    "Front left door": {
        "de": "Tür vorne links",
        "fr": "Porte avant gauche",
        "it": "Porta anteriore sinistra",
        "nl": "Deur voor links",
    },
    "Front right door": {
        "de": "Tür vorne rechts",
        "fr": "Porte avant droite",
        "it": "Porta anteriore destra",
        "nl": "Deur voor rechts",
    },
    "Rear left door": {
        "de": "Tür hinten links",
        "fr": "Porte arrière gauche",
        "it": "Porta posteriore sinistra",
        "nl": "Deur achter links",
    },
    "Rear right door": {
        "de": "Tür hinten rechts",
        "fr": "Porte arrière droite",
        "it": "Porta posteriore destra",
        "nl": "Deur achter rechts",
    },
    "Tailgate": {
        "de": "Heckklappe",
        "fr": "Hayon",
        "it": "Portellone",
        "nl": "Achterklep",
    },
    "Hood": {
        "de": "Motorhaube",
        "fr": "Capot",
        "it": "Cofano",
        "nl": "Motorkap",
    },
    "Front right door safe": {
        "de": "Tür vorne rechts sicher",
        "fr": "Porte avant droite sécurisée",
        "it": "Porta anteriore destra sicura",
        "nl": "Deur voor rechts veilig",
    },
    "Rear left door safe": {
        "de": "Tür hinten links sicher",
        "fr": "Porte arrière gauche sécurisée",
        "it": "Porta posteriore sinistra sicura",
        "nl": "Deur achter links veilig",
    },
    "Rear right door safe": {
        "de": "Tür hinten rechts sicher",
        "fr": "Porte arrière droite sécurisée",
        "it": "Porta posteriore destra sicura",
        "nl": "Deur achter rechts veilig",
    },
    "Tailgate safe": {
        "de": "Heckklappe sicher",
        "fr": "Hayon sécurisé",
        "it": "Portellone sicuro",
        "nl": "Achterklep veilig",
    },
    "Hood safe": {
        "de": "Motorhaube sicher",
        "fr": "Capot sécurisé",
        "it": "Cofano sicuro",
        "nl": "Motorkap veilig",
    },
    "Front left window": {
        "de": "Fenster vorne links",
        "fr": "Vitres avant gauche",
        "it": "Finestrino anteriore sinistro",
        "nl": "Raam voor links",
    },
    "Front right window": {
        "de": "Fenster vorne rechts",
        "fr": "Vitres avant droite",
        "it": "Finestrino anteriore destro",
        "nl": "Raam voor rechts",
    },
    "Rear left window": {
        "de": "Fenster hinten links",
        "fr": "Vitres arrière gauche",
        "it": "Finestrino posteriore sinistro",
        "nl": "Raam achter links",
    },
    "Rear right window": {
        "de": "Fenster hinten rechts",
        "fr": "Vitres arrière droite",
        "it": "Finestrino posteriore destro",
        "nl": "Raam achter rechts",
    },
    "Sunroof": {
        "de": "Schiebedach",
        "fr": "Toit ouvrant",
        "it": "Tetto apribile",
        "nl": "Schuifdak",
    },
    "Sunroof motor 3": {
        "de": "Schiebedachmotor 3",
        "fr": "Moteur toit ouvrant 3",
        "it": "Motore tetto apribile 3",
        "nl": "Schuifdakmotor 3",
    },
    "Hood state": {
        "de": "Motorhaubenstatus",
        "fr": "État capot",
        "it": "Stato cofano",
        "nl": "Motorkapstatus",
    },
    "Service hatch": {
        "de": "Serviceklappe",
        "fr": "Trappe de service",
        "it": "Sportello di servizio",
        "nl": "Serviceklep",
    },
    "Spoiler": {
        "de": "Spoiler",
        "fr": "Spoiler",
        "it": "Spoiler",
        "nl": "Spoiler",
    },
    "Window heating front": {
        "de": "Scheibenheizung vorne",
        "fr": "Chauffage vitre avant",
        "it": "Riscaldamento vetro anteriore",
        "nl": "Ruitverwarming voor",
    },
    "Window heating rear": {
        "de": "Scheibenheizung hinten",
        "fr": "Chauffage vitre arrière",
        "it": "Riscaldamento vetro posteriore",
        "nl": "Ruitverwarming achter",
    },
    "Charging LED": {
        "de": "Lade-LED",
        "fr": "LED de charge",
        "it": "LED di carica",
        "nl": "Laad-LED",
    },
    "Energy flow": {
        "de": "Energiefluss",
        "fr": "Flux d'énergie",
        "it": "Flusso di energia",
        "nl": "Energiestroom",
    },
    "Charging plug": {
        "de": "Ladeplug",
        "fr": "Prise de charge",
        "it": "Presa di ricarica",
        "nl": "Laadstekker",
    },
    "Central lock": {
        "de": "Zentralverriegelung",
        "fr": "Verrouillage central",
        "it": "Blocco centralizzato",
        "nl": "Centrale vergrendeling",
    },
    "Charging": {
        "de": "Lädt",
        "fr": "En charge",
        "it": "In carica",
        "nl": "Aan het laden",
    },
}

# translation_key -> English name (all curated binary sensors)
_BINARY_KEYS: dict[str, str] = {
    "locked": "Vehicle locked",
    "open": "Vehicle open",
    "parking_brake": "Parking brake",
    "parking_light_left": "Parking light left",
    "parking_light_right": "Parking light right",
    "charge_mode_selection_options_immediate_charging": "Immediate charging",
    "charge_mode_selection_options_immediate_discharging": "Immediate discharging",
    "charge_mode_selection_options_timer_charging": "Timer charging",
    "charge_mode_selection_options_timer_charging_climatization": (
        "Timer charging climatization"
    ),
    "charge_mode_selection_options_home_storage_charging": "Home storage charging",
    "charge_mode_selection_options_only_own_current": "Only own current",
    "charge_mode_selection_options_preferred_charging_times": "Preferred charging times",
    "locked_state_front_left_door": "Front left door lock",
    "locked_state_front_right_door": "Front right door lock",
    "locked_state__rear_left_door": "Rear left door lock",
    "locked_state_rear_right_door": "Rear right door lock",
    "locked_state_tailgate": "Tailgate lock",
    "locked_state_front_engine_bonnet": "Hood lock",
    "open_state_front_left_door": "Front left door",
    "open_state_front_right_door": "Front right door",
    "open_state_rear_left_door": "Rear left door",
    "open_state_rear_right_door": "Rear right door",
    "open_state_tailgate": "Tailgate",
    "open_state_front_engine_bonnet": "Hood",
    "safe_state_front_right_door": "Front right door safe",
    "safe_state_rear_left_door": "Rear left door safe",
    "safe_state_rear_right_door": "Rear right door safe",
    "safe_state_tailgate": "Tailgate safe",
    "safe_state_front_engine_bonnet": "Hood safe",
    "state_front_left_door_window_lifter": "Front left window",
    "state_front_right_door_window_lifter": "Front right window",
    "state_rear_left_door_window_lifter": "Rear left window",
    "state_rear_right_door_window_lifter": "Rear right window",
    "state_sunroof_motor_hood_1": "Sunroof",
    "state_sunroof_motor_hood_3": "Sunroof motor 3",
    "parking_lights": "Parking lights",
    "state_of_hood": "Hood state",
    "state_service_hatch": "Service hatch",
    "state_spoiler": "Spoiler",
    "window_heating_state_front": "Window heating front",
    "window_heating_state_rear": "Window heating rear",
    "led_state": "Charging LED",
    "energy_flow": "Energy flow",
    "plug_state": "Charging plug",
    "lock_state": "Central lock",
    "charging": "Charging",
}


def _labels(en: str) -> dict[str, str]:
    loc = _BY_ENGLISH[en]
    return {"en": en, **loc}


def build_name_labels() -> dict[str, dict]:
    """Return {translation_key: {names: {lang: label}}} for binary sensors."""
    out: dict[str, dict] = {}
    for key, en in _BINARY_KEYS.items():
        out[key] = {"names": _labels(en)}
    return out


NAME_LABELS: dict[str, dict] = build_name_labels()
