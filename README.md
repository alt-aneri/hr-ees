# HR·EES

Interaktivni vodič kroz hrvatski elektroenergetski sustav. Pet alata i hub
stranica, na hrvatskom, namijenjeni obrazovanoj publici koja nije nužno
struka.

Objavljeno na [wonderingneutron.space/alati/](https://wonderingneutron.space/alati/).

| | |
|---|---|
| `index.html` | hub — vodič kroz sustav i popis alata |
| `alat-karta.html` | karta elektrana i 400 kV mreže |
| `alat-opterecenje.html` | krivulje opterećenja i rezidualno opterećenje |
| `alat-simulator.html` | merit order: tko postavlja cijenu |
| `alat-scenariji.html` | scenariji i njihove posljedice |
| `alat-frekvencija.html` | frekvencijski odziv na ispad bloka |
| `assets/app.js` | sva logika i podaci |
| `assets/style.css` | cijeli dizajn sustav |

## Pokretanje

Nema build koraka, package managera ni testova — sve je statični HTML, CSS i
JavaScript. Za lokalni pregled dovoljan je bilo koji statični poslužitelj iz
korijena projekta:

```
python3 -m http.server 8777
```

Otvaranjem datoteka izravno (`file://`) radi sve osim dohvata živih podataka.

## Podaci

Kapaciteti i lokacije elektrana, krivulje opterećenja i troškovi ugrađeni su u
`assets/app.js` kao konstante. Krivulje opterećenja su iz ENTSO-E mjerenja za
2024. i 2025.; popis elektrana slijedi HEP-ovu tablicu proizvodnih postrojenja
i MINGO registar OIE. Granični troškovi u simulatorima su ilustrativni i
označeni kao takvi u samom alatu.

Traka stanja na naslovnici čita `podaci.json` koji svakih sat vremena osvježava
GitHub Action (`dohvati.py`) iz ENTSO-E Transparency Platforme. Podaci se
objavljuju na granu [`podaci`](../../tree/podaci), da satno osvježavanje ne
zatrpava povijest koda. Ako dohvat ne uspije, traka
pada na ilustrativni prikaz — stranica radi i bez mreže.

Frekvencija u toj traci **nije mjerena** i tako je označena: ENTSO-E
Transparency Platforma ne objavljuje frekvenciju sustava.

## Ugrađivanje

Stranice primaju dva parametra:

- `?embed=1` skriva zaglavlje i podnožje, za prikaz u iframeu
- `?theme=dark` ili `?theme=light` postavlja temu; bez toga se prati OS

Tema se može promijeniti i naknadno, porukom `{wnTheme: "dark"}` kroz
`postMessage`.

## Licenca

Apache 2.0, v. [LICENSE.md](LICENSE.md).
