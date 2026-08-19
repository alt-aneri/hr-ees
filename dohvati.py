#!/usr/bin/env python3
"""Dohvat podataka o hrvatskom EES-u s ENTSO-E Transparency Platforme.

Piše `podaci.json` koji hr-ees čita s raw.githubusercontent.com.

Namjerno bez vanjskih ovisnosti (samo standardna biblioteka) — nema
`pip install` koraka u Actionu, nema lanca ovisnosti koji može propasti
usred noći, a skripta se može pokrenuti lokalno bez ičega osim Pythona.

ENTSO-E vraća XML. Namespace se razlikuje po tipu dokumenta, pa se
elementi traže po lokalnom imenu umjesto po punom nazivu s namespaceom —
inače bi svaka promjena verzije sheme razbila parsiranje.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

BAZA = "https://web-api.tp.entsoe.eu/api"
HR = "10YHR-HEP------M"          # hrvatska regulacijska zona / tržišno područje
TOKEN = os.environ.get("ENTSOE_TOKEN", "").strip()

# ENTSO-E izvore označava šiframa (psrType). Prevode se ovdje, a ne pri
# prikazu: podaci.json je javan i netko ga može čitati bez ovog repoa, pa nema
# smisla da mora tražiti šifrarnik. Šifre koje se u hrvatskoj zoni ne pojavljuju
# (offshore vjetar, nuklearna — Krško je slovensko) nisu navedene i prolaze kao
# vlastita šifra.
IZVORI = {
    "B01": "biomasa",
    "B02": "lignit",
    "B03": "plin iz ugljena",
    "B04": "plin",
    "B05": "kameni ugljen",
    "B06": "loživo ulje",
    "B09": "geotermalna",
    "B10": "reverzibilna HE",
    "B11": "protočna HE",
    "B12": "akumulacijska HE",
    "B15": "ostali obnovljivi",
    "B16": "sunce",
    "B17": "otpad",
    "B18": "vjetar (pučina)",
    "B19": "vjetar (kopno)",
    "B20": "ostalo",
    "B25": "pohrana",
}

# Susjedi za prekogranične tokove. Ključ je oznaka koju prikazujemo.
SUSJEDI = {
    "SI": "10YSI-ELES-----O",
    "HU": "10YHU-MAVIR----U",
    "BA": "10YBA-JPCC-----D",
    "RS": "10YCS-SERBIATSOV",
}


def sat(dt):
    """ENTSO-E traži yyyyMMddHHmm u UTC-u."""
    return dt.strftime("%Y%m%d%H%M")


def _dohvati(params, u_zaglavlju):
    """Jedan HTTP poziv. Vraća korijen XML-a; iznimke propušta pozivatelju."""
    p = dict(params)
    headers = {}
    if u_zaglavlju:
        headers["SECURITY_TOKEN"] = TOKEN
    else:
        p["securityToken"] = TOKEN
    url = BAZA + "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        return ET.fromstring(r.read())


# Zaglavlje SECURITY_TOKEN dokumentirano je za POST, a securityToken u query
# stringu za GET. Naši upiti su GET, pa prvi pokušaj ide zaglavljem (token tada
# nije u URL-u), a na 401 se ponavlja s parametrom. Nakon prvog uspjeha način
# se pamti, da se ne udvostručuje svaki poziv.
_nacin = {"zaglavlje": True}


def upit(**params):
    """Jedan poziv API-ju. Vraća korijen XML-a ili None."""
    for pokusaj in (_nacin["zaglavlje"], not _nacin["zaglavlje"]):
        try:
            korijen = _dohvati(params, pokusaj)
            _nacin["zaglavlje"] = pokusaj
            return korijen
        except urllib.error.HTTPError as e:
            if e.code == 401 and pokusaj != (not _nacin["zaglavlje"]):
                continue          # probaj drugi način slanja tokena
            # 400 = loš upit, 429 = prekoračena kvota, 401 na oba načina = loš token.
            # Ne rušimo cijeli dohvat zbog jednog upita: bolje objaviti
            # djelomične podatke nego nijedne.
            print(f"  ! HTTP {e.code} za {params.get('documentType')}", file=sys.stderr)
            return None
        except Exception as e:  # mreža, timeout, neispravan XML
            # Ispisuje se samo tip iznimke: poruka zna sadržavati URL, a u
            # jednom od dva načina token je u URL-u.
            print(f"  ! {type(e).__name__} za {params.get('documentType')}", file=sys.stderr)
            return None
    return None


def djeca(el, ime):
    """Elementi zadanog lokalnog imena, bez obzira na namespace."""
    return [d for d in el.iter() if d.tag.rsplit("}", 1)[-1] == ime]


def tocke(korijen, polje):
    """Izvlači (vrijeme, vrijednost) iz svih TimeSeries/Period/Point.

    `polje` je 'quantity' (količine) ili 'price.amount' (cijene).
    """
    out = []
    if korijen is None:
        return out
    for period in djeca(korijen, "Period"):
        poc_el = djeca(period, "start")
        rez_el = djeca(period, "resolution")
        if not poc_el or not rez_el:
            continue
        try:
            poc = datetime.strptime(poc_el[0].text, "%Y-%m-%dT%H:%MZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        rez = rez_el[0].text
        korak = {"PT15M": 15, "PT30M": 30, "PT60M": 60, "PT1H": 60}.get(rez)
        if korak is None:
            continue
        for p in djeca(period, "Point"):
            poz = djeca(p, "position")
            vr = djeca(p, polje)
            if not poz or not vr:
                continue
            try:
                i = int(poz[0].text)
                v = float(vr[0].text)
            except (TypeError, ValueError):
                continue
            out.append((poc + timedelta(minutes=korak * (i - 1)), v))
    out.sort()
    return out


def zadnja(niz):
    return niz[-1][1] if niz else None


def main():
    if not TOKEN:
        # Nepostavljen token nije kvar nego stanje "još nije podešeno" —
        # izlazimo uspješno da cron ne šalje obavijest o padu svakih sat
        # vremena dok token ne stigne s ENTSO-E-a (dodjeljuje se ručno,
        # zna potrajati danima).
        print("ENTSOE_TOKEN nije postavljen — preskačem dohvat. "
              "Postavi ga u Settings → Secrets and variables → Actions.")
        return 0

    sada = datetime.now(timezone.utc)
    # Prozor unatrag: objavljena mjerenja kasne, pa gledamo šire i uzimamo
    # zadnju točku koja stvarno postoji.
    od, do = sada - timedelta(hours=8), sada + timedelta(hours=1)
    # Cijene su dan-unaprijed, pa im treba prozor koji pokriva cijeli dan.
    cod, cdo = sada - timedelta(hours=2), sada + timedelta(hours=24)

    print("opterećenje…")
    opt = tocke(
        upit(documentType="A65", processType="A16", outBiddingZone_Domain=HR,
             periodStart=sat(od), periodEnd=sat(do)),
        "quantity",
    )

    print("proizvodnja po izvorima…")
    prod_xml = upit(documentType="A75", processType="A16", in_Domain=HR,
                    periodStart=sat(od), periodEnd=sat(do))
    proizvodnja = {}
    if prod_xml is not None:
        for ts in djeca(prod_xml, "TimeSeries"):
            vrsta = djeca(ts, "psrType")
            if not vrsta:
                continue
            niz = tocke(ts, "quantity")
            v = zadnja(niz)
            if v is not None:
                # isti psrType zna doći u više TimeSeries (npr. i potrošnja
                # agregata) — zbrajamo umjesto da se međusobno gaze
                proizvodnja[vrsta[0].text] = proizvodnja.get(vrsta[0].text, 0) + v

    print("cijena dan-unaprijed…")
    cijene = tocke(
        upit(documentType="A44", in_Domain=HR, out_Domain=HR,
             periodStart=sat(cod), periodEnd=sat(cdo)),
        "price.amount",
    )
    # Za "trenutno" uzimamo cijenu sata u kojem jesmo, ne zadnju objavljenu
    # (zadnja je često sutrašnja).
    sat_sada = sada.replace(minute=0, second=0, microsecond=0)
    cijena_sad = next((v for t, v in cijene if t == sat_sada), None)

    print("prekogranični tokovi…")
    razmjena = {}
    for oznaka, eic in SUSJEDI.items():
        izvoz = zadnja(tocke(
            upit(documentType="A11", out_Domain=HR, in_Domain=eic,
                 periodStart=sat(od), periodEnd=sat(do)), "quantity"))
        uvoz = zadnja(tocke(
            upit(documentType="A11", out_Domain=eic, in_Domain=HR,
                 periodStart=sat(od), periodEnd=sat(do)), "quantity"))
        if izvoz is not None or uvoz is not None:
            # pozitivno = neto uvoz u Hrvatsku
            razmjena[oznaka] = round((uvoz or 0) - (izvoz or 0))

    podaci = {
        "osvjezeno": sada.replace(microsecond=0).isoformat(),
        "izvor": "ENTSO-E Transparency Platform",
        "zona": HR,
        "opterecenje_mw": round(zadnja(opt)) if zadnja(opt) is not None else None,
        "opterecenje_vrijeme": opt[-1][0].isoformat() if opt else None,
        "cijena_eur_mwh": round(cijena_sad, 2) if cijena_sad is not None else None,
        "proizvodnja_mw": {
            IZVORI.get(k, k): round(v)
            for k, v in sorted(proizvodnja.items(), key=lambda p: -p[1])
        },
        "razmjena_mw": razmjena,
        "neto_razmjena_mw": sum(razmjena.values()) if razmjena else None,
    }

    # Ako baš ništa nije stiglo, ne prepisuj zatečenu datoteku ispraznom —
    # bolje je prikazati podatke od prije sat vremena nego rupu.
    if podaci["opterecenje_mw"] is None and not proizvodnja and not razmjena:
        print("Nijedan upit nije uspio — ostavljam prethodni podaci.json.",
              file=sys.stderr)
        return 1

    with open("podaci.json", "w", encoding="utf-8") as f:
        json.dump(podaci, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("zapisano:", json.dumps(podaci, ensure_ascii=False)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
