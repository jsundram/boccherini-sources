# Can each holding library be searched by a script?

148 libraries hold 1300 quartet holdings that RISM links no scan for.
This is a verdict per library, with the evidence behind it.

| verdict | libraries | holdings | meaning |
|---|---:|---:|---|
| `api` | 1 | 7 | OAI-PMH or SRU answered at a host RISM links |
| `known` | 23 | 477 | established by hand — works, or actively refuses |
| `website` | 105 | 755 | a site to search, no API at the usual endpoints |
| `no url` | 19 | 61 | RISM records no website and links no host |

A negative is weaker than a positive, and here it is *much* weaker. Of the hosts
probed so far only a single one answered — a public website is rarely the catalogue
server, and the catalogue normally sits on a subdomain no convention predicts. So
`website` means "no OAI or SRU at the conventional paths on the host RISM gives",
not "cannot be automated". Every `known` row, by contrast, was tried directly and
says what actually happened.

Probing is also incomplete: it runs inside a sandbox that requires every host to be
declared in advance, and redirects keep introducing new ones. Results are cached in
`.rism-cache/portals.json`, so re-running this outside the sandbox finishes the job
without repeating any work.

---

## Scriptable (24 libraries, 484 holdings)

Worth writing a resolver for — or, where the note says so, worth not trying again.

