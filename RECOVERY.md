# Obnova repozitára (RECOVERY)

Tento repozitár bol obnovený 21. 11. 2026 z textovej zálohy projektu „aurelvi-ha“ v claude.ai
(snapshot z 28. 10. 2026), pretože pôvodný GitHub účet `sonics007` bol zrušený.
História commitov sa nezachovala – toto je nový počiatočný commit.

## Čo chýba (nebolo v zálohe)

- Binárne súbory: obrázky (webp/png), zvuky (wav), APK súbory, ZIP archívy.
- Jazykové súbory okrem angličtiny a slovenčiny (pôvodne 26 jazykov v `locale/`).
  Testy, ktoré očakávajú 26 jazykov, preto zlyhajú, kým sa nedoplnia.
- Pribalené knižnice `jssip` a `sendspin` (minifikované bundly vo frontende).
- Podpisový kľúč APK (keystore) a súkromný licenčný kľúč – tieto nikdy neboli v Gite.

## Čo bolo pregenerované

- `tools/build_locales.py` vygeneroval `i18n.js`, `frontend/locale/*.json`,
  `translations/*.json` a `strings.json` z `locale/en.json` a `locale/sk.json`.
- `android/assets/` je kópia frontendu z aurelvi-ha (bez Studia).
- `android/examples/*.json` a `THIRD_PARTY_NOTICES.txt` boli zostavené zo zachovaných zdrojov.

Všetky odkazy na pôvodný účet `sonics007` (zdroj aktualizácií, workflowy, README, web, manifest, LICENSE) boli prepísané na `soso8782`.