| siglum | library | holdings | verdict | evidence |
|---|---|---:|---|---|
| [GB-Lbl](https://rism.online/institutions/30001581) | The British Library | 54 | `known` | British Library search endpoints did not respond to scripted requests. Manual. |
| [I-Nc](https://rism.online/institutions/30000223) | Biblioteca del Conservatorio di Musica S | 52 | `known` | SEARCHED, EXHAUSTED. Internet Culturale holds some digitized Boccherini but no quartet parts. `opac.sbn.it` serves HTML only, and RISM already links its `id.sbn.it` records — which are catalogue entries, not scans. The 52 holdings here are catalogue entries; nothing to fetch. |
| [DK-Km](https://rism.online/institutions/30001346) | Musikmuseet | 47 | `known` | `kb.dk` returned 403 to a scripted request. Manual. |
| [B-Bc](https://rism.online/institutions/30000438) | Conservatoire royal de Bruxelles, Biblio | 44 | `known` | SEARCHED, DEAD END. The Conservatoire runs a Koha catalogue at `catalog.b-bc.org` (e.g. `/cgi-bin/koha/opac-search.pl?q=an:57075`), which is a catalogue only -- no digitized music behind it. Its 44 RISM holdings are records, not scans. |
| [D-Mbs](https://rism.online/institutions/30000882) | Bayerische Staatsbibliothek | 34 | `known` | SEARCHED, EXHAUSTED. BSB digitizes heavily and its delivery API is scriptable (api.digitale-sammlungen.de), but its manuscript portal holds only two Boccherini items and both are quintets (e.g. bsb00112249, GerB 380). Its 34 RISM holdings are catalogue entries, not scans. Not worth a second look. |
| [S-Skma](https://rism.online/institutions/30002153) | Musik- och teaterbiblioteket | 34 | `known` | SEARCHED, NEARLY EXHAUSTED. Search and record pages both return 403 to a script. Of 34 RISM holdings only 4 are digitized; W 4-R was downloaded by hand and turned out to be the Hummel print, not the manuscript both it and RISM call it. |
| [NL-Uim](https://rism.online/institutions/30002045) | Universiteit Utrecht - Instituut voor Mu | 31 | `known` | SEARCHED, DEAD END. Utrecht routes discovery through WorldCat, which mostly returns other libraries' holdings; their own digitized Boccherini is a single minuet. The 31 RISM holdings are catalogue records. RISM links a FAUST database (dmga.faust-hosting.de) and WorldCat for this siglum, neither of which serves images. The library itself has no digital-collections search: uu.nl/en/university-library/searching-for-literature/search-engines lists third-party engines instead, which is why a search returns other libraries' copies. |
| [D-Dl](https://rism.online/institutions/30000042) | Sächsische Landesbibliothek - Staats- un | 28 | `known` | SLUB Dresden publishes IIIF (`iiif.slub-dresden.de`, images on `images.iiif.slub-dresden.de`) and one of its items was downloaded this way, but its catalogue endpoints refused scripted requests. |
| [D-F](https://rism.online/institutions/30000125) | Universitätsbibliothek Johann Christian  | 23 | `known` | SEARCHED, DEAD END for string quartets. Visual Library OAI answers at `sammlungen.ub.uni-frankfurt.de/oai/` (walkable, no keyword search) and the site is behind the same Anubis browser check as Eichstaett. The one item musiconn surfaced, urn:nbn:de:hebis:30-1160725 = Mus.pr.Q 51/41, turns out to be FLUTE quartets -- an arrangement, not the string quartets. Frankfurt shelfmarks read as quartets either way, so check the scoring before fetching. |
| [I-Vc](https://rism.online/institutions/30001975) | Biblioteca del Conservatorio di Musica B | 21 | `known` | Same Italian picture as I-Nc: SBN catalogue records, no digitized quartet parts. |
| [GB-Lam](https://rism.online/institutions/30000263) | Royal Academy of Music, Library | 17 | `known` | SEARCHED, DEAD END. Royal Academy of Music runs Koha at `lib.ram.ac.uk` (`/cgi-bin/koha/opac-search.pl?idx=au&q=boccherini`) -- a catalogue with no digital copies attached, the same picture as B-Bc. Koha instances in this survey have produced nothing: they index holdings, they do not serve images. |
| [E-Mn](https://rism.online/institutions/30001386) | Biblioteca Nacional de España | 17 | `known` | Cloudflare. Every BNE host refuses the TLS handshake to a scripted client, and `curl` from an unblocked machine still gets a challenge page rather than results -- only a browser gets through. A saved results page yielded 14 quartet prints; see BNE-TODO.md. |
| [I-Fn](https://rism.online/institutions/30001783) | Biblioteca nazionale centrale | 14 | `known` | Same Italian picture as I-Nc. |
| [F-Pc](https://rism.online/institutions/30001480) | Bibliothèque du Conservatoire | 13 | `known` | Same Gallica SRU as F-Po. |
| [F-Pmeyer](https://rism.online/institutions/30001487) | Collection André Meyer | 11 | `known` | Same Gallica SRU as F-Po. |
| [F-Pn](https://rism.online/institutions/30001488) | Bibliothèque nationale de France, Départ | 9 | `known` | Same Gallica SRU as F-Po — one search covers all BnF departments. |
| [D-Bhm](https://rism.online/institutions/30000659) | Universität der Künste Berlin, Universit | 8 | `known` | No IIIF or searchable digital collection found for the Universität der Künste. Manual. |
| [A-ST](https://rism.online/institutions/30000384) | Zisterzienserstift Stams, Bibliothek und | 7 | `api` | SRU `https://muscat.rism.info/sru?operation=explain&version=1.2` |
| [F-Po](https://rism.online/institutions/30001489) | Bibliothèque-Musée de l'Opéra | 7 | `known` | Gallica SRU at `gallica.bnf.fr/SRU`, verified: 339 Boccherini items in the BnF music departments, 37 string quartets. Covers every F-P* siglum. |
| [D-MÜs](https://rism.online/institutions/30000239) | Santini-Bibliothek | 6 | `known` | Visual Library OAI-PMH answers at `sammlungen.ulb.uni-muenster.de/oai/`, but OAI has no keyword search — you can only walk sets. No search endpoint found, so the Santini autograph needs a manual look. |
| [US-R](https://rism.online/institutions/30002450) | Sibley Music Library, Eastman School of  | 4 | `known` | Sibley/Rochester resolves through the Handle REST API to `urresearch.rochester.edu`, whose pages carry per-part PDFs. Already harvested by `rism_digitizations.py`. |
| [CZ-Pu](https://rism.online/institutions/30000083) | Národní knihovna České republiky | 1 | `known` | Manuscriptorium needs a portal session before it serves images. |
| [S-Sm](https://rism.online/institutions/30000254) | Musikmuseet | 1 | `known` | SEARCHED, DEAD END. Discovery runs through Alvin, which returns the same items already found via S-Skma. Its own archive interface (arkiv.musikochteaterbiblioteket.se) is Swedish-language, hard to drive, and returns nothing for Boccherini. Sweden as a whole is exhausted: S-Skma had 4 digitized of 34 holdings and S-Sm adds nothing. |
| [F-Prothschild](https://rism.online/institutions/30001492) | Collection Germaine de Rothschild (Baron | 1 | `known` | Same Gallica SRU as F-Po. |

## Needs a person (105 libraries, 755 holdings)

RISM gives a website; no OAI or SRU answered. Search these by hand.

| siglum | library | holdings | verdict | evidence |
|---|---|---:|---|---|
| [D-B](https://rism.online/institutions/30000655) | Staatsbibliothek zu Berlin - Preußischer | 62 | `website` | no OAI/SRU found at <https://staatsbibliothek-berlin.de/>, <https://staatsbibliothek-berlin.de/die-staatsbibliothek/abteilungen/musik>, `digital.slub-dresden.de`, `resolver.staatsbibliothek-berlin.de` |
| [US-CA](https://rism.online/institutions/30002227) | Harvard University, Harvard College Libr | 29 | `website` | no OAI/SRU found at <http://lib.harvard.edu/> |
| [I-Mc](https://rism.online/institutions/30000238) | Biblioteca del Conservatorio Statale di  | 24 | `website` | no OAI/SRU found at <https://www.consmilano.it/it/biblioteca>, `id.sbn.it` |
| [A-Wgm](https://rism.online/institutions/30000388) | Gesellschaft der Musikfreunde in Wien, A | 23 | `website` | no OAI/SRU found at <https://www.musikverein.at/archiv/>, <https://www.musikverein.at/archiv/katalog/> |
| [PL-WRu](https://rism.online/institutions/30002111) | Biblioteka Uniwersytecka | 22 | `website` | no OAI/SRU found at <http://www.bu.uni.wroc.pl/oddzialy/piasek/oddzial-starych-drukow>, <https://www.bu.uni.wroc.pl/oddzialy/curie-zbiory-specjalne/oddzial-zbiorow-muzycznych> |
| [RUS-SPk](https://rism.online/institutions/30002520) | Sankt-Peterburgskaja gosudarstvennaja ko | 21 | `website` | no OAI/SRU found at <https://www.conservatory.ru/science/library> |
| [B-Br](https://rism.online/institutions/30000440) | Bibliothèque royale de Belgique (KBR) -  | 21 | `website` | no OAI/SRU found at <https://www.kbr.be/en/>, <https://www.kbr.be/en/collections/music/> |
| [CZ-K](https://rism.online/institutions/30000183) | Státní oblastní archiv v Třeboni, pobočk | 20 | `website` | no OAI/SRU found at <https://www.ceskearchivy.cz/archivni-oddeleni/soa-cesky-krumlov/uvod> |
| [US-Wc](https://rism.online/institutions/30002492) | The Library of Congress, Music Division | 18 | `website` | no OAI/SRU found at <https://guides.loc.gov/theater-research/music-division>, `lccn.loc.gov` |
| [I-Rc](https://rism.online/institutions/30000230) | Biblioteca Casanatense | 18 | `website` | no OAI/SRU found at <https://casanatense.beniculturali.it/>, `id.sbn.it` |
| [B-Gc](https://rism.online/institutions/30000444) | Koninklijk Muziekconservatorium, Muziekb | 15 | `website` | no OAI/SRU found at <https://schoolofartsgent.be/nl/> |
| [CZ-Pnm](https://rism.online/institutions/30000029) | Národní muzeum - České muzeum hudby, Sbí | 15 | `website` | no OAI/SRU found at <https://www.nm.cz/>, <https://www.nm.cz/ceske-muzeum-hudby#z-nasich-sbirek> |
| [UA-Knbuv](https://rism.online/institutions/30078247) | Nacional'na biblioteka Ukrajiny imeni V. | 14 | `website` | no OAI/SRU found at <http://www.nbuv.gov.ua/node/66> |
| [DK-Kk](https://rism.online/institutions/30001344) | Det Kongelige Bibliotek på Slotsholmen - | 14 | `website` | no OAI/SRU found at <https://www.kb.dk/>, <https://www.kb.dk/en/find-materials/guides/music> |
| [S-L](https://rism.online/institutions/30000153) | Universitetsbiblioteket | 14 | `website` | no OAI/SRU found at <https://www.ub.lu.se/>, <https://www.ub.lu.se/en/find/sheet-music-and-scores> |
| [D-NZfg](https://rism.online/institutions/30003995) | Bibliothek des Freiherrn von Gemmingen-H | 13 | `website` | no OAI/SRU found at <http://www.burg-hornberg.de> |
| [I-Ria](https://rism.online/institutions/30001906) | Biblioteca di Archeologia e Storia dell' | 13 | `website` | no OAI/SRU found at <https://vive.cultura.gov.it/it/biblioteca-archeologia-e-storia-arte>, `id.sbn.it` |
| [J-Tk](https://rism.online/institutions/30004431) | Kunitachi Ongaku Daigaku | 12 | `website` | no OAI/SRU found at <https://www.kunitachi.ac.jp/en/organization/library.html> |
| [FIN-A](https://rism.online/institutions/30002168) | Sibelius-museo, Arkisto | 12 | `website` | no OAI/SRU found at <http://www.sibeliusmuseum.fi/> |
| [RUS-SPsc](https://rism.online/institutions/30000181) | Rossijskaja nacional'naja biblioteka | 12 | `website` | no OAI/SRU found at <https://nlr.ru/> |
| [US-DN](https://rism.online/institutions/30002265) | University of North Texas (UNT), Music L | 11 | `website` | no OAI/SRU found at <http://www.unt.edu/library-technology.htm> |
| [GB-Ckc](https://rism.online/institutions/30001541) | Rowe Music Library, King's College, Univ | 11 | `website` | no OAI/SRU found at <https://www.kings.cam.ac.uk/library/special-collections#rowe> |
| [US-NH](https://rism.online/institutions/30002351) | Yale University, Music Library | 11 | `website` | no OAI/SRU found at <https://web.library.yale.edu/music> |
| [CH-Gc](https://rism.online/institutions/30000234) | Bibliothèque CMG-HEM | 10 | `website` | no OAI/SRU found at <https://www.hesge.ch/hem/la-hem/campus/bibliotheques> |
| [F-C](https://rism.online/institutions/30001435) | Bibliothèque-musée Inguimbertine | 10 | `website` | no OAI/SRU found at <https://inguimbertine.carpentras.fr/> |
| [RUS-Mrg](https://rism.online/institutions/30002528) | Rossijskaja Gosudarstvennaja biblioteka | 9 | `website` | no OAI/SRU found at <https://www.rsl.ru/>, <https://www.rsl.ru/ru/about/funds/mz> |
| [CH-BEk](https://rism.online/institutions/30000222) | Hochschule der Künste Bern, Musikbibliot | 9 | `website` | no OAI/SRU found at <http://www.hkb.bfh.ch/> |
| [CH-EN](https://rism.online/institutions/30000007) | Kloster Engelberg, Musikbibliothek | 9 | `website` | no OAI/SRU found at <https://www.kloster-engelberg.ch/kloster/musikbibliothek/> |
| [I-Gl](https://rism.online/institutions/30001802) | Biblioteca del Conservatorio di musica N | 9 | `website` | no OAI/SRU found at <http://www.conservatoriopaganini.org> |
| [I-OS](https://rism.online/institutions/30003098) | Biblioteca musicale Giuseppe Greggiati | 8 | `website` | no OAI/SRU found at <https://www.comune.ostiglia.mn.it/biblioteca-greggiati>, `id.sbn.it` |
| [SK-BRnm](https://rism.online/institutions/30000017) | Slovenské národné múzeum - Hudobné múzeu | 8 | `website` | no OAI/SRU found at <http://www.snm.sk/?hudobne-muzeum-uvodna-stranka> |
| [I-Bc](https://rism.online/institutions/30001740) | Museo internazionale e biblioteca della  | 8 | `website` | no OAI/SRU found at <http://www.museibologna.it/musica/>, `www.bibliotecamusica.it` |
| [B-MAR](https://rism.online/institutions/30004573) | Abbaye de Maredsous, Bibliothèque | 8 | `website` | no OAI/SRU found at <http://www.maredsous.be> |
| [D-BNba](https://rism.online/institutions/30000692) | Beethoven-Haus, Forschungszentrum Beetho | 8 | `website` | no OAI/SRU found at <http://www.beethoven-haus-bonn.de>, `www.beethoven.de` |
| [I-PAc](https://rism.online/institutions/30001861) | Sezione musicale della Biblioteca Palati | 8 | `website` | no OAI/SRU found at <https://complessopilotta.it/biblioteca-palatina/> |
| [A-GÖ](https://rism.online/institutions/30000342) | Benediktinerabtei, Musikarchiv | 7 | `website` | no OAI/SRU found at <https://www.stiftgoettweig.at/site/kunstkultur/sammlungen> |
| [A-Wn](https://rism.online/institutions/30000398) | Österreichische Nationalbibliothek, Musi | 7 | `website` | no OAI/SRU found at <https://www.onb.ac.at/>, <https://www.onb.ac.at/bibliothek/sammlungen/musik> |
| [CZ-JIa](https://rism.online/institutions/30000580) | Státní oblastní archiv v Třeboni, pobočk | 7 | `website` | no OAI/SRU found at <http://www.ceskearchivy.cz/index.php?doctree=1ec> |
| [US-U](https://rism.online/institutions/30000306) | University of Illinois at Urbana-Champai | 7 | `website` | no OAI/SRU found at <https://www.library.illinois.edu/mpal/> |
| [D-GOl](https://rism.online/institutions/30000045) | Forschungsbibliothek Gotha der Universit | 7 | `website` | no OAI/SRU found at <https://www.uni-erfurt.de/forschungsbibliothek-gotha>, <https://www.uni-erfurt.de/forschungsbibliothek-gotha/sammlungen/handschriften-und-nachlaesse/musikalien>, `digital.slub-dresden.de` |
| [N-Onm](https://rism.online/institutions/30076022) | Nasjonalbiblioteket, Seksjon for Musikk | 7 | `website` | no OAI/SRU found at <https://www.nb.no/> |
| [US-BETm](https://rism.online/institutions/30002214) | Moravian Music Foundation | 7 | `website` | no OAI/SRU found at <https://moravianmusic.org/>, <https://www.moravianchurcharchives.org/> |
| [CH-Gpu](https://rism.online/institutions/30000516) | Bibliothèque de Genève | 7 | `website` | no OAI/SRU found at <http://www.ville-ge.ch/bge> |
| [D-Kl](https://rism.online/institutions/30000836) | Landesbibliothek und Murhardsche Bibliot | 7 | `website` | no OAI/SRU found at <http://www.ub.uni-kassel.de/bb6.html> |
| [D-HER](https://rism.online/institutions/30000048) | Unitätsarchiv der Evangelischen Brüder-U | 7 | `website` | no OAI/SRU found at <http://www.archiv.ebu.de/> |
| [US-WS](https://rism.online/institutions/30002512) | Moravian Music Foundation, Archie K. Dav | 7 | `website` | no OAI/SRU found at <https://moravianmusic.org/> |
| [A-SEI](https://rism.online/institutions/30000121) | Benediktinerstift, Bibliothek und Musika | 7 | `website` | no OAI/SRU found at <http://www.stift-seitenstetten.at/> |
| [I-Rsg](https://rism.online/institutions/30001913) | Archivio musicale della Basilica di San  | 7 | `website` | no OAI/SRU found at <http://www.vatican.va/various/basiliche/san_giovanni/it/archivio_storico/archivio.htm> |
| [I-VIc](https://rism.online/institutions/30005543) | Biblioteca del Conservatorio di Musica d | 7 | `website` | no OAI/SRU found at <https://www.consvi.it/biblioteca/>, `id.sbn.it` |
| [I-Mcv](https://rism.online/institutions/51002491) | Biblioteca della Casa di riposo per musi | 7 | `website` | no OAI/SRU found at <https://www.casaverdi.it/istituzione/biblioteca-di-casa-verdi/>, `id.sbn.it` |
| [I-MC](https://rism.online/institutions/30001834) | Biblioteca dell'Abbazia di Montecassino | 7 | `website` | no OAI/SRU found at <http://www.abbaziamontecassino.org/> |
| [US-AAu](https://rism.online/institutions/30002177) | University of Michigan, Music Library | 7 | `website` | no OAI/SRU found at <http://www.lib.umich.edu/music/> |
| [US-NYcub](https://rism.online/institutions/30000315) | Columbia University, Butler Library | 6 | `website` | no OAI/SRU found at <https://library.columbia.edu/libraries/rbml.html> |
| [I-MOe](https://rism.online/institutions/30001837) | Biblioteca Estense Universitaria | 5 | `website` | no OAI/SRU found at <https://gallerie-estensi.beniculturali.it/biblioteca-estense-universitaria/> |
| [D-FUl](https://rism.online/institutions/30000770) | Hochschul-, Landes- und Stadtbibliothek | 4 | `website` | no OAI/SRU found at <https://www.hs-fulda.de/hlsb/> |
| [US-NYp](https://rism.online/institutions/30000321) | New York Public Library for the Performi | 4 | `website` | no OAI/SRU found at <https://www.nypl.org/locations/lpa/music-division> |
| [US-CHH](https://rism.online/institutions/30002243) | University of North Carolina (UNC), Musi | 4 | `website` | no OAI/SRU found at <https://library.unc.edu/music/>, <https://library.unc.edu/wilson/> |
| [DK-Kmk](https://rism.online/institutions/30001345) | Det Kongelige danske Musikkonservatorium | 4 | `website` | no OAI/SRU found at <https://www.dkdm.dk/Om-DKDM/Faciliteter/Biblioteket> |
| [I-Fc](https://rism.online/institutions/30001778) | Biblioteca del Conservatorio di musica L | 4 | `website` | no OAI/SRU found at <https://www.consfi.it/biblioteca/> |
| [S-HÄ](https://rism.online/institutions/30002136) | Murberget Länsmuseet Västernorrland | 3 | `website` | no OAI/SRU found at <http://www.murberget.se> |
| [S-SK](https://rism.online/institutions/30002158) | Gamla biblioteket | 3 | `website` | no OAI/SRU found at <https://www.skara.se/upplevaochgora/bibliotek/forskaravdelningen/gamlabiblioteket.GamlaBiblioteket.html> |
| [D-LEm](https://rism.online/institutions/30000053) | Leipziger Stadtbibliothek - Musikbibliot | 3 | `website` | no OAI/SRU found at <https://stadtbibliothek.leipzig.de/unsere-bibliotheken/leipziger-stadtbibliothek/>, `digital.slub-dresden.de`, `iiif.slub-dresden.de` |
| [S-J](https://rism.online/institutions/30000200) | Per Brahegymnasiet, Biblioteket | 3 | `website` | no OAI/SRU found at <http://www.pb.edu.jonkoping.se> |
| [F-Lm](https://rism.online/institutions/30001457) | Médiathèque Jean Lévy | 3 | `website` | no OAI/SRU found at <https://bm-lille.fr/Default/accueil-portal.aspx> |
| [E-Mp](https://rism.online/institutions/30001387) | Palacio Real, Biblioteca | 3 | `website` | no OAI/SRU found at <http://www.realbiblioteca.es/> |
| [US-BEm](https://rism.online/institutions/30002210) | Jean Gray Hargrove Music Library - Unive | 2 | `website` | no OAI/SRU found at <https://music.berkeley.edu/resources-and-facilities/jean-gray-hargrove-music-library/>, <https://www.lib.berkeley.edu/visit/music> |
| [CH-E](https://rism.online/institutions/30000006) | Kloster Einsiedeln, Musikbibliothek | 2 | `website` | no OAI/SRU found at <https://www.kloster-einsiedeln.ch/agenda-kultur/kultur/musikbibliothek> |
| [D-MÜu](https://rism.online/institutions/30000186) | Universitäts- und Landesbibliothek | 2 | `website` | no OAI/SRU found at <http://www.ulb.uni-muenster.de/> |
| [A-LA](https://rism.online/institutions/30000354) | Benediktinerstift Lambach, Musikarchiv | 2 | `website` | no OAI/SRU found at <https://www.stift-lambach.at/>, <https://www.stift-lambach.at/musikarchiv/> |
| [I-AN](https://rism.online/institutions/30000249) | Biblioteca comunale Luciano Benincasa | 2 | `website` | no OAI/SRU found at <http://www.cultura.marche.it/musamarche/arim/5.html>, `id.sbn.it` |
| [I-MTc](https://rism.online/institutions/30004845) | Biblioteca comunale Leandro Magnani | 2 | `website` | no OAI/SRU found at <https://biblio.comune.pistoia.it/library/biblioteca-comunale-leandro-magnani-villa-forini-lippi/>, `id.sbn.it` |
| [GB-Mcm](https://rism.online/institutions/30001614) | Royal Northern College of Music - The Li | 2 | `website` | no OAI/SRU found at <http://www.rncm.ac.uk/> |
| [GB-Lcm](https://rism.online/institutions/30001582) | Royal College of Music | 2 | `website` | no OAI/SRU found at <http://www.rcm.ac.uk/> |
| [GB-Mp](https://rism.online/institutions/30001615) | Henry Watson Music Library | 2 | `website` | no OAI/SRU found at <http://www.manchester.gov.uk/info/500138/central_library/6316/what_you_can_do_at_central_library/3> |
| [US-PO](https://rism.online/institutions/30000312) | Vassar College, George Sherman Dickinson | 2 | `website` | no OAI/SRU found at <https://library.vassar.edu/musiclibrary/home> |
| [GB-Cpl](https://rism.online/institutions/30001545) | Pendlebury Library of Music, Faculty of  | 2 | `website` | no OAI/SRU found at <http://www.mus.cam.ac.uk/> |
| [S-Uu](https://rism.online/institutions/30000253) | Universitetsbibliotek, Carolina Rediviva | 2 | `website` | no OAI/SRU found at <http://www.ub.uu.se/> |
| [B-Ac](https://rism.online/institutions/30000428) | Koninklijk Conservatorium - Artesis Hoge | 2 | `website` | no OAI/SRU found at <http://www.ha.be/conservatorium/> |
| [F-AU](https://rism.online/institutions/30001426) | Bibliothèque municipale Jacques Lacarriè | 2 | `website` | no OAI/SRU found at <https://bm-auxerre.fr/> |
| [CH-LAc](https://rism.online/institutions/30000524) | Conservatoire de Lausanne, Bibliothèque | 2 | `website` | no OAI/SRU found at <http://biblio.hemu-cl.ch/> |
| [F-V](https://rism.online/institutions/30001511) | Bibliothèque municipale | 2 | `website` | no OAI/SRU found at <https://bibliotheque.versailles.fr/index.php> |
| [S-Smf](https://rism.online/institutions/30002154) | Stiftelsen Musikkulturens främjande | 2 | `website` | no OAI/SRU found at <http://www.nydahlcoll.se/> |
| [US-Cn](https://rism.online/institutions/30000320) | The Newberry Library | 2 | `website` | no OAI/SRU found at <https://www.newberry.org/> |
| [NL-DHnmi](https://rism.online/institutions/30006492) | Nederlands Muziek Instituut (NMI) - Bibl | 1 | `website` | no OAI/SRU found at <http://www.nederlandsmuziekinstituut.nl> |
| [CH-SO](https://rism.online/institutions/30000012) | Zentralbibliothek, Historische Musiksamm | 1 | `website` | no OAI/SRU found at <http://www.zbsolothurn.ch/> |
| [A-KR](https://rism.online/institutions/30000352) | Benediktinerstift, Musikarchiv | 1 | `website` | no OAI/SRU found at <http://www.stift-kremsmuenster.at> |
| [D-BFb](https://rism.online/institutions/30000034) | Fürst zu Bentheimsche Musikaliensammlung | 1 | `website` | no OAI/SRU found at <http://www.ulb.uni-muenster.de/sammlungen/musik/> |
| [PL-Kj](https://rism.online/institutions/30002079) | Biblioteka Jagiellońska | 1 | `website` | no OAI/SRU found at <https://bj.uj.edu.pl/> |
| [US-PHci](https://rism.online/institutions/30002410) | The Curtis Institute of Music - Library  | 1 | `website` | no OAI/SRU found at <https://www.curtis.edu/learn/library/> |
| [GB-Lwa](https://rism.online/institutions/30001604) | Westminster Abbey Library | 1 | `website` | no OAI/SRU found at <http://www.westminster-abbey.org/library-research> |
| [I-Vqs](https://rism.online/institutions/30001981) | Biblioteca della Fondazione Querini Stam | 1 | `website` | no OAI/SRU found at <https://www.querinistampalia.org/it/> |
| [US-COu](https://rism.online/institutions/30002254) | Music & Dance Library | 1 | `website` | no OAI/SRU found at <http://go.osu.edu/mus> |
| [CH-ZUkaoe](https://rism.online/institutions/51009238) | Kulturarchiv Oberengadin | 1 | `website` | no OAI/SRU found at <https://www.kulturarchiv.ch/kulturarchiv-oberengadin-/-archiv-culturel-dengiadinota> |
| [US-PHu](https://rism.online/institutions/30002433) | University of Pennsylvania Libraries, Va | 1 | `website` | no OAI/SRU found at <https://www.library.upenn.edu/music> |
| [US-WGw](https://rism.online/institutions/30002506) | Colonial Williamsburg - John D. Rockefel | 1 | `website` | no OAI/SRU found at <https://www.colonialwilliamsburg.org/locations/john-d-rockefeller-jr-library/> |
| [I-Mcom](https://rism.online/institutions/30001824) | Biblioteca Sormani | 1 | `website` | no OAI/SRU found at <https://milano.biblioteche.it/library/sormani/> |
| [A-M](https://rism.online/institutions/30000359) | Benediktinerstift, Stiftsbibliothek und  | 1 | `website` | no OAI/SRU found at <http://www.stiftmelk.at> |
| [D-Mmb](https://rism.online/institutions/30000888) | Münchner Stadtbibliothek, Musikbibliothe | 1 | `website` | no OAI/SRU found at <http://www.muenchner-stadtbibliothek.de/bibliotheken/musikbibliothek/> |
| [H-KE](https://rism.online/institutions/30000074) | Helikon Kastélymúzeum Könyvtára | 1 | `website` | no OAI/SRU found at <https://helikonkastely.hu/konyvtar/> |
| [D-Tmi](https://rism.online/institutions/30001016) | Musikwissenschaftliches Institut der Ebe | 1 | `website` | no OAI/SRU found at <https://uni-tuebingen.de/fakultaeten/philosophische-fakultaet/fachbereiche/altertums-und-kunstwissenschaften/musikwissenschaftliches-institut/institut/aktuelles/> |
| [CH-N](https://rism.online/institutions/30000233) | Bibliothèque publique de Neuchâtel | 1 | `website` | no OAI/SRU found at <http://www.bpun.ch/> |
| [D-HEms](https://rism.online/institutions/30000799) | Musikwissenschaftliches Seminar der Rupr | 1 | `website` | no OAI/SRU found at <http://www.musikwissenschaft.uni-hd.de/> |
| [HR-Dsmb](https://rism.online/institutions/30000201) | Franjevački samostan Male braće, knjižni | 1 | `website` | no OAI/SRU found at <http://malabraca.wix.com/malabraca> |
| [B-Lc](https://rism.online/institutions/30000449) | Conservatoire Royal de Liège, Bibliothèq | 1 | `website` | no OAI/SRU found at <http://www.crlg.be/> |
| [I-Vgc](https://rism.online/institutions/30001978) | Biblioteca della Fondazione Giorgio Cini | 1 | `website` | no OAI/SRU found at <http://www.cini.it/biblioteche> |

## No lead but the RISM record (19 libraries, 61 holdings)

Start from the RISM library page, which lists what it holds.

| siglum | library | holdings | verdict | evidence |
|---|---|---:|---|---|
| [F-MH](https://rism.online/institutions/30001468) | Bibliothèque municipale | 10 | `no url` | RISM records no website for this library |
| [D-HR](https://rism.online/institutions/30000814) | Öttingen-Wallersteinsche Bibliothek | 9 | `no url` | RISM records no website for this library |
| [CH-Gamoudruz](https://rism.online/institutions/30000514) | Collection M. Emile Amoudruz | 8 | `no url` | RISM records no website for this library |
| [A-Wnh](https://rism.online/institutions/30000399) | Österreichische Nationalbibliothek, Samm | 7 | `no url` | RISM records no website for this library |
| [D-BDHlebermann](https://rism.online/institutions/30000676) | Privatsammlung Walter Lebermann | 5 | `no url` | RISM records no website for this library |
| [NL-At](https://rism.online/institutions/30002021) | Toonkunst-Bibliotheek | 4 | `no url` | RISM records no website for this library |
| [F-Sim](https://rism.online/institutions/30001502) | Bibliothèque de l'Institut de Musicologi | 3 | `no url` | RISM records no website for this library |
| [GB-Ep](https://rism.online/institutions/30001564) | Public Library | 3 | `no url` | RISM records no website for this library |
| [D-Bsa](https://rism.online/institutions/20000001) | Sing-Akademie zu Berlin, Notenarchiv | 2 | `no url` | RISM records no website for this library |
| [DK-Dschoenbaum](https://rism.online/institutions/30001338) | Privatbibliotek Dr. Camillo Schoenbaum | 1 | `no url` | RISM records no website for this library |
| [F-Rc](https://rism.online/institutions/30001498) | Bibliothèque du Conservatoire | 1 | `no url` | RISM records no website for this library |
| [GB-Lcml](https://rism.online/institutions/30001583) | Central Music Library | 1 | `no url` | RISM records no website for this library |
| [D-MZfederhofer](https://rism.online/institutions/30000924) | Privatbibliothek Prof. Dr. Hellmut Feder | 1 | `no url` | RISM records no website for this library |
| [GB-Lu](https://rism.online/institutions/30001602) | University of London, Senate House Libra | 1 | `no url` | RISM records no website for this library |
| [D-Es](https://rism.online/institutions/30000740) | Staats- und Seminarbibliothek | 1 | `no url` | RISM records no website for this library |
| [US-CHua](https://rism.online/institutions/30003173) | University of Virginia, Alderman Library | 1 | `no url` | RISM records no website for this library |
| [GB-Er](https://rism.online/institutions/30001565) | Reid Music Library | 1 | `no url` | RISM records no website for this library |
| [HR-Dsd](https://rism.online/institutions/30002540) | Samostan sv. Dominika, knjižnica | 1 | `no url` | RISM records no website for this library |
| [F-Gc](https://rism.online/institutions/30001453) | Bibliothèque du Conservatoire | 1 | `no url` | RISM records no website for this library |
